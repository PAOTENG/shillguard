"""审核 Agent 的 LangGraph 状态机（Moderation Agent 举报审核链路的核心引擎）。

============================================================================
本文件对应总体流程的哪一部分
============================================================================
对应 __init__.py 总体流程编号 ③④⑤⑥⑦⑧⑨⑩⑪⑫⑬（举报审核链路1 的图引擎）：
  ③ pre_filter_node()        —— 节点1：T1/T2 级联前置过滤（在 cascade.py，本文件注册）
  ④ route_after_pre_filter() —— 条件路由：级联三态分流
  ⑤ classify_node()          —— 节点2：内容分类（T3 LLM 第一跳）
  ⑥ route_after_classify()   —— 条件路由：normal 跳过检索
  ⑦ retrieve_node()          —— 节点3：三路并行 RAG 检索
  ⑧ crag_filter_node()       —— 节点4：CRAG 质量过滤
  ⑨ judge_node()             —— 节点5：违规判定（T3 LLM 第二跳）
  ⑩ route_after_judge()      —— 条件路由：低分跳过证据
  ⑪ evidence_node()          —— 节点6：证据生成（T3 LLM 第三跳，级联已填则跳过）
  ⑫ citation_verify_node()   —— 节点7：引用溯源校验（在 citation_verifier.py，本文件注册）
  ⑬ action_node()            —— 节点8：处罚决策（纯逻辑）
  build_graph()               —— 构建 8 节点图 + 3 处条件路由

调用关系（谁来调用本文件）：
  - router.py::_run_moderate_task() 通过 build_graph() 拿编译图，graph.ainvoke 驱动。
执行入口：graph 被 ainvoke 驱动后，LangGraph 按边与条件路由调度各节点 → END。

============================================================================
本部分流程与思路
============================================================================
举报审核是一条【8 节点图 + 3 处条件路由 + 4 级短路】的状态机：

  pre_filter ──┬─[clear_violation]─→ evidence → citation_verify → action → END
               ├─[clear_normal]───→ action → END
               └─[ambiguous]──────→ classify ─┬─[normal]──→ action → END
                                              └─[违规]──→ retrieve → crag_filter → judge
                                                                    ├─[score≥0.6]→ evidence → ...
                                                                    └─[score<0.6]→ action → END

核心思路：
  - 级联前置（pre_filter）：用确定性规则/商业 API 先清掉明确违规与明确正常，目标 90%+ 免 LLM。
  - 四级短路：级联 clear_violation/clear_normal、classify normal、judge 低分，每级都能提前结束。
  - T3 三跳 LLM：classify（分类）→ judge（判定+打分）→ evidence（出报告），灰区才走。
  - CRAG 过滤：检索后用小模型过滤低质量 chunk，提升喂给 judge/evidence 的法条信噪比。
  - 引用溯源：evidence 后校验法律引用是否有 RAG 支撑，防幻觉。
  - 无 checkpointer：审核是一次性任务，不需跨请求记忆（与 chat 多轮记忆对比）。

============================================================================
【完整流程（8 节点 + 条件路由）】
  pre_filter(级联) → classify → retrieve → crag_filter → judge → evidence → citation_verify → action → END

【短路优化（项目自定义）】
  - pre_filter 判 clear_violation → 跳过 classify/retrieve/judge，直接 evidence
  - pre_filter 判 clear_normal   → 跳过全部 LLM，直接 action
  - classify 判 normal           → 跳过 retrieve/judge，直接 action
  - judge score < 0.6            → 跳过 evidence，直接 action

【LangGraph 核心 API（官方）】
  StateGraph(StateSchema)  — 定义状态图
  add_node(name, fn)       — 注册节点；fn 签名 (state) -> dict，返回 partial update
  add_edge(from, to)       — 固定边
  add_conditional_edges(from, router_fn, mapping) — 条件边
  set_entry_point(name)    — 入口节点
  compile()                — 编译为 Runnable，可 invoke/ainvoke
  文档: https://langchain-ai.github.io/langgraph/concepts/low_level/

retrieve_node 采用"三路并行检索"策略：
  Q1 原文语义查询：绕开分类错误，直接用内容检索
  Q2 类型模板查询：_TYPE_QUERY_MAP 精准关键词
  Q3 Step-Back 本体约束：轻量 LLM + 固定法律本体，防止 HyDE 漂移
"""

