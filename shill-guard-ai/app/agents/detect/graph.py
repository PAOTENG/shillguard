"""证据生成 Agent 的 LangGraph 状态机（Detect Agent 证据链路的核心引擎）。

============================================================================
本文件对应总体流程的哪一部分
============================================================================
对应 __init__.py 总体流程编号 ⑦⑧⑨⑩⑪（证据生成链路 B 的图引擎部分）：
  ⑦ build_graph() / get_graph()(get_graph 在 router.py)  —— 构建 4 节点线性图
  ⑧ retrieve_node()         —— 节点1：三路 RAG 检索 + CRAG 过滤
  ⑨ identify_node()         —— 节点2：逐条精细法条标注
  ⑩ evidence_node()         —— 节点3：生成 Markdown 证据报告
  ⑪ citation_verify_node()  —— 节点4：法律引用溯源校验（防幻觉）

调用关系（谁来调用本文件）：
  - router.py::detect_evidence() 通过 build_graph() 拿到编译后的图，
    再 graph.ainvoke(initial_state) 驱动整条链路。
执行入口：graph 被 ainvoke 驱动后，LangGraph 自动按边线性调度 4 个节点 → END。

============================================================================
本部分流程与思路
============================================================================
证据生成链路是一条【4 节点线性图，无条件路由、无循环】：

  START → retrieve → identify → evidence → citation_verify → END

  1. retrieve        ：已知违规方向（contentType + violated_laws/rules），构造 query 三路并行
                      检索法规知识库，CRAG 过滤低质量 chunk → rag_context（法规原文片段）。
  2. identify        ：对【已确认违规】的 violating_items（非全量内容）逐条结合 rag_context
                      做精细标注（original/type/rule/law）→ violating_details。
  3. evidence        ：LLM 综合 violating_items + violating_details + rag_context + 判定信息
                      + mute_action，生成五章节 Markdown 证据报告 → evidence_detail。
  4. citation_verify ：校验 evidence_detail 里每条法律引用是否有 rag_context 支撑，
                      修补幻觉引用，输出 hallucinated_laws（未溯源列表）。

设计要点：
  - 线性无条件路由：证据生成是确定性单次任务，不需要 chat 那种 ReAct 循环/并行 fan-in。
  - 无 checkpointer：一次性任务，无需跨轮持久化状态（与 chat agent 多轮记忆形成对比）。
  - 复用 moderation 的检索策略与溯源器：retrieve 对齐 moderation retrieve_node（Q2精准+Q3 Step-Back
    本体扩展+CRAG），citation_verify 直接复用 moderation/citation_verifier.py，保证两链路风格一致。
  - 精标注而非全量筛选：violating_items 已由链路A 级联确认违规，identify 只做精细法条对应，
    不再从全量内容里挑违规，定位更准、不误判正常内容。

============================================================================
【业务场景】
  /ai/detect-users 级联确认违规后，Java 对 muteAction != "none" 的用户
  调用 /ai/detect-evidence，生成为禁言/申诉用的完整结构化证据报告。

【输入】来自 /ai/detect-users 的级联结果：violatingItems + contentType + violated_laws 等
"""

# ── 标准库：异步并发(asyncio) + JSON 解析(json) + 类型注解(TypedDict/List) ──
import asyncio                                  # asyncio.gather：三路检索并行执行
import json                                      # 预留：JSON 序列化（本文件实际未直接使用，保留以防扩展）
from typing import TypedDict, List               # TypedDict 定义图状态；List 类型注解

# ── LangGraph：状态图构建 ──
from langgraph.graph import StateGraph, END      # StateGraph=状态图容器；END=终止节点

# ── 项目内：LLM 与 RAG 组件 ──
from app.llm import get_llm                      # 主 LLM 工厂（identify/evidence 节点用）
from app.rag.retriever import retrieve           # 单路混合检索（ES BM25 + pgvector + RRF + rerank）
from app.rag.query_expander import expand_queries, dedup_and_merge  # 三路 query 生成 + 去重合并
from app.rag.crag_filter import crag_filter      # CRAG 质量过滤（评估 chunk 与 query 相关性）
from app.agents.moderation.citation_verifier import verify_and_patch_citations  # 法律引用溯源校验器（复用 moderation）
from app.utils import parse_json_from_llm        # 从 LLM 输出文本中健壮提取 JSON（正则兜底）
from app.agents.detect.prompts import (          # 证据生成三个 prompt 模板
    SYSTEM_PROMPT,                               #   identify + evidence 共用的系统角色 prompt
    IDENTIFY_PROMPT,                             #   identify_node 的逐条标注任务 prompt
    EVIDENCE_PROMPT,                             #   evidence_node 的报告生成任务 prompt
)


