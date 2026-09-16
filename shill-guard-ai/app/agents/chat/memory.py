"""对话 Agent 的三层记忆管理模块（Chat Agent 的记忆子系统）。

============================================================================
本文件对应总体流程的哪一部分
============================================================================
对应 __init__.py 总体流程编号 ⑨（被 ④ memory_node 与 ② event_stream 调用）：
  - search_memories()         —— Layer3 mem0 检索：被 graph.py::memory_node 调用
  - add_memories_background() —— Layer3 mem0 写入：被 router.py::event_stream 调用
  - summarize_old_messages()  —— Layer2 LLM 摘要压缩：被 graph.py::memory_node 调用
  - format_user_said_history()—— 提取用户历史发言：被 graph.py::context_processor_node 调用
  - get_mem0() / _build_mem0_config() —— mem0 客户端单例与配置

调用关系：本文件不主动驱动流程，是被 graph.py / router.py 调用的"记忆工具箱"。
执行入口：上层节点在需要时调用对应函数；本文件无独立运行入口。

============================================================================
【三层架构】
  Layer 1 - 滑动窗口：在 chat_node 里直接截取 messages[-keep_recent_messages:]，
            保证 LLM 只看最近 N 条原文，防止 context 溢出。
            （不在本文件实现，在 graph.py chat_node 里控制）

  Layer 2 - LLM 摘要压缩：当历史消息超过阈值，调 LLM 把旧消息压缩为摘要。
            摘要写入独立 ChatState.summary 字段（不覆盖 messages），
            符合 LangGraph 官方"summary key 与 messages 分离"的最佳实践。
            摘要同时包含用户发言和助手回复（助手回复现在干净，无 bullet 复读）。

  Layer 3 - mem0 跨会话长期记忆：从完整对话对（user + assistant）中提取关键事实，
            写入前经 OWASP Agent Memory Guard (ASI06) 校验，防止 prompt injection
            和自强化循环污染记忆库。
            （search_memories / add_memories_background 函数）

【mem0 向量后端】
  使用 PostgreSQL pgvector（同一台 PG 实例，独立表 shillguard_mem0），
  支持向量语义检索 + BM25 混合检索（Hybrid Search），
  比 ChromaDB 后端召回质量更高，且减少 ChromaDB 依赖。
  embedding_model_dims=1024 对应 text-embedding-v3 实测输出维度。

【错误策略】
  mem0 / AMG 操作全部 try/except 静默降级：记忆失败不影响主对话流程。
"""
# asyncio：to_thread（把同步 mem0 调用丢到线程池）、wait_for（超时控制）
import asyncio
# Optional：类型注解
from typing import Optional

# BaseMessage/HumanMessage/AIMessage：消息类型判断；SystemMessage：摘要 LLM 的系统提示
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_core.messages import SystemMessage

# settings：全局配置（mem0 开关、检索条数、LLM/Embedding/PG 连接参数）
from app.config import settings
# get_llm：摘要用的主 LLM
from app.llm import get_llm

# ── OWASP Agent Memory Guard (ASI06) ────────────────────────────────────────
# 尝试导入 agent_memory_guard（记忆安全守卫，防 prompt injection 污染记忆库）
# 第三方包未安装时静默降级：_AMG_AVAILABLE=False，写入时不做校验
try:
    from agent_memory_guard import MemoryGuard, Policy, PolicyViolation
    # strict 策略：严格模式，检测到不安全内容抛 PolicyViolation
    _amg_guard = MemoryGuard(policy=Policy.strict())
    _AMG_AVAILABLE = True
except ImportError:
    _AMG_AVAILABLE = False
    _amg_guard = None

# ── mem0 客户端单例 ──────────────────────────────────────────────────────────
# mem0 实例缓存：避免每次请求重新初始化（初始化会建 pgvector 表/连 LLM）
_mem0_instance = None