# ── 标准库：异步并发(asyncio) + 类型注解(TypedDict/NotRequired) ──
import asyncio                                  # asyncio.gather：三路检索并行执行
from typing import NotRequired, TypedDict       # TypedDict 定义图状态；NotRequired 标可选字段

# ── LangGraph：状态图构建 ──
from langgraph.graph import StateGraph, END      # StateGraph=状态图容器；END=终止节点

# ── 项目内：级联与溯源节点（本文件注册进图，实现分别在各自模块）──
from app.agents.moderation.cascade import pre_filter_node              # 节点1：T1/T2 级联前置过滤
from app.agents.moderation.citation_verifier import citation_verify_node  # 节点7：法律引用溯源校验

# ── 项目内：LLM / RAG / 工具 ──
from app.llm import get_llm                      # 主 LLM 工厂（classify/judge/evidence 用）
from app.utils import parse_json_from_llm        # 从 LLM 输出健壮提取 JSON（正则兜底）
from app.rag.retriever import retrieve           # 单路混合检索（向量+BM25+RRF+rerank）
from app.rag.query_expander import expand_queries, dedup_and_merge  # 三路 query 生成 + 投票合并
from app.rag.crag_filter import crag_filter      # CRAG 质量过滤（小模型三档打分）
from app.config import settings                  # 配置（阈值等，可在 .env 覆盖）
from app.agents.moderation.prompts import (      # 审核四个 prompt + 举报分类映射
    SYSTEM_PROMPT,                               #   所有 LLM 节点共用的系统角色
    CLASSIFY_PROMPT,                             #   classify_node 分类任务
    JUDGE_PROMPT,                                #   judge_node 判定+打分任务
    EVIDENCE_PROMPT,                             #   evidence_node 证据生成任务
    get_report_category_desc,                    #   举报分类数字→中文
)


# ═══════════════════════════════════════════════════════════════
#  State 定义：图的状态容器，所有节点共享并增量更新这些字段
# ═══════════════════════════════════════════════════════════════

class ModerationState(TypedDict):
    """审核图的全局状态。

    【流程定位】
      被 router.py::_run_moderate_task() 用 initial_state 初始化（输入字段），
      8 个节点依次往里写入各自产物，最后 router 取关键字段包装 ModerateResult。

    【官方机制】LangGraph 把各节点返回的 dict merge 进 state（不是整份替换）。
    【项目约定】字段按写入节点分组，便于追踪数据流。
    【NotRequired】TypedDict 中该键可以不存在（可选观测字段）。
    """

    # ── 输入（moderation/router.py 在 ainvoke 前填充）──
    content_list: list[str]   # Java 传来的被举报帖子/评论列表
    report_category: int      # 举报分类编号，见 prompts.get_report_category_desc

    # ── pre_filter_node / classify_node 写入 ──
    content_type: str         # normal / spam / fraud / cyberbullying / ...
    classify_reason: str      # 分类理由（供 judge 参考）

    # ── retrieve_node 写入 ──
    rag_context: str          # 检索到的法规/规则片段，拼成字符串注入 judge/evidence prompt

    # ── judge_node 写入 ──
    anomaly_score: float      # 异常分数 0~1，决定 action 和是否生成证据
    violated_rules: list[str] # 违反的平台规则
    violated_laws: list[str]  # 违反的法律法规
    judgment: str             # 判定说明

    # ── evidence_node 写入 ──
    evidence_detail: str      # Markdown 格式的完整证据报告

    # ── citation_verify_node 写入 ──
    hallucinated_laws: list[str]  # 未在 rag_context 中找到支撑的法律引用

    # ── action_node 写入 ──
    action: str               # none / manual_review / auto_mute

    # ── pre_filter_node（级联）写入 ──
    tier_verdict: str         # clear_violation / clear_normal / ambiguous
    filter_tier: str          # T1-blacklist / T2-api / T3-llm / ...
    filter_reason: str        # 级联判定原因（可观测性）

    # ── 可选观测字段（NotRequired = TypedDict 中该键可以不存在）──
    api_risk_score: NotRequired[float]      # 易盾/阿里云 API 风险分
    api_primary_label: NotRequired[str]     # API 主标签
    crag_stats: NotRequired[dict]           # CRAG 过滤统计（before/after/correct/ambiguous/incorrect）


