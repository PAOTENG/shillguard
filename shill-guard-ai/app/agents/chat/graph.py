"""对话 Agent 的 LangGraph 状态机（Chat Agent 流程的核心引擎）。

============================================================================
本文件对应总体流程的哪一部分
============================================================================
对应 __init__.py 总体流程编号 ③④⑤⑥⑦⑧：
  ③ build_graph()/get_graph()        —— 图构建与 PostgreSQL 持久化
  ④ memory_node()                    —— 节点1：记忆检索 + 摘要压缩
  ⑤ rag_node() / _should_retrieve()  —— 节点2：Adaptive RAG 路由 + 检索
  ⑥ context_processor_node()         —— 节点3：Worker LLM 提炼背景（架构隔离）
  ⑦ chat_node()                      —— 节点4：Main LLM 推理生成回答
  ⑧ tools（ToolNode）                —— 节点5：web_search 工具执行

调用关系（谁来调用本文件）：
  - router.py::chat() 通过 get_graph() 拿到编译后的图，再 graph.astream_events 触发执行。
  - router.py / history_router.py 通过 get_pg_pool() 共享 PostgreSQL 连接池。
执行入口：graph 被 astream_events 驱动后，LangGraph 自动按边调度各节点。

============================================================================
【图结构（5节点，memory/rag 并行）】
    ┌── memory ──┐
    │            ├── context_processor → chat ──有tool_calls?──→ tools ──→ chat(循环)
    └──  rag   ──┘                           └──无tool_calls──→ END

【并行优化】memory_node 与 rag_node 完全独立，写入不同 state 字段，
  并行执行可节省 max(mem0_latency, rag_latency) - min(mem0_latency, rag_latency)
  的等待时间（约 600ms+），context_processor_node 等全部完成后再运行。

【Adaptive RAG（查询路由 / 自适应检索）】
  rag_node 内置轻量路由器 _should_retrieve：在执行实际检索前，先用 Worker LLM
  判断当前查询是否需要查阅知识库。无关问题（闲聊/日期/数学/天气等）直接返回空
  rag_context，跳过 embedding + BM25 + rerank 全流程，节省 ~2-4s。
  知识库内容描述集中在 _RAG_CORPUS_DESC 变量，新增 RAG 文件时只需更新该常量。
  路由失败时采用保守策略（默认执行检索），避免漏回答知识库相关问题。

【架构隔离（Context Engineering - Isolate 策略）—— 防复读根本解法】
  context_processor_node 是 Worker LLM：读取所有原始背景数据（memories/summary/RAG），
  通过 prompt 内嵌 JSON 强制输出 WorkerContextResult，
  提炼为单句 background_fact 写入 processed_context。
  chat_node (Main LLM) 只看 processed_context，永远看不到原始 memories/summary/RAG。
  这是防止 LLM 复读的根本解法（架构隔离），而不是事后 regex 清洗。

【三层记忆】
  Layer 1 - 滑动窗口：chat_node 只将最近 N 条消息传给 LLM（trim_messages 思路）
  Layer 2 - LLM 摘要：memory_node 将旧消息压缩为摘要，写入独立 summary state key
  Layer 3 - mem0 跨会话记忆：memory_node 检索 mem0，router 异步写入（含 AMG 校验）

【双轨存储（Context Engineering 主流模式）】
  checkpointer (PostgresSaver) → LLM 工作记忆，可被摘要压缩
  chat_messages 表             → UI 展示历史，append-only，永不删除
  两者严格分离，UI 永远读 chat_messages，不读 checkpointer。
"""
# ── 标准库导入 ──────────────────────────────────────────────────────────────
# asyncio：异步并发（memory/rag 并行、信号量限流、超时控制）
import asyncio
# time：perf_counter 高精度计时，用于各节点耗时打点（[TIMER] 日志）
import time
# json：解析 Worker LLM 输出的 JSON 背景事实
import json
# re：正则提取 yes/no 路由判断、提取 JSON 片段
import re
# Annotated/Optional/TypedDict：类型注解，TypedDict 定义图状态结构
from typing import Annotated, Optional, TypedDict

# ── LangChain / LangGraph 消息与图原语 ─────────────────────────────────────
# BaseMessage：所有消息的基类；HumanMessage/AIMessage/SystemMessage：三种角色消息
# RemoveMessage：LangGraph 删除旧消息的指令（摘要压缩时用）
from langchain_core.messages import (
    BaseMessage, HumanMessage, AIMessage, SystemMessage, RemoveMessage,
)
# StateGraph：状态图；START/END：图的起点终点
from langgraph.graph import StateGraph, START, END
# add_messages：消息列表的 reducer（新消息追加而非覆盖，按 id 去重更新）
from langgraph.graph.message import add_messages
# AsyncPostgresSaver：LangGraph 异步 PostgreSQL checkpointer（持久化工作记忆）
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
# AsyncConnectionPool：psycopg3 异步连接池（与 checkpointer、chat_messages 共用）
from psycopg_pool import AsyncConnectionPool
# dict_row：让 psycopg 返回 dict 行（而非元组），方便按字段名取值
from psycopg.rows import dict_row
# ToolNode：预置工具执行节点；tools_condition：判断 LLM 输出是否有 tool_calls 的条件路由
from langgraph.prebuilt import ToolNode, tools_condition