def _build_mem0_config() -> dict:
    """构造 mem0 初始化配置，复用项目已有的 LLM、Embedding 和 PostgreSQL 配置。

    【功能 / 流程定位】
      属于 mem0 单例初始化的子步骤，被 get_mem0() 首次调用时使用。
      本函数结束后，调用方 get_mem0() 拿到配置 dict 传给 Memory.from_config。
      无"下一个函数"概念，纯配置工厂。

    【思路】
      向量后端使用 pgvector（PostgreSQL 扩展），相比 ChromaDB：
        - 支持 Hybrid Search（向量 + BM25），记忆召回更准确
        - 与 LangGraph checkpointer 共用同一 PG 实例，减少外部依赖
        - embedding_model_dims=1024：text-embedding-v3 实测输出维度

    返回:
        mem0 配置 dict（llm / embedder / vector_store 三段）
    """
    # 返回 mem0 期望的三段式配置 dict
    return {
        # LLM 段：mem0 内置用此 LLM 从对话中提取结构化事实
        "llm": {
            "provider": "openai",  # 用 OpenAI 兼容协议（可对接 DeepSeek/Qwen）
            "config": {
                "model": settings.llm_model,             # 复用项目主 LLM 模型名
                "api_key": settings.llm_api_key,         # 复用项目 LLM key
                # openai_base_url：mem0 识别的字段名（指向 DeepSeek/Qwen 等 OpenAI 兼容端点）
                "openai_base_url": settings.llm_base_url or "https://api.openai.com/v1",
                "temperature": 0.1,                      # 低温度，提取事实要稳定
            },
        },
        # Embedder 段：把记忆文本向量化存入 pgvector
        "embedder": {
            "provider": "openai",  # OpenAI 兼容 embedding 协议
            "config": {
                "model": settings.embedding_model,       # text-embedding-v3
                "api_key": settings.embed_api_key,       # embedding key
                "openai_base_url": settings.embed_base_url,  # embedding 端点
            },
        },
        # 向量库段：用 pgvector 后端（与 checkpointer 同一台 PG，独立 collection）
        "vector_store": {
            "provider": "pgvector",
            "config": {
                "host": settings.pg_host,
                "port": settings.pg_port,
                "dbname": settings.pg_dbname,
                "user": settings.pg_user,
                "password": settings.pg_password,
                "collection_name": "shillguard_mem0",    # 独立 collection，不与 checkpointer 冲突
                # text-embedding-v3 实测输出维度（diag_pgvector.py 检测结果）
                "embedding_model_dims": 1024,
            },
        },
    }


def get_mem0():
    """获取 mem0 Memory 单例（懒加载，首次调用时初始化）。

    【功能 / 流程定位】
      基础设施层，被 search_memories / add_memories_background 调用取 mem0 客户端。
      本函数结束后，调用方拿到 Memory 实例，可调 .search() / .add()。

    【思路】
      延迟导入 mem0（`from mem0 import Memory`），避免应用启动时强依赖 mem0 包。
      首次调用 Memory.from_config(配置) 初始化并缓存；后续直接返回。

    返回:
        mem0.Memory 实例单例
    """
    # 声明修改全局单例
    global _mem0_instance
    if _mem0_instance is None:
        # 延迟导入：仅在真正用到 mem0 时才 import，避免启动期强依赖
        from mem0 import Memory
        # from_config：按配置 dict 构造 Memory 实例（内部建 pgvector 表/连 LLM/Embedder）
        _mem0_instance = Memory.from_config(_build_mem0_config())
    # 返回缓存的单例
    return _mem0_instance


# ── Layer 3：mem0 跨会话长期记忆 ────────────────────────────────────────────

async def search_memories(query: str, user_id: str) -> str:
    """语义检索该用户的长期记忆，返回格式化字符串（注入 Worker 提炼）。

    【功能 / 流程定位】
      Layer3 检索，被 graph.py::memory_node 调用，结果写入 state.long_term_memories。
      本函数结束后，调用方 memory_node 把返回值作为 long_term_memories 传给 context_processor。

    【思路 / 代码流程】
      1. mem0 关闭或 query 空 → 直接返回 ""
      2. mem0.search 是同步 API → asyncio.to_thread 丢线程池异步化
      3. wait_for 5s 超时：mem0 内部调 embedding/LLM，网络抖动会阻塞 22s+，超时降级空
      4. 兼容 mem0 新旧版返回字段（memory/text/data）拼接为多行字符串
      5. 全程 try/except 静默降级，记忆失败不拖慢主对话

    参数:
        query:   检索词（一般用当前用户问题做语义检索）
        user_id: 用户 ID（mem0 按 user 隔离记忆）

    返回:
        格式化的记忆文本（多行，每行一条记忆）；无记忆/失败时返回 ""
    """
    # 全局开关：mem0 未启用直接返回空
    if not settings.mem0_enabled:
        return ""
    try:
        # 取 mem0 单例
        mem0 = get_mem0()
        # mem0 新版 API：user_id 必须通过 filters 传入，不能作为顶级关键字参数
        # asyncio.wait_for 超时 5s：mem0 内部调 embedding/LLM API，网络抖动时
        # 会阻塞 22s+；超时后立刻降级为空，不拖慢整条链路。
        # asyncio.to_thread：把同步 mem0.search 丢到线程池异步执行
        result = await asyncio.wait_for(
            asyncio.to_thread(
                mem0.search,                       # mem0 同步检索方法
                query,                             # 检索词
                filters={"user_id": user_id},      # 按 user_id 过滤记忆
                limit=settings.mem0_search_limit,  # 返回条数上限
            ),
            timeout=5.0,                           # 5s 超时
        )
        # mem0 返回可能是 dict（新版 {"results": [...]}）或 list（旧版）；统一取列表
        items = result.get("results", []) if isinstance(result, dict) else (result or [])
        # 无结果直接返回空
        if not items:
            return ""
        # mem0 新版本把记忆文本存在 metadata["data"] 里（ChromaDB documents 字段为 None）
        # 兼容旧版（memory / text 字段）和新版（data 字段）
        lines = []
        for m in items:
            # 按优先级取记忆文本：memory → text → data → ""
            text = (
                m.get("memory")
                or m.get("text")
                or m.get("data")
                or ""
            )
            if text:
                lines.append(str(text))
        # 多行拼接返回（每条记忆一行）
        return "\n".join(lines)
    except asyncio.TimeoutError:
        # 超时降级：打印告警，返回空，不影响主对话
        print("[mem0] 检索记忆超时（5s）已跳过", flush=True)
        return ""
    except Exception as e:
        # 其他异常降级：返回空
        print(f"[mem0] 检索记忆失败（已跳过）: {e}", flush=True)
        return ""