# ═══════════════════════════════════════════════════════════════
#  辅助函数
# ═══════════════════════════════════════════════════════════════

def _parse_json_from_llm(text: str) -> dict:
    """从 LLM 输出文本中提取 JSON 字典。

    【功能/流程定位】
      通用辅助，被 classify_node / judge_node 调用（解析 LLM 结构化输出）。
      本函数结束后 → 调用方继续处理解析出的 dict（无固定下游，按调用点走）。

    【思路/代码流程】
      委托 app.utils.parse_json_from_llm，该函数封装"去 markdown 包裹 + 正则兜底
      提取首个 JSON 对象"，兼容 thinking 模型夹带解释文字。
      参数：text —— LLM 原始输出字符串。
      返回：dict —— 解析出的字典（失败返回空 dict，由调用方防御处理）。
    """
    return parse_json_from_llm(text)   # 委托项目通用工具，保证全项目 JSON 提取行为一致


# ═══════════════════════════════════════════════════════════════
#  节点：内容分类（T3 LLM 第一跳）
# ═══════════════════════════════════════════════════════════════

def classify_node(state: ModerationState) -> dict:
    """节点2：LLM 判断内容属于哪种违规类型（仅在 pre_filter 判 ambiguous 时执行）。

    【功能/流程定位】
      对应总体流程 ⑤。T3 LLM 第一跳，读取输入 content_list + report_category，
      用 LLM 判内容属于 13 种 type 哪种，产出 content_type + classify_reason。
      本函数结束后 → 下一个是 route_after_classify（条件路由，normal 跳检索，违规走 retrieve）。

    【思路/代码流程】
      1. 取 content_list 与 report_category，转中文描述。
      2. 编号拼文本，填 CLASSIFY_PROMPT（两占位符）。
      3. get_llm() + SystemMessage + HumanMessage，invoke 同步调用。
      4. _parse_json_from_llm 解析，取 type（默认 normal）+ reason。
      5. 打印分类结果，返回 {content_type, classify_reason}（局部更新 state）。
      【官方】同步节点函数；图用 ainvoke 时 LangGraph 在线程池跑同步节点。
      参数：state —— 当前图状态。
      返回：dict —— 仅含 content_type 与 classify_reason。
    """
    content_list = state["content_list"]                  # 取被举报内容列表
    report_category = state["report_category"]            # 取举报分类编号
    report_category_desc = get_report_category_desc(report_category)  # 转中文（注入 prompt 供参考）

    content_text = "\n".join(f"{i+1}. {c}" for i, c in enumerate(content_list))  # 编号拼文本

    prompt = CLASSIFY_PROMPT.format(                       # 填充 CLASSIFY_PROMPT 两占位符
        content_list=content_text,                         #   编号内容文本
        report_category_desc=report_category_desc,         #   举报分类中文（仅供参考）
    )

    llm = get_llm()                                        # 取主 LLM 实例
    from langchain_core.messages import SystemMessage, HumanMessage  # 局部导入消息类
    msgs = [
        SystemMessage(content=SYSTEM_PROMPT),              #   系统角色：审核员 + 反幻觉约束
        HumanMessage(content=prompt),                      #   本次分类任务
    ]
    # invoke: 【官方 ChatOpenAI】同步调用，阻塞直到返回 AIMessage
    response = llm.invoke(msgs)                            # 同步调 LLM 拿分类结果
    result = _parse_json_from_llm(response.content)        # 解析输出 JSON 为 dict

    content_type = result.get("type", "normal")           # 取类型，未输出默认 normal
    classify_reason = result.get("reason", "")             # 取分类理由

    print(f"[审核] 内容分类: {content_type}, 理由: {classify_reason}")  # 打印可观测

    return {                                               # 局部返回，更新 state 两字段
        "content_type": content_type,
        "classify_reason": classify_reason,
    }