# ── 项目内模块导入 ──────────────────────────────────────────────────────────
# get_llm：主对话 LLM；get_expander_llm：轻量 Worker LLM（路由/提炼用，便宜快）
from app.llm import get_llm, get_expander_llm
# build_system_prompt：组装 Main LLM 的 system prompt（架构隔离版）
from app.agents.chat.prompts import build_system_prompt
# 三层记忆相关函数：mem0 检索 / 旧消息摘要 / 用户历史发言提取
from app.agents.chat.memory import (
    search_memories,
    summarize_old_messages,
    format_user_said_history,
)
# WorkerContextResult：Worker LLM 结构化输出模型 + 清洗
from app.agents.chat.schemas import WorkerContextResult
# ensure_table：初始化 chat_messages 双轨存储表
from app.agents.chat.history_store import ensure_table
# retrieve：RAG 混合检索（ES BM25 + pgvector + RRF + rerank）
from app.rag.retriever import retrieve
# settings：全局配置（DB 连接、阈值、并发数等）
from app.config import settings
# get_web_search_tool：联网搜索工具（chat_node 可调用）
from app.tools import get_web_search_tool


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _sanitize_window(messages: list[BaseMessage]) -> list[BaseMessage]:
    """清洗发送给 Main LLM 的消息窗口，防止 API 400 tool 消息结构错误。

    【功能 / 流程定位】
      属于节点4 chat_node 的前置清洗步骤（⑦ 的子步骤）。
      chat_node 取最近 N 条滑动窗口后立即调用本函数，再拼 SystemMessage 发给 LLM。
      本函数结束后，调用方（chat_node）拿到结构合法的消息列表，下一步拼 system prompt。

    【为什么需要】
      滑动窗口会把消息列表"拦腰截断"，可能切坏 OpenAI 兼容 API 要求的
      tool 消息结构（AIMessage(tool_calls) 必须紧跟对应的 ToolMessage），导致 400。

    【处理三类问题】
      1. 窗口开头/中间的孤立 ToolMessage（前驱 AIMessage(tool_calls) 不在窗口内）
      2. AIMessage 有多个 tool_calls，但对应的 ToolMessage 不完整
         （旧版顺序扫描只检查"前一条是否是 AIMessage"，无法处理第 2+ 个 ToolMessage）
      3. 末尾悬空的 AIMessage(tool_calls)（对应 ToolMessage 完全不在窗口内）

    【策略】把 AIMessage(tool_calls) + 其全部对应 ToolMessages 作为原子单元。
      - 若所有 tool_call_id 都有对应 ToolMessage → 整组保留
      - 若有任何一个 tool_call_id 缺少 ToolMessage → 整组丢弃
      单独出现的 ToolMessage（无对应 AIMessage 上下文）直接丢弃。

    参数:
        messages: chat_node 截取的最近 N 条原始消息（可能被窗口切坏）

    返回:
        结构合法、可安全发给 LLM 的消息列表（可能比输入短）
    """
    # 局部导入 ToolMessage：仅本函数用到，放函数内避免顶层污染
    from langchain_core.messages import ToolMessage

    # Step 1：从第一个 HumanMessage 开始，丢弃任何前置乱序消息
    # next(...) + 生成器：找到第一个 HumanMessage 的索引 i；找不到则用 0
    # 意义：窗口头部若以 ToolMessage/AIMessage 开头（被截断的残组）一律砍掉
    start = next((i for i, m in enumerate(messages) if isinstance(m, HumanMessage)), 0)
    # 切片得到从首条 HumanMessage 开始的消息副本
    msgs = list(messages[start:])

    # Step 2：原子化处理工具调用组
    # cleaned：收集清洗后保留的消息；i：当前扫描指针
    cleaned: list[BaseMessage] = []
    i = 0
    # 用 while 而非 for：因为内层会向前跳跃跳过已收集的 ToolMessages
    while i < len(msgs):
        msg = msgs[i]  # 当前消息

        if isinstance(msg, ToolMessage):
            # 孤立 ToolMessage（没有被前面 AIMessage 分支预先收集）→ 直接丢弃，指针后移
            i += 1

        elif isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
            # 该 AIMessage 要求调用工具：收集它期望的所有 tool_call_id
            # msg.tool_calls 形如 [{"id": "...", "name": "...", "args": {...}}, ...]
            expected_ids: set[str] = {tc["id"] for tc in msg.tool_calls}

            # 向前看：收集紧跟其后的连续 ToolMessages（工具返回结果）
            j = i + 1
            following_tool_msgs: list[ToolMessage] = []
            # 连续的 ToolMessage 都属于本组（一旦遇到非 ToolMessage 就停）
            while j < len(msgs) and isinstance(msgs[j], ToolMessage):
                following_tool_msgs.append(msgs[j])
                j += 1

            # 提取这些 ToolMessage 实际满足的 tool_call_id 集合
            satisfied_ids = {
                tm.tool_call_id
                for tm in following_tool_msgs
                if hasattr(tm, "tool_call_id")
            }
            #用expected_ids存储所有的aimessage中的tool的id
            #用satisfied_ids存储实际满足的tool的id，也就是有tool消息的id
            #只有同时在二者均存在的id，说明该id是完整的格式的tool信息，我们保留
            if expected_ids == satisfied_ids:
                # 完整的工具调用组 → 整组保留，按原顺序（AIMessage 在前，ToolMessages 在后）
                cleaned.append(msg)
                cleaned.extend(following_tool_msgs)
            # else：不完整 → 整组丢弃（AIMessage + 所有部分 ToolMessages 全不加入 cleaned）

            i = j  # 指针跳过已处理的 ToolMessages（无论保留还是丢弃）

        else:
            # 普通消息（HumanMessage / 无 tool_calls 的 AIMessage / SystemMessage）→ 直接保留
            cleaned.append(msg)
            i += 1

    # Step 3：移除末尾仍然悬空的 AIMessage(tool_calls)
    # 理论上 Step 2 已处理，这里是双保险：末尾若有 tool_calls 却无后续 ToolMessage，弹掉
    while cleaned and getattr(cleaned[-1], "tool_calls", None):
        cleaned.pop()  # 丢弃末尾悬空的 AIMessage(tool_calls)

    # 返回结构合法的消息列表给 chat_node 使用
    return cleaned


