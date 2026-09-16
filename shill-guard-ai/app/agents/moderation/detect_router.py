"""每日用户内容批量检测：POST /ai/detect-users（Detect Agent 打分链路，物理在 moderation/）。

============================================================================
本文件对应总体流程的哪一部分
============================================================================
业务属 Detect Agent（见 app/agents/detect/__init__.py 链路A ①~⑤），
因复用 moderation 的 cascade.pre_filter_node 而放在本目录：
  ① detect_users()      —— HTTP 入口：批量接用户内容，串行调 _process_user
  ② _process_user()     —— 单用户：逐条级联 + 统计违规条数 + 定 muteAction
  ③ _cascade_single()   —— 单条：复用 pre_filter_node（T1/T2）+ 灰区走 T3
  ④ _t3_llm_judge()     —— T3 轻量：expander LLM inline 判违规（无 RAG）
  ⑤ 返回 DetectUsersResponse
  遗留 _score_user()    —— 旧打分（含完整 RAG），供 stream/MCP 复用

调用关系：
  - app/main.py 挂载本 router → POST /ai/detect-users
  - detect_stream_router.py 复用 _process_user
  - Java 对 muteAction != "none" 的用户再调 /ai/detect-evidence（detect/ 目录）

============================================================================
本部分流程与思路
============================================================================
管理员/定时任务触发 → Java 按 userId 分组传入今日帖子+评论 → 本接口逐用户逐条级联：
  T1 黑名单 (<1ms) → T2 阿里云 API (~50ms) → T3 轻量 LLM (~1s，无 RAG)
按违规条数定禁言：0→none / 1→mute_3days / 2+→mute_7days；2+ 早退跳过剩余内容。
T3 不跑完整 RAG+证据（太贵）；完整证据由 detect-evidence 对高危用户单独生成。

【与 moderation 举报审核的区别】
  moderation：用户举报 → 单次内容 → 完整 8 节点图（含 RAG+证据+action）
  detect    ：主动扫描 → 批量逐条级联 → 按违规数量定禁言时长

【早退优化】
  某用户已累积 2+ 条违规 → 直接跳过其剩余内容（mute_7days 已确定）。
"""
import asyncio

from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import List

from app.llm import get_expander_llm
from app.rag.retriever import retrieve
from app.rag.query_expander import expand_queries, dedup_and_merge
from app.rag.crag_filter import crag_filter
from app.utils import parse_json_from_llm
from app.agents.moderation.cascade import pre_filter_node
from app.config import settings
from langchain_core.messages import SystemMessage, HumanMessage

router = APIRouter()


# ═══════════════════════════════════════════════════════════════
#  数据模型（字段名 camelCase 与 Java DTO 对齐）
# ═══════════════════════════════════════════════════════════════

class UserContent(BaseModel):
    """单个用户及其今日内容。"""
    userId: int = Field(..., description="用户ID")
    contentList: List[str] = Field(
        ...,
        description="该用户今日帖子(标题+正文)与评论，建议带[帖子]/[评论]前缀",
    )


class DetectUsersRequest(BaseModel):
    """批量检测请求体。"""
    users: List[UserContent] = Field(..., description="待检测的用户内容列表")


class UserScoreResult(BaseModel):
    """单个用户的检测结果（Java 落库 + 阈值判断）。"""
    userId: int = Field(..., description="用户ID")
    # ── 新字段：禁言决策 ──
    muteAction: str = Field(
        "none",
        description="处罚动作：none=不处罚 | mute_3days=禁言3天(1条违规) | mute_7days=禁言7天(2+条违规)",
    )
    violationCount: int = Field(0, description="违规条数")
    violatingItems: List[str] = Field(default=[], description="具体违规的内容原文列表（供 /ai/detect-evidence 使用）")
    # ── 向后兼容字段（detect-evidence 链路需要）──
    anomalyScore: float = Field(0.0, description="最高违规内容的异常分数")
    contentType: str = Field("normal", description="主导违规类型（最严重那条）")
    violatedRules: List[str] = Field(default=[], description="合并后的违反平台规则")
    violatedLaws: List[str] = Field(default=[], description="合并后的违反法律条文")
    evidenceSummary: str = Field("", description="判定说明摘要")
    contentList: List[str] = Field(default=[], description="回传内容快照，便于 Java 落库")