# ═══════════════════════════════════════════════════════════════
#  节点：RAG 检索
# ═══════════════════════════════════════════════════════════════

# 【项目自定义】内容类型 → 检索关键词模板，提升 Q2 查询精准度
# key 与 CLASSIFY_PROMPT 的 13 种 type 对齐，供 retrieve 路由选模板
_TYPE_QUERY_MAP = {
    "spam": "广告引流 站外推广 违规 处罚 平台规则",
    "fraud": "诈骗 虚假营销 虚假投资 违法 刑法 电信网络诈骗",
    "political": "危害国家安全 涉政 违法 信息管理 煽动颠覆",
    "pornography": "色情淫秽 低俗 违规 处罚 法律 未成年人保护",
    "cyberbullying": "网络暴力 侮辱诽谤 人身攻击 寻衅滋事 治安管理处罚法 网络暴力信息治理规定",
    "violence": "威胁恐吓 煽动暴力 人身威胁 寻衅滋事 故意伤害",
    "illegal_sales": "违禁商品 处方药 烟草 违规带货 枪支 毒品 食品安全",
    "gambling": "网络赌博 开设赌场 赌博推广 博彩 治安管理处罚法",
    "drugs": "毒品交易 贩毒 禁毒法 涉毒信息 走私制造毒品",
    "rumor": "造谣传谣 虚假信息 扰乱秩序 违法 深度合成 AI换脸",
    "privacy_violation": "人肉搜索 个人信息 隐私 侵犯公民个人信息罪 个人信息保护法",
    "other_violation": "违规内容 平台规则 处罚",
}


async def retrieve_node(state: ModerationState) -> dict:
    """节点3：三路并行 RAG 检索（async 节点，必须 await graph.ainvoke 调用图）。

    【功能/流程定位】
      对应总体流程 ⑦。读取 classify 给的 content_type + content_list，
      三路并行混合检索法规知识库，产出 rag_context + _raw_chunks（供 CRAG 用）。
      本函数结束后 → 下一个是 crag_filter_node（节点4，质量过滤）。

    【思路/代码流程】
      1. 取 content_type + content_list，按类型选 Q2 模板（_TYPE_QUERY_MAP）。
      2. expand_queries 生成三路 query（Q1 原文 + Q2 模板 + Q3 Step-Back 本体约束）。
      3. asyncio.gather 对每路 query 并行调 retrieve（top_k=10），等全部返回。
      4. dedup_and_merge 投票合并（多路命中排前）。
      5. rag_context 拼前 10 条；同时存 _raw_chunks 供 crag_filter_node 用。
      Q1 — 原文语义：直接用 content_list 文本检索，绕开 classify 偏差
      Q2 — 类型模板：_TYPE_QUERY_MAP[content_type] 精准关键词
      Q3 — Step-Back：轻量 LLM 从 law_taxonomy 本体中选检索词
      dedup_and_merge: 被多路同时命中的 chunk 排名更靠前（投票机制）。
      参数：state —— 当前图状态。
      返回：dict —— 含 rag_context（拼接文本）+ _raw_chunks（原始 chunk 列表）。
    """
    content_type = state["content_type"]                  # 取分类结果（指导 Q2 模板）
    content_list = state["content_list"]                  # 取被举报内容

    type_query = _TYPE_QUERY_MAP.get(content_type, "违规内容 平台规则 法律 处罚")  # 选 Q2 模板，未知类型用通用兜底

    queries = await expand_queries(content_list, content_type, type_query)  # 生成三路 query（最多5条）

    # asyncio.gather: 【官方 Python】并发执行多个 coroutine，全部完成后返回结果列表
    result_lists = await asyncio.gather(*[                # 对每路 query 并行调 retrieve（混合检索）
        retrieve(q, top_k=10) for q in queries
    ])

    merged = dedup_and_merge(list(result_lists))           # 投票合并：多路命中的 chunk 排前

    print(
        f"[审核] RAG三路检索: {len(queries)}路查询, "
        f"去重后{len(merged)}条, 取前{min(10, len(merged))}条"
    )

    # 存原始 chunk 列表，供 crag_filter_node 使用（保留分段边界）
    return {"rag_context": "\n\n".join(merged[:10]), "_raw_chunks": merged[:10]}