async def add_memories_background(
    user_message: str,
    user_id: str,
    assistant_message: str = "",
) -> None:
    """从完整对话对（user + assistant）提取记忆存入 mem0（后台任务，不阻塞 SSE 流）。

    【功能 / 流程定位】
      Layer3 写入，被 router.py::event_stream 的 finally 块通过 asyncio.create_task 调用。
      本函数结束后无返回值；mem0 记忆库已更新（或失败静默跳过）。
      无"下一个函数"——这是一次请求记忆链路的终点。

    【工业标准做法】
      - 传入 (user, assistant) 消息对，让 mem0 内置 LLM 从完整对话中提取事实，
        比只传用户发言的事实覆盖率更高（符合 Mem0 arXiv:2504.19413 架构设计）。
      - 写入前经 OWASP Agent Memory Guard 校验（ASI06 Memory Poisoning 防御）：
        检测 prompt injection、自强化循环等攻击，阻止后静默跳过。
      - 助手回复现在干净（context_processor 架构隔离保证无 bullet 复读），
        可安全写入 mem0。

    参数:
        user_message:      本轮用户发言
        user_id:           用户 ID（mem0 按 user 隔离）
        assistant_message: 本轮助手回复（可选）

    返回:
        None（失败静默降级）
    """
    # mem0 未启用 → 直接返回
    if not settings.mem0_enabled:
        return
    # 用户消息为空 → 没有可提取的事实，直接返回
    if not user_message or not user_message.strip():
        return

    # AMG 写入前校验（OWASP ASI06）
    # 仅当 agent_memory_guard 包可用且守卫实例存在时校验
    if _AMG_AVAILABLE and _amg_guard is not None:
        try:
            # 校验用户发言：检测 prompt injection / 不安全内容，违规则抛异常
            _amg_guard.write("conversation.user", user_message)
            # 校验助手回复（若存在）
            if assistant_message:
                _amg_guard.write("conversation.assistant", assistant_message)
        except Exception as guard_err:
            # 校验未通过：打印告警并放弃写入，避免污染记忆库
            print(f"[AMG] 记忆写入被阻止（检测到不安全内容）: {guard_err}", flush=True)
            return

    try:
        # 取 mem0 单例
        mem0 = get_mem0()
        # 传入完整对话对，mem0 内置 LLM 从双方发言提取结构化事实
        # 构造 OpenAI 消息格式列表
        messages = [{"role": "user", "content": user_message.strip()}]
        # 助手回复非空才加入对话对
        if assistant_message and assistant_message.strip():
            messages.append({"role": "assistant", "content": assistant_message.strip()})
        # mem0.add 是同步 API → asyncio.to_thread 丢线程池异步执行
        # user_id：按用户隔离存储记忆
        await asyncio.to_thread(mem0.add, messages, user_id=user_id)
        # 打印写入完成日志
        print(f"[mem0] 记忆更新完成(对话对): user_id={user_id}", flush=True)
    except Exception as e:
        # 写入失败静默降级，不影响主对话
        print(f"[mem0] 存储记忆失败（已跳过）: {e}")


# ── Layer 2：LLM 摘要压缩 ─────────────────────────────────────────────────────