class DetectUsersResponse(BaseModel):
    results: List[UserScoreResult] = Field(default=[], description="每个用户的检测结果")


# ═══════════════════════════════════════════════════════════════
#  T3 轻量 LLM 判定（无 RAG，仅 classify + judge）
# ═══════════════════════════════════════════════════════════════

_T3_LITE_PROMPT = """判断以下单条内容是否违规，输出 JSON：

内容：{content}

输出格式（严格 JSON，不要其他文字）：
{{"is_violation": true或false, "anomaly_score": 0.0到1.0, "content_type": "违规类型或normal", "reason": "判断依据"}}

违规类型参考：cyberbullying/violence/fraud/spam/pornography/privacy_violation/rumor/illegal_sales/gambling/drugs/political/other_violation/normal
anomaly_score 说明：0.8+ 明确违规，0.6-0.8 较明显，0.4-0.6 轻微，< 0.4 基本正常"""


async def _t3_llm_judge(content: str) -> dict:
    """T3 轻量 LLM 判定：用便宜的 expander LLM 对单条内容快速判违规。

    【功能/流程定位】
      对应 Detect 链路A ④。被 _cascade_single 在 pre_filter 判 ambiguous 时调用。
      本函数结束后 → _cascade_single 用 is_violation + score≥阈值 判定是否计入违规。

    【思路/代码流程】
      1. content 截断 300 字填 _T3_LITE_PROMPT。
      2. get_expander_llm().ainvoke 异步调用；parse_json_from_llm 解析。
      3. 返回 is_violation/anomaly_score/content_type/reason。
      4. 失败退化为不违规（不阻断主流程）。
    无 RAG，不生成证据，只判断是否违规 + 异常分；具体条款留给 detect-evidence 补全。
    """
    prompt = _T3_LITE_PROMPT.format(content=content[:300])
    try:
        llm = get_expander_llm()
        resp = await llm.ainvoke([HumanMessage(content=prompt)])
        result = parse_json_from_llm(resp.content)
        return {
            "is_violation": bool(result.get("is_violation", False)),
            "anomaly_score": float(result.get("anomaly_score", 0.0)),
            "content_type": result.get("content_type", "normal"),
            "reason": result.get("reason", ""),
        }
    except Exception as e:
        print(f"[检测-T3] LLM 轻量判定失败（退化为不违规）: {e}")
        return {"is_violation": False, "anomaly_score": 0.0, "content_type": "normal", "reason": ""}


# ═══════════════════════════════════════════════════════════════
#  单条内容级联检测
# ═══════════════════════════════════════════════════════════════

async def _cascade_single(content: str) -> dict:
    """对单条内容运行 T1/T2/T3 级联，返回标准化结果。

    【功能/流程定位】
      对应 Detect 链路A ③。被 _process_user 逐条调用。
      本函数结束后 → _process_user 按 is_violation 累计违规条数 / 合并 rules/laws。

    【思路/代码流程】
      1. 构造 state{content_list:[content], report_category:0}，调 pre_filter_node。
      2. clear_violation → 直接返回违规（带 rules/laws/score）。
      3. clear_normal → 返回不违规。
      4. ambiguous → _t3_llm_judge；is_violation 且 score≥阈值才算违规（T3 不带条款）。

    返回 dict 包含：
      is_violation / anomaly_score / content_type / violated_rules / violated_laws /
      filter_tier（T1-blacklist / T2-api / T3-llm / clear_normal）/ reason
    """
    state = {
        "content_list": [content],
        "report_category": 0,   # detect 主动检测，无用户举报分类
    }
    cascade_result = await pre_filter_node(state)
    verdict = cascade_result.get("tier_verdict", "ambiguous")

    if verdict == "clear_violation":
        return {
            "is_violation": True,
            "anomaly_score": float(cascade_result.get("anomaly_score", 0.8)),
            "content_type": cascade_result.get("content_type", "other_violation"),
            "violated_rules": cascade_result.get("violated_rules", []),
            "violated_laws": cascade_result.get("violated_laws", []),
            "filter_tier": cascade_result.get("filter_tier", "T1-blacklist"),
            "reason": cascade_result.get("judgment", ""),
        }

    if verdict == "clear_normal":
        return {
            "is_violation": False,
            "anomaly_score": 0.0,
            "content_type": "normal",
            "violated_rules": [],
            "violated_laws": [],
            "filter_tier": cascade_result.get("filter_tier", "T1-whitelist"),
            "reason": "级联判定正常",
        }

    # ambiguous → T3 轻量 LLM 判定
    t3 = await _t3_llm_judge(content)
    is_violation = t3["is_violation"] and t3["anomaly_score"] >= settings.moderation_manual_review_threshold
    return {
        "is_violation": is_violation,
        "anomaly_score": t3["anomaly_score"],
        "content_type": t3["content_type"],
        "violated_rules": [],     # T3 轻量版不输出具体条款，由 detect-evidence 补全
        "violated_laws": [],
        "filter_tier": "T3-llm",
        "reason": t3["reason"],
    }