# ═══════════════════════════════════════════════════════════════
#  节点：CRAG 检索质量过滤（retrieve → crag_filter → judge）
# ═══════════════════════════════════════════════════════════════

async def crag_filter_node(state: ModerationState) -> dict:
    """节点4：CRAG 质量过滤，对 retrieve 返回的 chunk 批量打分，过滤低质量片段。

    【功能/流程定位】
      对应总体流程 ⑧。读取 retrieve 的 _raw_chunks + 内容，用小模型三档打分
      （Correct/Ambiguous/Incorrect），丢低质量、留高相关，更新 rag_context。
      本函数结束后 → 下一个是 judge_node（节点5，违规判定）。

    【思路/代码流程】
      1. 取 content_list + content_type，拼语义串（截 200 字）。
      2. 优先用 _raw_chunks（保留分段边界），降级按 \n\n 切 rag_context。
      3. 无 chunk → 跳过过滤返回空统计。
      4. crag_filter 打分过滤，返回 (filtered_chunks, stats)。
      5. 拼接 filtered_chunks 更新 rag_context，返回 {rag_context, crag_stats}。
      【输入】state["rag_context"] / state["_raw_chunks"]
      【输出】更新 rag_context（过滤后）+ crag_stats（过滤统计）
      参数：state —— 当前图状态。
      返回：dict —— 含 rag_context（过滤后）+ crag_stats（统计）。
    """
    content_list = state["content_list"]                  # 取被举报内容
    content_type = state["content_type"]                  # 取分类（传给评估器做类型加权）
    content_text = " ".join(content_list)[:200]           # 拼语义串截 200 字（喂评估器）

    # 优先用原始 chunk 列表（保留分段边界），降级则按 \n\n 切割 rag_context
    raw_chunks: list[str] = state.get("_raw_chunks") or [  # type: ignore[attr-defined]
        c.strip() for c in state.get("rag_context", "").split("\n\n") if c.strip()
    ]

    if not raw_chunks:                                    # 无检索结果 → 跳过过滤
        print("[CRAG] 无检索结果，跳过过滤")
        return {"crag_stats": {"before": 0, "after": 0}}

    filtered_chunks, stats = await crag_filter(raw_chunks, content_text, content_type)  # 小模型三档打分过滤

    rag_context = "\n\n".join(filtered_chunks)            # 拼接过滤后的 chunk
    return {"rag_context": rag_context, "crag_stats": stats}  # 局部更新 rag_context + 统计


# ═══════════════════════════════════════════════════════════════
#  节点：违规判定（T3 LLM 第二跳）
# ═══════════════════════════════════════════════════════════════