# ═══════════════════════════════════════════════════════════════
#  State 定义
# ═══════════════════════════════════════════════════════════════

class DetectEvidenceState(TypedDict):
    """证据生成图的状态容器。

    【流程定位】
      被 router.py::detect_evidence() 用 initial_state 初始化（输入字段），
      4 个节点依次往里写入各自产物，最后 router 取 evidence_detail / violating_items 返回。

    【思路】
      用 TypedDict 而非 Pydantic，因为 LangGraph state 要求"可局部更新"（每节点返回 dict
      只更新自己负责的字段，其余保持），TypedDict 正好满足且零运行时校验开销。
      字段分四组：输入 / retrieve 写入 / identify 写入 / evidence 写入 / 可观测性。
    """
    # ── 输入（detect/router.py 从 Java 请求体填充）──
    violating_items: List[str]    # 级联已确认的违规内容列表（非全量内容）
    mute_action: str              # 禁言动作：mute_3days | mute_7days
    content_type: str             # 主导违规类型（指导 RAG 检索方向）
    anomaly_score: float          # 最高违规分数
    violated_rules: List[str]     # 级联已识别的违反规则（T1/T2 有值）
    violated_laws: List[str]      # 级联已识别的违反法律（T1/T2 有值）
    judgment: str                 # 判定说明摘要

    # ── retrieve_node 写入 ──
    rag_context: str              # RAG 检索到的法规原文片段

    # ── identify_node 写入 ──
    violating_details: List[dict] # 内部用：每条违规的完整结构化信息

    # ── evidence_node 写入 ──
    evidence_detail: str          # 最终 Markdown 证据报告（citation_verify 后修补）

    # ── 可观测性字段 ──
    crag_stats: dict              # CRAG 过滤统计
    hallucinated_laws: List[str]  # 未溯源法律引用（citation verify 结果）


# ═══════════════════════════════════════════════════════════════
#  辅助函数
# ═══════════════════════════════════════════════════════════════

def _parse_json_from_llm(text: str) -> dict:
    """从 LLM 输出文本中提取 JSON 字典。

    【功能/流程定位】
      通用辅助函数，被 identify_node 调用（解析 LLM 返回的精细标注 JSON）。
      本函数结束后 → 调用方继续处理解析出的 dict（无固定下游函数，按调用点走）。

    【思路/代码流程】
      不在本文件重新实现 JSON 提取逻辑，而是委托给 app.utils.parse_json_from_llm，
      该函数已封装"去 markdown 代码块包裹 + 正则兜底提取首个 JSON 对象"的健壮逻辑，
      兼容 thinking 模型可能输出的额外说明文字。
      参数：text —— LLM 的原始输出字符串。
      返回：dict —— 解析出的字典（解析失败时返回空 dict，由调用方防御处理）。
    """
    return parse_json_from_llm(text)   # 委托给项目通用工具，保证全项目 JSON 提取行为一致


# ═══════════════════════════════════════════════════════════════
#  节点1：RAG 检索
# ═══════════════════════════════════════════════════════════════