# ═══════════════════════════════════════════════════════════════
#  单用户处理
# ═══════════════════════════════════════════════════════════════

async def _process_user(user: UserContent) -> UserScoreResult:
    """对单个用户的所有内容逐条级联，统计违规数，决定禁言时长。

    【功能/流程定位】
      对应 Detect 链路A ②。被 detect_users / detect_stream_router 调用。
      本函数结束后 → 调用方把 UserScoreResult 收进批次结果；Java 对 mute!=none 调 evidence。

    【思路/代码流程】
      1. 逐条 _cascade_single；命中违规则累计、合并 rules/laws、更新最高分+主导类型。
      2. 早退：已有 2+ 条违规 → mute_7days 已定 → break 跳过剩余。
      3. 按条数定 muteAction：0→none / 1→mute_3days / 2+→mute_7days。
      4. 包装 UserScoreResult（含 violatingItems 供 detect-evidence）。

    【早退优化】已有 2+ 条违规时跳过剩余内容（mute_7days 已确定）。
    """
    violations: list[dict] = []
    all_rules: list[str] = []
    all_laws: list[str] = []
    max_score = 0.0
    dominant_type = "normal"

    for content in user.contentList:
        result = await _cascade_single(content)

        if result["is_violation"]:
            violations.append({"content": content, **result})
            all_rules.extend(r for r in result["violated_rules"] if r not in all_rules)
            all_laws.extend(l for l in result["violated_laws"] if l not in all_laws)
            if result["anomaly_score"] > max_score:
                max_score = result["anomaly_score"]
                dominant_type = result["content_type"]

            print(
                f"[检测] 用户 {user.userId} 命中违规: "
                f"tier={result['filter_tier']}, score={result['anomaly_score']:.2f}, "
                f"type={result['content_type']}"
            )

        # 早退：已确认 2+ 条，禁言7天已定，不必再跑剩余
        if len(violations) >= 2:
            remaining = len(user.contentList) - user.contentList.index(content) - 1
            if remaining > 0:
                print(f"[检测] 用户 {user.userId} 早退，已有{len(violations)}条违规，跳过剩余{remaining}条")
            break

    count = len(violations)
    if count == 0:
        mute_action = "none"
    elif count == 1:
        mute_action = "mute_3days"
    else:
        mute_action = "mute_7days"

    violating_items = [v["content"] for v in violations]
    summary = f"共检测{len(user.contentList)}条内容，发现{count}条违规，判定{mute_action}。" if count > 0 else "未发现违规内容。"

    print(
        f"[检测] 用户 {user.userId} 完成: "
        f"检测{len(user.contentList)}条, 违规{count}条, action={mute_action}"
    )

    return UserScoreResult(
        userId=user.userId,
        muteAction=mute_action,
        violationCount=count,
        violatingItems=violating_items,
        anomalyScore=round(max_score, 3),
        contentType=dominant_type,
        violatedRules=all_rules,
        violatedLaws=all_laws,
        evidenceSummary=summary,
        contentList=user.contentList,
    )


# ═══════════════════════════════════════════════════════════════
#  HTTP 接口
# ═══════════════════════════════════════════════════════════════