def judge_node(state: ModerationState) -> dict:
    """节点5：LLM 结合内容 + RAG 法规片段，输出 anomaly_score 和违反条款列表。

    【功能/流程定位】
      对应总体流程 ⑨。T3 LLM 第二跳，读取 content + content_type + classify_reason +
      rag_context，用 JUDGE_PROMPT（含五级恶意程度分级表）让 LLM 打分并给条款。
      本函数结束后 → 下一个是 route_after_judge（条件路由，score≥0.6 走 evidence，否则 action）。

    【思路/代码流程】
      1. 取 content_list/content_type/classify_reason/rag_context。
      2. 编号拼文本，填 JUDGE_PROMPT（四占位符）。
      3. get_llm() + SystemMessage + HumanMessage，invoke 同步调用。
      4. 解析输出，取 anomaly_score（默认 0.0）+ violated_rules/laws + judgment。
      5. 打印判定结果，返回四字段（局部更新 state）。
      参数：state —— 当前图状态。
      返回：dict —— 含 anomaly_score/violated_rules/violated_laws/judgment。
    """
    content_list = state["content_list"]                  # 取被举报内容
    content_type = state["content_type"]                  # 取分类（注入 prompt）
    classify_reason = state["classify_reason"]            # 取分类理由（注入 prompt 供 judge 参考）
    rag_context = state["rag_context"]                   # 取过滤后的法规片段

    content_text = "\n".join(f"{i+1}. {c}" for i, c in enumerate(content_list))  # 编号拼文本

    prompt = JUDGE_PROMPT.format(                         # 填充 JUDGE_PROMPT 四占位符
        rag_context=rag_context,                           #   RAG 法规片段
        content_list=content_text,                         #   编号内容
        content_type=content_type,                         #   分类结果
        classify_reason=classify_reason,                   #   分类理由
    )

    llm = get_llm()                                        # 取主 LLM 实例
    from langchain_core.messages import SystemMessage, HumanMessage  # 局部导入消息类
    msgs = [
        SystemMessage(content=SYSTEM_PROMPT),              #   系统角色
        HumanMessage(content=prompt),                      #   本次判定任务
    ]
    response = llm.invoke(msgs)                            # 同步调 LLM 拿判定结果
    result = _parse_json_from_llm(response.content)        # 解析输出 JSON

    anomaly_score = float(result.get("anomaly_score", 0.0))  # 取异常分，默认 0.0
    violated_rules = result.get("violated_rules", [])     # 取违反规则
    violated_laws = result.get("violated_laws", [])       # 取违反法律
    judgment = result.get("judgment", "")                  # 取判定说明

    print(
        f"[审核] 违规判定: score={anomaly_score}, "
        f"违反规则{len(violated_rules)}条, 违反法律{len(violated_laws)}条"
    )

    return {                                               # 局部返回，更新 state 四字段
        "anomaly_score": anomaly_score,
        "violated_rules": violated_rules,
        "violated_laws": violated_laws,
        "judgment": judgment,
    }


# ═══════════════════════════════════════════════════════════════
#  节点：证据生成（T3 LLM 第三跳，或级联 T1/T2 已预填则跳过）
# ═══════════════════════════════════════════════════════════════

def evidence_node(state: ModerationState) -> dict:
    """节点6：LLM 生成结构化封号证据报告（Markdown）。

    【功能/流程定位】
      对应总体流程 ⑪。T3 LLM 第三跳，读取 judge 全部输出 + rag_context，
      用 EVIDENCE_PROMPT（含反幻觉引用约束）生成五章节 Markdown 证据报告。
      本函数结束后 → 下一个是 citation_verify_node（节点7，引用溯源校验）。

    【短路】若 pre_filter（T1 黑名单/T2 API）已写入 evidence_detail，返回 {} 跳过 LLM。
    LangGraph merge 规则：返回空 dict 不覆盖已有字段。

    【思路/代码流程】
      1. 若 state 已有 evidence_detail（级联已生成模板证据）→ 返回 {} 跳过 LLM。
      2. 编号拼文本，填 EVIDENCE_PROMPT（含 judge 输出 + rag_context）。
      3. get_llm() + SystemMessage + HumanMessage，invoke 同步调用。
      4. 直接拿 response.content 作 evidence_detail，返回。
      参数：state —— 当前图状态。
      返回：dict —— 含 evidence_detail（Markdown 报告），或空 dict（级联已填时）。
    """
    if state.get("evidence_detail"):                       # 级联 T1/T2 已写模板证据 → 短路
        print("[审核] 证据已经由级联生成，跳过 LLM")
        return {}                                          # 返回空 dict，LangGraph 不覆盖已有 evidence_detail

    content_list = state["content_list"]                   # 取被举报内容
    content_text = "\n".join(f"{i+1}. {c}" for i, c in enumerate(content_list))  # 编号拼文本

    prompt = EVIDENCE_PROMPT.format(                       # 填充 EVIDENCE_PROMPT 全部占位符
        content_list=content_text,                          #   编号内容
        anomaly_score=state["anomaly_score"],              #   异常分
        content_type=state["content_type"],                #   分类
        violated_rules=", ".join(state["violated_rules"]),  #   违反规则
        violated_laws=", ".join(state["violated_laws"]),   #   违反法律
        judgment=state["judgment"],                        #   判定说明
        rag_context=state.get("rag_context", "（无检索结果）"),  #   RAG 片段，无则占位
    )

    llm = get_llm()                                        # 取主 LLM 实例
    from langchain_core.messages import SystemMessage, HumanMessage  # 局部导入消息类
    msgs = [
        SystemMessage(content=SYSTEM_PROMPT),              #   系统角色
        HumanMessage(content=prompt),                      #   本次证据生成任务
    ]
    response = llm.invoke(msgs)                            # 同步调 LLM 生成报告

    print(f"[审核] 证据报告已生成: {len(response.content)}字")

    return {"evidence_detail": response.content}          # 返回 Markdown 报告，下游 citation_verify 会再修补