async def retrieve_node(state: DetectEvidenceState) -> dict:
    """节点1：根据打分阶段给出的违规方向构造 query，三路并行检索法规 + CRAG 过滤。

    【功能/流程定位】
      对应总体流程 ⑧。证据生成图的入口节点，从 state 读取链路A 已算出的
      violating_items / violated_laws / violated_rules / content_type，
      检索法规知识库，产出 rag_context 供下游节点引用法条。
      本函数结束后 → 下一个是 identify_node（节点2，逐条精细标注）。

    【升级】与 moderation retrieve_node 对齐：
      - Q2 用已知违规方向（精准）
      - Q3 Step-Back 用 law_taxonomy 本体约束扩展（补漏）
      - CRAG 过滤低质量 chunk
    证据阶段已知 content_type（打分阶段已算出），可以精确选词表。

    【思路/代码流程】
      1. 取输入字段（违规条目/已知法条规则/主导类型）。
      2. 构造 Q2 精准 query（已知违规方向优先，否则通用模板）。
      3. 用违规条目（非全量）构造语义查询串，更精准。
      4. expand_queries 生成三路 query → asyncio.gather 并行 retrieve → dedup_and_merge 去重合并。
      5. crag_filter 过滤低质量 chunk → rag_context（无命中则占位文本）。
      6. 打印检索统计，返回 {rag_context, crag_stats}（局部更新 state）。
      参数：state —— 当前图状态。
      返回：dict —— 仅含 rag_context 与 crag_stats，LangGraph 合并进 state。
    """
    violating_items = state.get("violating_items", [])          # 取已确认违规条目列表，默认空
    violated_laws   = state.get("violated_laws", [])            # 取已知违反法律，用于 Q2 精准 query
    violated_rules  = state.get("violated_rules", [])           # 取已知违反规则，用于 Q2 精准 query
    content_type    = state.get("content_type", "other_violation")  # 取主导违规类型，默认 other_violation

    # Q2 模板：T1/T2 已知违规方向优先，否则用通用模板
    # 把已知 laws+rules 拼成 query（取前4条避免过长），全空则用通用兜底 query
    type_query = " ".join((violated_laws + violated_rules)[:4]) or "违规内容 平台规则 法律 处罚"

    # 用违规条目（非全量）构造语义查询，更精准
    # 取前3条违规条目拼串并截断200字符；无违规条目则用通用 query
    content_joined = " ".join(violating_items[:3])[:200] if violating_items else "违规内容 平台规则 法律"

    # 三路并行检索
    # expand_queries：基于违规条目+类型+type_query 生成多路检索 query（含 Step-Back 本体扩展）
    queries = await expand_queries(violating_items[:3], content_type, type_query)
    # asyncio.gather：对每路 query 并行调 retrieve（单路混合检索，top_k=10），等全部返回
    result_lists = await asyncio.gather(*[retrieve(q, top_k=10) for q in queries])
    # dedup_and_merge：把多路结果列表拍平、去重、合并为一个 chunk 列表
    merged = dedup_and_merge(list(result_lists))

    # CRAG 过滤
    # crag_filter：评估 merged 前10个 chunk 与 content_joined 的相关性，过滤低质量 chunk
    # 返回 (过滤后的 chunk 列表, 统计 dict)；content_type 传给评估器做类型加权
    filtered_chunks, crag_stats = await crag_filter(merged[:10], content_joined, content_type)

    # 拼接法规原文片段；无任何命中则用占位文本（下游节点据此知道"无 RAG 支撑"）
    rag_context = "\n\n".join(filtered_chunks) if filtered_chunks else "（未检索到相关条款）"
    print(                                                       # 打印检索统计：路数/去重后条数/CRAG 过滤后条数，便于观测
        f"[证据] 三路检索: {len(queries)}路, 去重{len(merged)}条, "
        f"CRAG过滤后{crag_stats['after']}条"
    )
    # 局部返回：只更新 state 的 rag_context 与 crag_stats，其余字段保持不变
    return {"rag_context": rag_context, "crag_stats": crag_stats}


# ═══════════════════════════════════════════════════════════════
#  节点2：逐条识别违规内容
# ═══════════════════════════════════════════════════════════════