# ── 状态定义 ──────────────────────────────────────────────────────────────────

class ChatState(TypedDict):
    """对话图的状态容器（LangGraph 在节点间传递的"共享黑板"）。

    每个字段由不同节点写入，context_processor 汇总后供 chat_node 使用。
    add_messages reducer：messages 字段的新值会"追加+按 id 去重"而非覆盖。
    """
    # 消息列表（用户/助手/工具消息），add_messages reducer 自动合并
    messages: Annotated[list[BaseMessage], add_messages]
    # 用户上传文档解析文本（router 注入，chat_node 通过 system prompt 使用）
    doc_context: Optional[str]
    # RAG 检索片段（rag_node 写入，context_processor 消费）
    rag_context: Optional[str]
    # LLM 摘要（memory_node 写入，context_processor 消费）
    summary: Optional[str]
    # mem0 长期记忆检索结果（memory_node 写入，context_processor 消费）
    long_term_memories: Optional[str]
    # Worker 提炼后的单句背景（context_processor 写入，chat_node 通过 system prompt 使用）
    processed_context: Optional[str]
    # 用户 ID（router 注入，memory_node 用于 mem0 检索隔离）
    user_id: Optional[str]


# ── PostgreSQL 连接池单例 ──────────────────────────────────────────────────────

# 进程级连接池单例：避免每次请求新建池，复用 DB 连接
_pg_pool: AsyncConnectionPool | None = None


async def get_pg_pool() -> AsyncConnectionPool:
    """获取（必要时创建）全局 PostgreSQL 异步连接池单例。

    【功能 / 流程定位】
      基础设施层，被 build_graph()、router.py、history_router.py 共享调用。
      build_graph() 用它构造 AsyncPostgresSaver checkpointer + ensure_table；
      router.py 用它写 chat_messages；history_router.py 用它读历史。
      本函数结束后，调用方拿到一个已 open 的连接池，可直接 pool.connection() 取连接。

    【单例思路】
      首次调用时构造 AsyncConnectionPool 并 open；后续直接返回缓存。
      max_size=10 控制最大连接数，防止 DB 连接被打满。

    返回:
        AsyncConnectionPool 实例（已 open，row_factory=dict_row 返回 dict 行）
    """
    # 声明修改全局变量（Python 函数内赋值全局需 global）
    global _pg_pool
    if _pg_pool is None:
        # 拼接 psycopg 连接串 DSN：从 settings 读取 host/port/db/user/password
        dsn = (
            f"host={settings.pg_host} port={settings.pg_port} "
            f"dbname={settings.pg_dbname} user={settings.pg_user} "
            f"password={settings.pg_password}"
        )
        # 创建异步连接池
        _pg_pool = AsyncConnectionPool(
            conninfo=dsn,            # 连接串
            max_size=10,             # 最大连接数
            kwargs={
                # autocommit=True：每条 SQL 自动提交，无需手动 commit（checkpointer/历史表都无需事务）
                "autocommit": True,
                # prepare_threshold=0：禁用 psycnpg 的预备语句缓存阈值，
                # 避免 LangGraph checkpointer 的参数化 SQL 出现"prepared statement 缓存不一致"问题
                "prepare_threshold": 0,
                # row_factory=dict_row：所有查询返回 dict（按列名取值，而非元组下标）
                "row_factory": dict_row,
            },
            open=False,              # 不在构造时自动 open，下面手动 await open()
        )
        # 显式打开连接池（异步，需 await）
        await _pg_pool.open()
    # 返回已就绪的连接池单例
    return _pg_pool


# ── 节点1：记忆检索 + 摘要压缩 ────────────────────────────────────────────────