# ═══════════════════════════════════════════════════════════════
#  节点：处罚决策（纯逻辑，不调 LLM）
# ═══════════════════════════════════════════════════════════════

def action_node(state: ModerationState) -> dict:
    """节点8：根据 anomaly_score 决定处罚动作（阈值来自 settings，可在 .env 覆盖）。

    【功能/流程定位】
      对应总体流程 ⑬。图的最后一个节点，纯逻辑不调 LLM，按 score 三档定 action。
      本函数结束后 → 下一个是 END（图终止，router 取 action 包装结果）。

    【项目自定义】三档分级：
      score >= moderation_auto_mute_threshold (0.8)  → auto_mute
      score >= moderation_manual_review_threshold (0.6) → manual_review
      其余 → none
    【思路/代码流程】
      1. 取 anomaly_score（默认 0.0）。
      2. ≥0.8→auto_mute；≥0.6→manual_review；其余→none。
      3. 打印决策，返回 {action}。
      参数：state —— 当前图状态。
      返回：dict —— 仅含 action。
    """
    score = state.get("anomaly_score", 0.0)                # 取异常分，默认 0.0

    if score >= settings.moderation_auto_mute_threshold:   # ≥0.8 → 自动禁言
        action = "auto_mute"
    elif score >= settings.moderation_manual_review_threshold:  # ≥0.6 → 人工复核
        action = "manual_review"
    else:                                                  # 其余 → 忽略
        action = "none"

    print(f"[审核] 处罚决策: score={score}, action={action}")

    return {"action": action}                              # 局部返回，更新 state.action


# ═══════════════════════════════════════════════════════════════
#  条件路由函数（返回值必须是 add_conditional_edges mapping 的 key）
# ═══════════════════════════════════════════════════════════════

def route_after_classify(state: ModerationState) -> str:
    """classify 之后：normal 直接 action，违规类型走 retrieve。

    【功能/流程定位】对应总体流程 ⑥。短路：classify 判 normal → 跳 retrieve/judge 直奔 action。
    返回值必须是 build_graph 里 add_conditional_edges mapping 的 key（"action"/"retrieve"）。
    """
    if state["content_type"] == "normal":                 # 判正常 → 跳过检索判定
        return "action"
    return "retrieve"                                      # 违规类型 → 走检索


def route_after_judge(state: ModerationState) -> str:
    """judge 之后：score >= 0.6 生成证据，否则直接 action。

    【功能/流程定位】对应总体流程 ⑩。短路：低分违规不值得出证据 → 跳 evidence 直奔 action。
    阈值用 settings.moderation_manual_review_threshold（0.6），与 action_node 的 manual_review 档对齐。
    """
    if state["anomaly_score"] >= settings.moderation_manual_review_threshold:  # ≥0.6 → 出证据
        return "evidence"
    return "action"                                        # <0.6 → 跳证据直奔 action