@router.post("/detect-users", response_model=DetectUsersResponse)
async def detect_users(request: DetectUsersRequest) -> DetectUsersResponse:
    """批量检测今日所有用户内容，按违规条数决定禁言时长。

    【功能/流程定位】
      对应 Detect 链路A ①⑤。HTTP 入口，串行逐用户 _process_user，返回 DetectUsersResponse。
      本函数结束后 → Java 按 muteAction 处置，并对需禁言用户调 /ai/detect-evidence。

    【思路/代码流程】
      1. 遍历 users；空 contentList → 空结果跳过。
      2. try _process_user；失败降级为空结果，继续下一个。
      3. 打印批次统计（用户数 / 触发禁言数），返回 DetectUsersResponse。

    【Java 侧处理逻辑】：
      muteAction == "none"       → 不处理
      muteAction == "mute_3days" → 禁言 3 天
      muteAction == "mute_7days" → 禁言 7 天
        + 对 muteAction != "none" 的用户调 /ai/detect-evidence 生成完整证据报告

    【当前实现】串行逐用户；用户量大时可改 asyncio.gather + Semaphore 限流。
    """
    results: List[UserScoreResult] = []

    for user in request.users:
        if not user.contentList:
            results.append(UserScoreResult(
                userId=user.userId, contentList=[],
            ))
            continue
        try:
            result = await _process_user(user)
        except Exception as e:
            print(f"[检测] 用户 {user.userId} 处理失败: {e}")
            results.append(UserScoreResult(
                userId=user.userId, contentList=user.contentList,
            ))
            continue
        results.append(result)

    mute_count = sum(1 for r in results if r.muteAction != "none")
    print(f"[检测] 批次完成: {len(results)}个用户, {mute_count}个触发禁言")

    return DetectUsersResponse(results=results)


# ═══════════════════════════════════════════════════════════════
#  保留原打分函数供 MCP tools_detect / detect_stream_router 复用
#  （新逻辑推荐使用 _process_user，此函数标记为遗留）
# ═══════════════════════════════════════════════════════════════

_LEGACY_SCORE_SYSTEM = "你是内容安全审核专家，分析用户发布内容是否违规。"
_LEGACY_SCORE_PROMPT = """分析以下用户内容，输出违规评估 JSON：

## 用户内容
{content_list}

## 相关法律条款（RAG检索）
{rag_context}

输出格式（严格JSON）：
{{"anomaly_score":0.0到1.0,"content_type":"违规类型或normal","violated_rules":[],"violated_laws":[],"judgment":"判定说明"}}"""


async def _score_user(content_list: list[str]) -> dict:
    """【遗留】行为模式打分，供 detect_stream_router 和 MCP 工具使用。

    新业务逻辑请使用 _process_user。
    """
    content_joined = " ".join(content_list[:3])[:200] if content_list else "违规内容 平台规则 法律"

    type_query = "违规内容 平台规则 法律 处罚"
    queries = await expand_queries(content_list[:3], "other_violation", type_query)
    result_lists = await asyncio.gather(*[retrieve(q, top_k=10) for q in queries])
    merged = dedup_and_merge(list(result_lists))
    filtered_chunks, crag_stats = await crag_filter(merged[:10], content_joined, "other_violation")
    print(
        f"[检测-遗留] 三路检索: {len(queries)}路, 去重{len(merged)}条, "
        f"CRAG过滤后{crag_stats['after']}条"
    )
    rag_context = "\n\n".join(filtered_chunks) if filtered_chunks else "（未检索到相关条款）"

    content_text = "\n".join(f"{i+1}. {c}" for i, c in enumerate(content_list))
    prompt = _LEGACY_SCORE_PROMPT.format(content_list=content_text, rag_context=rag_context)

    from app.llm import get_llm
    llm = get_llm()
    msgs = [SystemMessage(content=_LEGACY_SCORE_SYSTEM), HumanMessage(content=prompt)]
    response = await llm.ainvoke(msgs)
    result = parse_json_from_llm(response.content)

    return {
        "anomaly_score": float(result.get("anomaly_score", 0.0)),
        "content_type": result.get("content_type", "normal"),
        "violated_rules": result.get("violated_rules", []),
        "violated_laws": result.get("violated_laws", []),
        "judgment": result.get("judgment", ""),
    }