async def memory_node(state: ChatState) -> dict:
    """节点1：并发执行 mem0 语义检索 + 按需触发 LLM 摘要压缩（与 rag_node 并行）。

    【功能 / 流程定位】
      总体流程 ④。与 ⑤ rag_node 同时被 START 触发并行执行，两者写不同 state 字段。
      本节点结束后，LangGraph 等待 rag_node 也完成后，再进入 ⑥ context_processor。

    【思路 / 代码流程】
      1. 取当前用户问题 + user_id（mem0 按 user 隔离检索）
      2. asyncio.create_task 启动 mem0 检索（不 await，让它后台跑）
      3. 同时判断历史长度是否超阈值：
         - 超 → 计算切割点，对齐到 HumanMessage 边界（防止截断工具调用序列）
         - 调 summarize_old_messages 把旧消息压缩为摘要
         - 生成 RemoveMessage 列表，从 state 删除已压缩的旧消息
      4. await mem0 任务拿结果
      5. 返回 long_term_memories / summary / messages(RemoveMessage 列表)

    参数:
        state: 当前图状态（取 messages、summary、user_id）

    返回:
        dict 更新：long_term_memories（mem0 检索结果）、summary（新摘要）、
        messages（RemoveMessage 列表，触发旧消息删除）
    """
    # perf_counter 起点：测量本节点总耗时
    _t0 = time.perf_counter()
    # 取当前用户问题：messages 最后一条的 content；消息列表空则取空串
    current_query = getattr(state["messages"][-1], "content", "") if state["messages"] else ""
    # user_id：mem0 按 user 隔离；缺失时回退 "anonymous"
    user_id = state.get("user_id") or "anonymous"

    # 全量消息副本；history = 除最后一条（本轮新问题）外的历史
    all_messages = list(state.get("messages", []))
    history = all_messages[:-1]

    # 启动 mem0 语义检索任务（不立即 await，让它与下面的摘要逻辑并发跑）
    # search_memories 在 memory.py：内部 asyncio.to_thread + 5s 超时降级
    mem_task = asyncio.create_task(search_memories(current_query, user_id))

    # 读取已有摘要（增量合并用）；默认空串
    existing_summary = state.get("summary") or ""
    # new_summary：默认等于旧摘要（若不触发压缩则保持不变）
    new_summary = existing_summary
    # 待删除消息列表：摘要后用 RemoveMessage 从 state 移除旧消息
    messages_to_remove: list[RemoveMessage] = []
    # 历史长度超阈值才触发摘要压缩（阈值来自 settings.max_messages_before_summary）
    if len(history) > settings.max_messages_before_summary:
        # 初始切割点：保留最近 keep_recent_messages 条，之前的拿去压缩
        cut = len(history) - settings.keep_recent_messages
        # 向左对齐到 HumanMessage 边界，防止把 AIMessage(tool_calls)/ToolMessage 对拦腰截断：
        # 若 keep 区的第一条消息不是 HumanMessage，说明切点落在一个工具调用序列中间，
        # 需要将切点左移，直到 keep 区以 HumanMessage 开头。
        while cut > 0 and not isinstance(history[cut], HumanMessage):
            cut -= 1
        # to_summarize：将被压缩的旧消息区间
        to_summarize = history[:cut]
        if to_summarize:
            # 调 memory.py::summarize_old_messages 把旧消息压缩为摘要（含增量合并）
            new_summary = await summarize_old_messages(to_summarize, existing_summary)
            # 摘要生成后从 state 里删除已压缩的旧消息，防止 messages 无限增长导致
            # Worker LLM token 超限，这是 LangGraph 官方推荐的 "summary + RemoveMessage" 模式
            # RemoveMessage(id=...)：LangGraph reducer 收到后会从 messages 删除对应 id 的消息
            messages_to_remove = [
                RemoveMessage(id=m.id) for m in to_summarize if getattr(m, "id", None)
            ]

    # 等待 mem0 检索任务完成（此时摘要逻辑已并行跑完或同时完成）
    long_term_memories = await mem_task

    # 计算并打印本节点耗时（ms）
    elapsed = int((time.perf_counter() - _t0) * 1000)
    print(f"[TIMER] memory_node={elapsed}ms (mem0+summary)", flush=True)

    # 返回状态更新：long_term_memories 给 context_processor；summary 持久化到 state；
    # messages=RemoveMessage 列表触发 add_messages reducer 删除旧消息
    return {
        "long_term_memories": long_term_memories,
        "summary": new_summary,
        "messages": messages_to_remove,
    }


# ── 节点2：Adaptive RAG 路由器 + 知识库检索 ──────────────────────────────────
#
# ★ 扩展说明：新增 RAG 文件时，只需更新 _RAG_CORPUS_DESC 的描述内容即可。
#   路由逻辑、图结构、检索流程均无需改动。
#
# _RAG_CORPUS_DESC：描述当前知识库涵盖的领域，供路由 LLM 判断"问题是否归属知识库"。
# 新增 RAG 文档领域时，只需在此常量补充描述，路由器即可识别新领域。
_RAG_CORPUS_DESC = (
    "当前知识库包含以下领域的专属文档：\n"
    "  • 平台规则与内容审核条款（ShillGuard 平台用户行为规范、违规判定标准）\n"
    "  • 相关法律法规（网络暴力、隐私侵权、造谣传谣、网络安全等国家法规）\n"
    "如未来新增其他领域文档，请在此补充对应描述。"
)