# _SUMMARY_SYSTEM：摘要 LLM 的 system prompt。
# 规则：记录用户个人信息 + 核心话题 + 助手关键结论，禁止写入实时数据（天气/股价），
# 输出最多6条 bullet，每条 ≤20 字，已有摘要则合并去重。
_SUMMARY_SYSTEM = (
    "你是对话摘要助手。提炼对话的关键信息，供后续轮次的 LLM 理解上下文。\n"
    "规则：\n"
    "1. 记录用户明确说出的个人信息（姓名、年龄、职业、偏好等）。\n"
    "2. 记录用户问过的核心话题（不超过3个）。\n"
    "3. 记录助手给出的关键结论（不超过2条，仅限事实性结论，不含搜索结果摘要）。\n"
    "4. 严禁写入联网搜索内容、天气实况、股价等实时数据。\n"
    "5. 输出最多6条，每条以'• '开头，20字以内。\n"
    "6. 如已有摘要，合并去重后输出完整列表。"
)


def format_user_said_history(messages: list[BaseMessage]) -> str:
    """提取用户历史发言（不含助手回复），供 Worker 提炼个人事实。

    【功能 / 流程定位】
      被 graph.py::context_processor_node 调用，产出 user_said 背景。
      本函数结束后，调用方 context_processor 把返回值作为"[用户此前发言]"拼入背景。

    【思路】
      遍历 messages[:-1]（排除本轮新问题），只取 HumanMessage 且 content 非空，
      拼成多行字符串。不含助手回复（助手回复由 summary 体现）。

    参数:
        messages: 当前全量消息列表

    返回:
        用户历史发言多行字符串；无则空串
    """
    # 收集用户发言行
    lines = []
    # messages[:-1]：排除最后一条（本轮新问题），只看历史
    for m in messages[:-1]:
        # 只取 HumanMessage 且 content 非空
        if isinstance(m, HumanMessage) and m.content:
            lines.append(str(m.content).strip())
    # 多行拼接返回
    return "\n".join(lines)


async def summarize_old_messages(
    messages: list[BaseMessage],
    existing_summary: str = "",
) -> str:
    """用 LLM 将旧消息列表压缩为摘要（含增量合并逻辑）。

    【功能 / 流程定位】
      Layer2 摘要压缩，被 graph.py::memory_node 调用，结果写入 state.summary。
      本函数结束后，调用方 memory_node 把返回值作为新 summary 持久化到 state。

    【思路 / 代码流程】
      符合 LangGraph 官方 "summary key 与 messages 分离" 最佳实践：
        - 摘要写入独立 state["summary"] 字段，messages 本体保持原样
        - 同时压缩用户发言和助手回复，提供完整对话上下文
        - 助手回复现在干净（context_processor 架构隔离无 bullet 复读），可安全压缩
      1. 把消息列表格式化为"用户：.../助手：..."文本（助手回复截断 200 字省 token）
      2. 拼已有摘要 + 新增对话作为 user prompt
      3. 调 LLM 生成新摘要
      4. 异常时保留旧摘要（静默降级）

    参数:
        messages:         待压缩的旧消息列表（HumanMessage / AIMessage）
        existing_summary: 上一轮已有的摘要（首次为空）

    返回:
        新的压缩摘要字符串；失败时返回旧摘要（静默降级）。
    """
    # 无消息可压缩 → 直接返回旧摘要
    if not messages:
        return existing_summary

    # 同时包含用户发言和助手回复（截断助手长回复避免 token 浪费）
    lines = []
    for m in messages:
        # 用户消息：原样取 content
        if isinstance(m, HumanMessage) and m.content:
            lines.append(f"用户：{str(m.content).strip()}")
        # 助手消息：仅取 str 类型 content，截断前 200 字
        elif isinstance(m, AIMessage) and isinstance(m.content, str) and m.content.strip():
            truncated = m.content.strip()[:200]
            lines.append(f"助手：{truncated}")

    # 没有有效内容 → 返回旧摘要
    if not lines:
        return existing_summary

    # 拼接对话文本
    history_text = "\n".join(lines)

    # 构造 user prompt：已有摘要 + 新增对话（增量合并）
    user_prompt = ""
    if existing_summary:
        user_prompt += f"已有摘要：\n{existing_summary}\n\n"
    user_prompt += f"新增对话：\n{history_text}"

    try:
        # 取主 LLM
        llm = get_llm()
        # 调 LLM：SystemMessage(摘要规则) + HumanMessage(已有摘要+新增对话)
        resp = await llm.ainvoke([
            SystemMessage(content=_SUMMARY_SYSTEM),
            HumanMessage(content=user_prompt),
        ])
        # 取生成的摘要文本并 strip
        new_summary = resp.content.strip()
        # 打印压缩日志：原消息数 → 摘要字数
        print(f"[摘要] 压缩 {len(messages)} 条消息 → {len(new_summary)} 字摘要", flush=True)
        return new_summary
    except Exception as e:
        # 压缩失败：保留旧摘要，不丢失已有上下文
        print(f"[摘要] 压缩失败（保留旧摘要）: {e}")
        return existing_summary