def identify_node(state: DetectEvidenceState) -> dict:
    """节点2：对级联已确认的违规条目做 LLM 精细标注（违规类型 + 法条对应）。

    【功能/流程定位】
      对应总体流程 ⑨。读取上游 retrieve_node 写入的 rag_context + 输入的 violating_items，
      用 LLM 对每条已确认违规内容标注 original/type/rule/law，产出 violating_details，
      供下游 evidence_node 生成准确引用。
      本函数结束后 → 下一个是 evidence_node（节点3，生成证据报告）。

    【新逻辑】违规条目已由 /ai/detect-users 的级联T1/T2/T3确认，
    此节点不再从全量内容中筛选，而是对已确认违规内容结合 RAG 法条
    做精细化标注（type/rule/law），供 evidence_node 生成准确引用。

    【思路/代码流程】
      1. 取 violating_items / rag_context / violated_rules / violated_laws。
      2. 无违规条目 → 直接返回空 violating_details（短路）。
      3. 把违规条目编号拼成文本，填入 IDENTIFY_PROMPT。
      4. get_llm() 取主 LLM，组装 SystemMessage + HumanMessage，invoke 调用。
      5. 解析 LLM 输出 JSON，遍历 violating_items，过滤无效项（非 dict/无 original），
         收集 {original, type, rule, law} 列表。
      6. 打印标注统计，返回 {violating_details}。
      参数：state —— 当前图状态。
      返回：dict —— 仅含 violating_details（每条违规的精细结构化信息）。
    """
    violating_items = state.get("violating_items", [])   # 取已确认违规条目
    rag_context = state.get("rag_context", "")           # 取上游检索到的法规原文片段
    violated_rules = state.get("violated_rules", [])     # 取已知规则（参考，需 LLM 逐条核实）
    violated_laws = state.get("violated_laws", [])       # 取已知法律（参考，需 LLM 逐条核实）

    if not violating_items:                              # 无违规条目则短路，避免空跑 LLM
        return {"violating_details": []}

    # 把违规条目编号拼成文本（1. xxx\n2. xxx ...），便于 LLM 逐条对应
    content_text = "\n".join(f"{i+1}. {c}" for i, c in enumerate(violating_items))

    # 填充 IDENTIFY_PROMPT 占位符：违规条目文本 + RAG 法条 + 已知规则 + 已知法律
    prompt = IDENTIFY_PROMPT.format(
        content_list=content_text,
        rag_context=rag_context,
        violated_rules=", ".join(violated_rules) if violated_rules else "无",  # 空则显示"无"
        violated_laws=", ".join(violated_laws) if violated_laws else "无",
    )

    llm = get_llm()                                      # 取主 LLM 实例（工厂模式，统一配置）
    from langchain_core.messages import SystemMessage, HumanMessage  # 局部导入消息类，避免文件头冗余
    msgs = [                                             # 组装消息列表：系统角色 + 用户任务
        SystemMessage(content=SYSTEM_PROMPT),            #   系统角色：证据生成专家 + 内嵌法条摘要
        HumanMessage(content=prompt),                    #   用户任务：逐条精细标注
    ]
    response = llm.invoke(msgs)                          # 同步调用 LLM（identify 节点非 async，用 invoke）
    result = _parse_json_from_llm(response.content)      # 解析 LLM 输出 JSON 为 dict

    raw_items = result.get("violating_items", [])        # 取 LLM 标注的违规条目数组
    details = []                                         # 收集清洗后的精细标注
    for it in raw_items:                                 # 遍历每条 LLM 标注结果
        if not isinstance(it, dict):                     # 防御：非 dict 项跳过（LLM 偶尔输出异常结构）
            continue
        original = it.get("original", "")                # 取违规条目原文（用于证据报告展示）
        if not original:                                 # 无原文的项无意义，跳过
            continue
        details.append({                                 # 收集标准化字段（缺失值给默认）
            "original": original,                        #   违规条目原文
            "type": it.get("type", "other"),             #   违规类型，默认 other
            "rule": it.get("rule", ""),                  #   对应平台规则，无则空串
            "law": it.get("law", ""),                    #   对应法律条文，无则空串
        })

    print(f"[证据] 违规条目精细标注: 共{len(violating_items)}条违规内容, 标注完成{len(details)}条")
    return {"violating_details": details}                # 局部返回，更新 state.violating_details


# ═══════════════════════════════════════════════════════════════
#  节点3：生成完整证据报告
# ═══════════════════════════════════════════════════════════════