# _RAG_ROUTER_SYSTEM：RAG 路由器的 system prompt，要求 LLM 只输出 yes/no。
# 内嵌 _RAG_CORPUS_DESC 让路由器知道知识库覆盖范围。
_RAG_ROUTER_SYSTEM = (
    "你是查询路由器，判断用户问题是否需要从【专属知识库】中检索信息才能准确回答。\n"
    "\n"
    f"{_RAG_CORPUS_DESC}\n"
    "\n"
    "判断标准：\n"
    "  需要（yes）：问题明确涉及知识库所含领域，仅靠通用知识无法可靠回答\n"
    "  不需要（no）：闲聊、问候、常识、数学计算、日期时间、天气预报、"
    "编程通识、用户个人信息（姓名/年龄）等与知识库无关的问题\n"
    "\n"
    "只输出 yes 或 no，不要任何其他内容。"
)

# 匹配 LLM 输出中的 yes（兼容思考链前缀：thinking 模型可能在 yes 前输出 <think>...</think>）
# \byes\b：单词边界匹配 yes，IGNORECASE 兼容 Yes/YES
_RAG_YES_RE = re.compile(r'\byes\b', re.IGNORECASE)


async def _should_retrieve(query: str) -> bool:
    """Adaptive Retrieval：判断当前查询是否需要 RAG 检索。

    【功能 / 流程定位】
      属于 ⑤ rag_node 的内部子步骤，在真正检索前先做轻量判断。
      本函数返回后，调用方 rag_node 据 True/False 决定是否调 retrieve()。

    【思路】
      用 Worker LLM（get_expander_llm，便宜快）+ yes/no 文本输出判断，
      完全兼容 thinking 模型（无 function_calling 也能用）。
      超时 5s 或异常 → 保守降级为 True（执行检索），避免遗漏知识库相关问题。

    参数:
        query: 用户当前问题文本

    返回:
        True=需要检索；False=跳过检索
    """
    # 空查询直接跳过检索（无需调 LLM）
    if not query.strip():
        return False
    try:
        # 计时起点
        t = time.perf_counter()
        # 取轻量 Worker LLM（路由判断不需要大模型）
        llm = get_expander_llm()
        # asyncio.wait_for 包裹 achaininvoke，设 5s 超时：
        # ainvoke 是 LangChain 异步调用 LLM 的统一入口
        # 传入 [SystemMessage(路由规则), HumanMessage(用户问题)] 两条消息
        resp = await asyncio.wait_for(
            llm.ainvoke([
                SystemMessage(content=_RAG_ROUTER_SYSTEM),
                HumanMessage(content=f"问题：{query}"),
            ]),
            timeout=5.0,
        )
        # resp.content 可能是 str 或 list（多模态），统一转 str 再正则匹配
        content = resp.content if isinstance(resp.content, str) else str(resp.content)
        # 用预编译正则搜索 yes：找到=需要检索
        need = bool(_RAG_YES_RE.search(content))
        # 耗时（ms）
        elapsed = int((time.perf_counter() - t) * 1000)
        # 决策文案用于日志
        decision = "需要RAG" if need else "跳过RAG"
        # 打印路由结果（含耗时、决策、原始输出前30字便于排查）
        print(f"[RAGRouter] {elapsed}ms → {decision} | raw='{content.strip()[:30]}'", flush=True)
        return need
    except asyncio.TimeoutError:
        # 超时：保守策略执行检索，不漏答
        print("[RAGRouter] 路由判断超时（5s），保守策略：执行检索", flush=True)
        return True
    except Exception as e:
        # 其他异常：保守策略执行检索
        print(f"[RAGRouter] 路由判断失败，保守策略：执行检索: {e}", flush=True)
        return True


async def rag_node(state: ChatState) -> dict:
    """节点2：Adaptive RAG - 先路由判断，再按需执行混合检索+重排序。

    【功能 / 流程定位】
      总体流程 ⑤。与 ④ memory_node 并行启动；本节点结束后等 memory 也完成 → ⑥ context_processor。

    【思路 / 代码流程】
      1. 取用户问题
      2. _should_retrieve 判断是否需要检索
         - 不需要 → 直接返回空 rag_context（跳过 embedding/BM25/rerank，省 2-4s）
         - 需要 → retrieve() 混合检索，拼接片段返回
      无关查询（闲聊/日期/常识等）在路由阶段直接返回空。

    参数:
        state: 当前图状态（取 messages 末条作为查询）

    返回:
        {"rag_context": "拼接的检索片段" 或 ""}
    """
    # 计时起点
    _t0 = time.perf_counter()
    # 取用户当前问题
    query = getattr(state["messages"][-1], "content", "")

    # 路由判断：不需要检索 → 返回空 rag_context
    if not await _should_retrieve(query):
        elapsed = int((time.perf_counter() - _t0) * 1000)
        print(f"[TIMER] rag_node={elapsed}ms (router: skip)", flush=True)
        # 空 rag_context：context_processor 会跳过 RAG 部分
        return {"rag_context": ""}

    # 需要检索：调 app/rag/retriever.py::retrieve（ES BM25 + pgvector + RRF + rerank）
    # 返回检索片段字符串列表
    snippets = await retrieve(query)
    # 耗时 + 命中片段数
    elapsed = int((time.perf_counter() - _t0) * 1000)
    print(f"[TIMER] rag_node={elapsed}ms ({len(snippets)} chunks, router: retrieve)", flush=True)
    # 用双换行拼接所有片段为一个字符串，写入 rag_context
    return {"rag_context": "\n\n".join(snippets)}