def route_after_pre_filter(state: ModerationState) -> str:
    """pre_filter 之后：级联三态路由。

    【功能/流程定位】对应总体流程 ④。级联前置过滤后按 tier_verdict 三态分流，是第一级短路。
    - clear_violation：T1/T2 已填 score/rules/laws（甚至模板证据），跳 classify/retrieve/judge 直奔 evidence
    - clear_normal：明确正常，跳过全部 LLM 直奔 action
    - ambiguous：灰区，走完整 T3 LLM 管线（classify 起）
    """
    verdict = state.get("tier_verdict", "ambiguous")       # 取级联判定，默认 ambiguous
    if verdict == "clear_violation":                       # 明确违规 → 直奔证据
        return "evidence"   # T1/T2 已填 score/rules/laws，直接生成或跳过 evidence
    if verdict == "clear_normal":                          # 明确正常 → 跳全部 LLM
        return "action"     # 明确正常，跳过全部 LLM
    return "classify"       # 灰区，走完整 T3 LLM 管线


# ═══════════════════════════════════════════════════════════════
#  构建图
# ═══════════════════════════════════════════════════════════════

def build_graph():
    """构建并编译审核 Agent 状态机。

    【功能/流程定位】
      对应总体流程的图构建。被 router.py::get_graph() 调用（懒加载单例），
      构建 8 节点 StateGraph + 3 处条件路由，compile 返回可被 ainvoke 驱动的图。
      本函数结束后 → 调用方 router 缓存单例，_run_moderate_task 用 ainvoke 驱动。

    图结构：
        pre_filter → [clear_violation] → evidence → citation_verify → action → END
                   → [clear_normal]   → action → END
                   → [ambiguous]      → classify → [normal] → action → END
                                                → retrieve → crag_filter → judge → [score>=0.6] → evidence → ...
                                                                                  → [score<0.6]  → action → END

    compile() 不带 checkpointer：审核是一次性任务，不需要跨请求记忆。

    【思路/代码流程】
      1. StateGraph(ModerationState) 创建状态图。
      2. add_node 注册 8 节点（pre_filter/classify/retrieve/crag_filter/judge/evidence/citation_verify/action）。
      3. set_entry_point("pre_filter") 设入口。
      4. add_conditional_edges 加 3 处条件路由（pre_filter/classify/judge 之后）。
      5. add_edge 加固定边（retrieve→crag_filter→judge、evidence→citation_verify→action、action→END）。
      6. compile() 编译返回。
      返回：编译后的 LangGraph 图实例。
    """
    g = StateGraph(ModerationState)                        # 创建状态图，schema = ModerationState

    g.add_node("pre_filter", pre_filter_node)              # 注册节点1：级联前置过滤（实现在 cascade.py）
    g.add_node("classify", classify_node)                  # 注册节点2：内容分类
    g.add_node("retrieve", retrieve_node)                 # 注册节点3：三路 RAG 检索
    g.add_node("crag_filter", crag_filter_node)            # 注册节点4：CRAG 质量过滤
    g.add_node("judge", judge_node)                        # 注册节点5：违规判定
    g.add_node("evidence", evidence_node)                  # 注册节点6：证据生成
    g.add_node("citation_verify", citation_verify_node)    # 注册节点7：引用溯源（实现在 citation_verifier.py）
    g.add_node("action", action_node)                      # 注册节点8：处罚决策

    g.set_entry_point("pre_filter")                        # 设入口节点为 pre_filter

    g.add_conditional_edges(                               # 条件路由1：pre_filter 后级联三态分流
        "pre_filter",
        route_after_pre_filter,
        {"evidence": "evidence", "action": "action", "classify": "classify"},
    )

    g.add_conditional_edges(                               # 条件路由2：classify 后 normal 跳检索
        "classify",
        route_after_classify,
        {"retrieve": "retrieve", "action": "action"},
    )

    g.add_edge("retrieve", "crag_filter")                  # 固定边：retrieve → crag_filter
    g.add_edge("crag_filter", "judge")                    # 固定边：crag_filter → judge

    g.add_conditional_edges(                               # 条件路由3：judge 后低分跳证据
        "judge",
        route_after_judge,
        {"evidence": "evidence", "action": "action"},
    )

    g.add_edge("evidence", "citation_verify")              # 固定边：evidence → citation_verify
    g.add_edge("citation_verify", "action")                # 固定边：citation_verify → action
    g.add_edge("action", END)                              # 终止边：action → END

    return g.compile()                                     # 编译并返回可执行图（无 checkpointer）