def evidence_node(state: DetectEvidenceState) -> dict:
    """节点3：LLM 综合违规内容 + 法条 + 规则，生成结构化 Markdown 证据报告。

    【功能/流程定位】
      对应总体流程 ⑩。读取 violating_items + rag_context + 上游 identify_node 的
      violating_details + 判定信息 + mute_action，用 EVIDENCE_PROMPT 让 LLM 生成
      五章节 Markdown 报告，产出 evidence_detail。
      本函数结束后 → 下一个是 citation_verify_node（节点4，引用溯源校验）。

    【思路/代码流程】
      1. 取违规条目 / rag_context / 精细标注 details。
      2. 编号拼接违规条目文本；把 details 格式化为"原文/类型/规则/法律"列表（无则占位说明）。
      3. 根据 mute_action 映射禁言描述（3天/7天）。
      4. 填充 EVIDENCE_PROMPT 全部占位符（含 anomaly_score/judgment 等）。
      5. get_llm() + SystemMessage + HumanMessage，invoke 调用，直接拿 response.content 作报告。
      6. 打印报告字数，返回 {evidence_detail}（Markdown 原文，下游 citation_verify 会再修补）。
      参数：state —— 当前图状态。
      返回：dict —— 仅含 evidence_detail（Markdown 证据报告字符串）。
    """
    violating_items = state.get("violating_items", [])   # 取已确认违规条目
    rag_context = state.get("rag_context", "")           # 取上游检索到的法规原文片段
    details = state.get("violating_details", [])         # 取 identify_node 的精细标注

    content_text = "\n".join(f"{i+1}. {c}" for i, c in enumerate(violating_items))  # 编号拼接违规条目文本

    if details:                                          # 有精细标注 → 格式化为列表项
        items_text = "\n".join(
            f"- 原文：{d['original']}\n  类型：{d['type']}\n  违反规则：{d['rule']}\n  违反法律：{d['law'] or '无'}"
            for d in details                             # law 为空串时显示"无"
        )
    else:                                                # 无精细标注 → 占位说明，提示 LLM 依据打分阶段判定生成
        items_text = "（识别节点未挑出具体违规条目，请依据打分阶段的判定生成证据）"

    mute_action = state.get("mute_action", "mute_3days") # 取禁言动作，默认 mute_3days
    # 映射为人类可读的禁言描述，写进报告的"处罚依据"章节
    mute_desc = "禁言3天（1条违规）" if mute_action == "mute_3days" else "禁言7天（多条违规）"

    # 填充 EVIDENCE_PROMPT 全部占位符（八处），组装最终 prompt
    prompt = EVIDENCE_PROMPT.format(
        content_list=content_text,                       # 编号违规条目
        anomaly_score=state.get("anomaly_score", 0.0),   # 最高违规分数
        violating_items=items_text,                      # 精细标注列表或占位
        rag_context=rag_context,                         # RAG 法规原文片段
        violated_rules=", ".join(state.get("violated_rules", [])) or "无",  # 已知规则，空则"无"
        violated_laws=", ".join(state.get("violated_laws", [])) or "无",    # 已知法律，空则"无"
        judgment=state.get("judgment", "") or "无",      # 打分阶段判定说明，空则"无"
        mute_action=mute_desc,                           # 人类可读禁言描述
    )

    llm = get_llm()                                      # 取主 LLM 实例
    from langchain_core.messages import SystemMessage, HumanMessage  # 局部导入消息类
    msgs = [                                             # 组装消息列表
        SystemMessage(content=SYSTEM_PROMPT),            #   系统角色：证据生成专家
        HumanMessage(content=prompt),                    #   用户任务：生成五章节报告
    ]
    response = llm.invoke(msgs)                          # 同步调用 LLM 生成报告

    print(f"[证据] 证据报告已生成: {len(response.content)}字")
    return {"evidence_detail": response.content}         # 直接把 LLM 输出作 evidence_detail；下游节点会再修补引用


# ═══════════════════════════════════════════════════════════════
#  节点4：引用溯源校验（复用 moderation citation_verifier）
# ═══════════════════════════════════════════════════════════════