# ── 节点3：Context Processor（Worker LLM + prompt 内嵌 JSON）────────────────────
#
# 不使用 with_structured_output（function_calling / json_mode），
# 原因：thinking 系列模型（DeepSeek-R1 / deepseek-v4-flash 等）两种方式都不支持，均报 400。
# 改为：在 prompt 里直接给出 JSON schema 示例，手动正则提取响应中的 JSON。
# 这是对所有模型（thinking / non-thinking）都兼容的工业标准做法。

# _WORKER_SYSTEM：Worker LLM 的 system prompt，要求只返回指定格式的 JSON。
# 规则：只提取与当前问题直接相关的单句事实，找不到则 has_relevant_context=false。
_WORKER_SYSTEM = (
    "你是信息提炼助手。根据【用户当前问题】，从背景信息中提取唯一一句与问题直接相关的事实。\n"
    "规则：\n"
    "1. 用户问年龄，只提取年龄；问名字，只提取名字；问天气，只提取天气。\n"
    "2. 严禁包含与当前问题无关的信息（如问年龄时不写台风、不写技术栈）。\n"
    "3. background_fact 必须是单句，无列表符号。\n"
    "4. 找不到相关信息时，has_relevant_context 为 false，background_fact 留空。\n"
    "\n"
    "必须只返回如下格式的 JSON，不要任何额外说明：\n"
    '{"has_relevant_context": true, "background_fact": "单句事实"}\n'
    "或\n"
    '{"has_relevant_context": false, "background_fact": ""}'
)

# 从模型响应中提取第一个完整 JSON 对象（兼容 thinking 模型输出前缀 <think>...</think>）
# [^{}]*：JSON 内部不含嵌套大括号；DOTALL 让 . 匹配换行
_JSON_RE = re.compile(r'\{[^{}]*"has_relevant_context"[^{}]*\}', re.DOTALL)


async def context_processor_node(state: ChatState) -> dict:
    """节点3：Worker LLM 提炼背景，Main LLM 只看干净结论（架构隔离核心）。

    【功能 / 流程定位】
      总体流程 ⑥。在 memory/rag 并行完成后运行，汇总全部原始背景，
      提炼为单句 processed_context。本节点结束后 → ⑦ chat_node。

    【架构隔离思路（Context Engineering - Isolate）】
      Worker LLM 读取 memories/summary/rag/user_said 全部原始背景，
      提炼为单句 background_fact 写入 processed_context。
      chat_node (Main LLM) 只看 processed_context，物理上看不到原文 → 无法复读。
      这是防复读的根本解法，替代事后 regex 清洗。

    【代码流程】
      1. 取用户问题 + 四类背景（memories/summary/rag/user_said）
      2. 若无任何外部背景（仅 user_said）→ 跳过 Worker LLM 省 ~1.5s，返回空
      3. 拼接背景 → Worker LLM（prompt 内嵌 JSON schema）
      4. 正则提取响应中的 JSON → WorkerContextResult.to_processed_context()
      5. 异常降级为空

    参数:
        state: 含 messages / long_term_memories / summary / rag_context

    返回:
        {"processed_context": "单句背景事实" 或 ""}
    """
    # 取用户当前问题
    question = getattr(state["messages"][-1], "content", "") if state["messages"] else ""

    # 读取四类背景，None 转空串
    memories = state.get("long_term_memories") or ""
    summary = state.get("summary") or ""
    rag = state.get("rag_context") or ""
    # format_user_said_history：提取历史用户发言（不含助手回复，排除本轮新问题）
    user_said = format_user_said_history(list(state.get("messages", [])))

    # 只有 user_said 没有任何外部背景时，跳过 Worker LLM（节省 ~1.5s）：
    # user_said 仅是当前窗口的发言记录，Main LLM 本身可直接访问消息历史，
    # 不需要 Worker 再去提炼，只有 memories/summary/rag 这类 Main LLM 看不到
    # 的"外部背景"才值得专门提炼。
    if not any([memories, summary, rag]):
        if user_said:
            print("[ContextProcessor] 跳过 Worker LLM（仅 user_said，无外部背景）", flush=True)
        # 无外部背景 → processed_context 留空，chat_node 不注入背景
        return {"processed_context": ""}

    # 按类别拼接原始背景，每类加标签便于 Worker LLM 区分来源
    parts = []
    if user_said:
        parts.append(f"[用户此前发言]\n{user_said}")
    if memories:
        parts.append(f"[长期记忆]\n{memories}")
    if summary:
        parts.append(f"[历史要点]\n{summary}")
    if rag:
        parts.append(f"[平台知识]\n{rag}")
    # 双换行合并为一段原始背景文本
    raw_context = "\n\n".join(parts)

    # 构造 Worker LLM 的 user message：问题 + 背景信息 + 输出要求
    user_msg = (
        f"用户问题：{question}\n\n"
        f"背景信息：\n{raw_context}\n\n"
        "请按上述 JSON 格式返回：是否与问题相关，以及一句关键事实。"
    )

    try:
        # 计时起点
        t = time.perf_counter()
        # 取轻量 Worker LLM（提炼用，便宜快）
        llm = get_expander_llm()
        # 调 Worker LLM：SystemMessage(规则+JSON schema) + HumanMessage(问题+背景)
        resp = await llm.ainvoke([
            SystemMessage(content=_WORKER_SYSTEM),
            HumanMessage(content=user_msg),
        ])
        # 耗时（ms）
        elapsed = int((time.perf_counter() - t) * 1000)

        # 从响应文本中提取 JSON（thinking 模型会在 JSON 前后输出思考链）
        # resp.content 可能是 str 或 list，统一转 str
        content = resp.content if isinstance(resp.content, str) else str(resp.content)
        # 用预编译正则搜索第一个含 has_relevant_context 的 JSON 片段
        match = _JSON_RE.search(content)
        # 找到则取匹配片段，否则取整段 strip 后的内容（兜底）
        raw_json = match.group() if match else content.strip()
        # json.loads：把 JSON 字符串解析为 dict
        data = json.loads(raw_json)
        # 用 Pydantic 模型校验 + 防御性清洗（sanitize_fact 校验器）
        result_obj = WorkerContextResult(**data)
        # to_processed_context：has_relevant_context 为真且非空 → 返回 background_fact，否则空串
        result = result_obj.to_processed_context()

        # 打印提炼日志：原始背景字数 → 是否有相关背景 → 提炼结果 → 耗时
        print(
            f"[ContextProcessor] {len(raw_context)}字→"
            f"has_ctx={result_obj.has_relevant_context} "
            f"fact='{result}' ({elapsed}ms)",
            flush=True,
        )
        # 返回提炼后的单句背景给 chat_node
        return {"processed_context": result}

    except Exception as e:
        # 任意异常（LLM 报错/JSON 解析失败/校验失败）→ 降级为空，不影响主对话
        print(f"[ContextProcessor] 提炼失败，降级为空: {e}", flush=True)
        return {"processed_context": ""}


# ── 节点4：Main LLM 推理（只看 processed_context）────────────────────────────

# LLM 并发信号量：限制同时调 Main LLM 的请求数，防止突发流量打爆 LLM API
# 设 2000 为高并发上限，可按 LLM 配额调整
_LLM_SEMAPHORE = asyncio.Semaphore(2000)


async def chat_node(state: ChatState) -> dict:
    """节点4：Main LLM 基于 processed_context 生成回答。

    【功能 / 流程定位】
      总体流程 ⑦。context_processor 完成后运行；这是真正生成用户可见回答的节点。
      本节点结束后 → tools_condition 判断：有 tool_calls → ⑧ tools 节点；无 → END。
      tools 节点执行后会回到本节点循环，直到无 tool_calls。

    【架构隔离下的生成思路】
      Main LLM 只接收 processed_context（单句）+ doc_context（用户上传文档），
      看不到 memories/summary/rag 原文，物理上无法复读。
      无需 regex 清洗；若仍出现复读，说明 Worker 失效，应修 context_processor 而非打补丁。

    【代码流程】
      1. get_llm 取主 LLM，bind_tools 绑定 web_search
      2. build_system_prompt 注入 processed_context + doc_context
      3. 取最近 N 条滑动窗口 + _sanitize_window 清洗
      4. 拼接 SystemMessage + 窗口消息
      5. 信号量限流下 ainvoke 调 LLM
      6. 返回 {"messages": [result]}（result 可能含 tool_calls）

    参数:
        state: 含 messages / processed_context / doc_context

    返回:
        {"messages": [AIMessage]}（add_messages reducer 自动追加）
    """
    # 取主对话 LLM（DeepSeek 等，OpenAI 兼容）
    llm = get_llm()
    # 工具列表：目前仅联网搜索
    tools = [get_web_search_tool()]
    # bind_tools：把工具 schema 绑定到 LLM，使其能在回答中输出 tool_calls
    llm_with_tools = llm.bind_tools(tools)

    # 组装 system prompt：注入 processed_context（Worker 单句背景）+ doc_context（上传文档）
    # build_system_prompt 在 prompts.py：还附 SYSTEM_PROMPT 规则 + 北京时间
    sys = build_system_prompt(
        doc_context=state.get("doc_context") or "",
        processed_context=state.get("processed_context") or "",
    )

    # 全量消息 → 取最近 N 条滑动窗口（Layer1 滑动窗口记忆）
    all_messages = list(state["messages"])
    window_messages = all_messages[-settings.keep_recent_messages:]
    # 清洗窗口：修复被截断的 tool 消息结构，防止 API 400
    window_messages = _sanitize_window(window_messages)

    # 最终发给 LLM 的消息序列：SystemMessage 在前 + 窗口消息在后
    msgs = [SystemMessage(content=sys)] + window_messages

    # 信号量限流：控制同时调 Main LLM 的并发数，超限则在此等待
    async with _LLM_SEMAPHORE:
        # 计时起点
        t = time.perf_counter()
        # 调用 Main LLM 生成回答（可能返回 AIMessage 含 tool_calls）
        result = await llm_with_tools.ainvoke(msgs)
        # 无需 regex 清洗：context_processor_node 已做架构隔离，
        # Main LLM 接收的 processed_context 仅为单句自然语言，
        # 不含 bullet 格式数据，LLM 无原始内容可复读。
        # 若仍出现复读，说明 Worker 失效，应修 context_processor，而非在此打补丁。
        # 耗时（ms）
        elapsed = int((time.perf_counter() - t) * 1000)
        # 打印耗时 + 窗口消息数/总消息数 + 是否有背景
        print(
            f"[TIMER] chat_node={elapsed}ms "
            f"(window={len(window_messages)}/{len(all_messages)} msgs, "
            f"ctx={'有' if state.get('processed_context') else '无'})",
            flush=True,
        )
        # 返回 AIMessage：add_messages reducer 自动追加到 state.messages
        # 若 result 含 tool_calls，tools_condition 会路由到 tools 节点
        return {"messages": [result]}