def citation_verify_node(state: DetectEvidenceState) -> dict:
    """节点4：校验 evidence_detail 里的法律引用，修补幻觉引用。

    【功能/流程定位】
      对应总体流程 ⑪。证据生成图的最后一个节点，读取 evidence_node 的 evidence_detail +
      violated_laws + rag_context，校验报告中每条法律引用是否有 RAG 上下文支撑，
      修补无支撑的幻觉引用，产出 hallucinated_laws。
      本函数结束后 → 下一个是 END（图终止，state 由 router 取用）。

    复用 moderation/citation_verifier.py 的 verify_and_patch_citations。

    【思路/代码流程】
      1. 取 evidence_detail / violated_laws / rag_context。
      2. rag_context 为空 → 无校验基准，跳过，返回空 hallucinated_laws。
      3. 调 verify_and_patch_citations：逐条法律引用与 rag_context 比对，
         修补无支撑引用，返回 {evidence_detail(修补后), violated_laws, hallucinated_laws, 统计}。
      4. 打印溯源统计（有幻觉则列名，否则全部通过）。
      5. 返回 {evidence_detail(修补后), violated_laws, hallucinated_laws}，更新 state。
      参数：state —— 当前图状态。
      返回：dict —— 修补后的 evidence_detail、可能更新的 violated_laws、未溯源列表。
    """
    evidence_detail = state.get("evidence_detail", "")   # 取上游生成的证据报告
    violated_laws   = state.get("violated_laws", [])     # 取已知违反法律（校验基准之一）
    rag_context     = state.get("rag_context", "")       # 取 RAG 上下文（校验基准之二）

    if not rag_context:                                  # 无 RAG 上下文 → 无法校验溯源，跳过
        print("[证据溯源] rag_context 为空，跳过校验")
        return {"hallucinated_laws": []}

    # 复用 moderation 溯源器：校验 + 修补幻觉法律引用
    # 参数：证据报告 / 已知法律 / RAG 上下文；返回 dict 含修补后报告与统计
    result = verify_and_patch_citations(evidence_detail, violated_laws, rag_context)

    hallucinated = result["hallucinated_laws"]           # 未溯源（幻觉）的法律引用列表
    total        = result["total_count"]                 # 报告中法律引用总数
    grounded     = result["grounded_count"]              # 已溯源（有 RAG 支撑）的数量

    if hallucinated:                                     # 有幻觉引用 → 打印告警 + 列名
        print(
            f"[证据溯源] 共 {total} 处法律引用，已溯源 {grounded}，"
            f"未溯源 {len(hallucinated)}：{hallucinated}"
        )
    else:                                                # 全部溯源通过
        print(f"[证据溯源] 共 {total} 处法律引用，全部溯源通过")

    # 返回修补后的报告 + 可能更新的 violated_laws + 幻觉列表，更新 state 后图结束
    return {
        "evidence_detail":  result["evidence_detail"],   #   修补幻觉引用后的报告
        "violated_laws":    result["violated_laws"],     #   溯源器可能修正的法律列表
        "hallucinated_laws": hallucinated,               #   未溯源列表（可观测性，供日志/审计）
    }


# ═══════════════════════════════════════════════════════════════
#  构建图
# ═══════════════════════════════════════════════════════════════

def build_graph():
    """构建证据生成 Agent 状态机（4 节点线性，无条件路由）。

    【功能/流程定位】
      对应总体流程 ⑦。被 router.py::get_graph() 调用（懒加载单例），
      构建 4 节点 StateGraph 并 compile，返回可被 ainvoke 驱动的编译图。
      本函数结束后 → 调用方 router.py 把它缓存为单例，detect_evidence() 用 ainvoke 驱动。

    流程：retrieve → identify → evidence → citation_verify → END

    与 moderation 不同：无 checkpointer，一次性任务。

    【思路/代码流程】
      1. StateGraph(DetectEvidenceState) 创建状态图容器。
      2. add_node 注册 4 个节点（retrieve/identify/evidence/citation_verify）。
      3. set_entry_point("retrieve") 设入口。
      4. add_edge 串成线性链 retrieve→identify→evidence→citation_verify→END。
      5. compile() 编译为可执行图并返回（无条件路由，无需 add_conditional_edges）。
      返回：编译后的 LangGraph 图实例。
    """
    g = StateGraph(DetectEvidenceState)                  # 创建状态图容器，state schema = DetectEvidenceState

    g.add_node("retrieve", retrieve_node)                # 注册节点1：三路 RAG 检索
    g.add_node("identify", identify_node)                # 注册节点2：逐条精细标注
    g.add_node("evidence", evidence_node)                # 注册节点3：生成证据报告
    g.add_node("citation_verify", citation_verify_node)  # 注册节点4：引用溯源校验

    g.set_entry_point("retrieve")                        # 设入口节点为 retrieve
    g.add_edge("retrieve", "identify")                   # 线性边：retrieve → identify
    g.add_edge("identify", "evidence")                   # 线性边：identify → evidence
    g.add_edge("evidence", "citation_verify")            # 线性边：evidence → citation_verify
    g.add_edge("citation_verify", END)                   # 终止边：citation_verify → END

    return g.compile()                                   # 编译并返回可执行图（无条件路由，无 checkpointer）