# ── 图构建 ────────────────────────────────────────────────────────────────────

async def build_graph():
    """构建并编译对话图（5节点 + PostgreSQL 持久化）。

    【功能 / 流程定位】
      总体流程 ③。在应用启动 / 首次请求时由 get_graph() 调用一次，编译后单例缓存。
      本函数结束后，调用方拿到一个可执行的 CompiledGraph，可 astream_events 驱动。

    【图结构】
      START → memory ∥ rag → context_processor → chat
              chat --tools_condition--> tools → chat（循环） / END

    返回:
        CompiledGraph（已挂载 AsyncPostgresSaver checkpointer）
    """
    # 创建以 ChatState 为状态容器的状态图
    g = StateGraph(ChatState)
    # 注册 5 个节点：节点名 → 异步函数
    g.add_node("memory", memory_node)                      # 节点1 记忆
    g.add_node("rag", rag_node)                            # 节点2 RAG
    g.add_node("context_processor", context_processor_node)  # 节点3 Worker 提炼
    g.add_node("chat", chat_node)                          # 节点4 Main LLM

    # 工具节点：ToolNode 包装工具列表，自动执行 LLM 的 tool_calls 并返回 ToolMessage
    tools = [get_web_search_tool()]
    tool_node = ToolNode(tools)
    g.add_node("tools", tool_node)                         # 节点5 工具执行

    # ── 连边 ──
    # memory_node 与 rag_node 并行：两者写入不同 state 字段，互不依赖。
    # context_processor_node 会等两者全部完成后再运行（LangGraph fan-in 语义）。
    g.add_edge(START, "memory")              # START 同时触发 memory
    g.add_edge(START, "rag")                 # START 同时触发 rag（并行）
    g.add_edge("memory", "context_processor")  # memory 完成 → context_processor
    g.add_edge("rag", "context_processor")   # rag 完成 → context_processor（fan-in 等齐）
    g.add_edge("context_processor", "chat")  # 提炼完成 → Main LLM
    # 条件边：tools_condition 检查 chat 输出是否有 tool_calls
    #   有 → 路由到 "tools"；无 → 路由到 END
    g.add_conditional_edges("chat", tools_condition)
    g.add_edge("tools", "chat")              # 工具执行完 → 回 chat（循环直到无 tool_calls）

    # 取 PostgreSQL 连接池单例
    pool = await get_pg_pool()
    # 用连接池构造异步 PostgreSQL checkpointer（持久化 LLM 工作记忆，按 thread_id 区分会话）
    checkpointer = AsyncPostgresSaver(pool)
    # setup()：checkpointer 首次使用前建表（checkpoints/writes 等，幂等）
    await checkpointer.setup()
    # 初始化双轨存储：UI 历史表 chat_messages（与 checkpointer 严格分离）
    # ensure_table 在 history_store.py：建表 + 索引，幂等
    await ensure_table(pool)

    # 编译图并挂载 checkpointer，返回可执行 CompiledGraph
    return g.compile(checkpointer=checkpointer)


# 编译后图的单例缓存：避免每次请求重建图
_graph_instance = None


async def get_graph():
    """获取（必要时构建）编译后的对话图单例。

    【功能 / 流程定位】
      总体流程 ③ 的对外入口。router.py::chat() 每次请求调本函数拿图实例。
      本函数结束后，调用方拿到 CompiledGraph，可直接 astream_events 驱动执行。

    【单例思路】
      首次调用 await build_graph() 编译并缓存；后续直接返回缓存实例。
      图编译开销大（建表、连池），全程只做一次。

    返回:
        CompiledGraph 单例
    """
    # 声明修改全局变量
    global _graph_instance
    if _graph_instance is None:
        # 首次：构建并编译图
        _graph_instance = await build_graph()
    # 返回缓存的单例图
    return _graph_instance
