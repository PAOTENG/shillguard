"""恶意用户检测与证据生成类 MCP Tools。

【设计原则】
  复用 FastAPI 路由层的底层函数/图，不重复实现业务逻辑：
    detect_user_score  → detect_router._score_user()
    generate_evidence  → detect/graph.build_graph().ainvoke()

【典型调用链】
  1. detect_user_score(content_list) → 得到 anomalyScore
  2. 若 anomalyScore >= 0.9 → generate_evidence(...) → 得到 evidenceDetail
"""
from app.mcp import mcp
from app.agents.moderation.detect_router import _score_user
from app.agents.detect.graph import build_graph as build_evidence_graph

_evidence_graph_instance = None


def _get_evidence_graph():
    """懒加载证据 agent 图单例。"""
    global _evidence_graph_instance
    if _evidence_graph_instance is None:
        _evidence_graph_instance = build_evidence_graph()
    return _evidence_graph_instance


@mcp.tool()
async def detect_user_score(content_list: list[str]) -> dict:
    """对单个用户今日的所有帖子/评论打异常分，判断其是否为恶意行为用户。

    输入：
      content_list: 该用户今日的内容列表（帖子标题+正文、评论，建议带 [帖子]/[评论] 前缀以便模型区分）

    输出（dict）：
      anomalyScore:   异常分数 0~1（>=0.9 高危建议禁言，0.8~0.9 预警）
      contentType:    主导违规类型（normal/cyberbullying/fraud/...）
      violatedRules:  违反的平台规则列表
      violatedLaws:   违反的法律条文列表
      judgment:       判定说明

    何时调用：当需要评估某个用户近期发言是否构成恶意行为、是否应预警/禁言时调用。
    注意：本工具只打分，不生成证据。若分数>=0.9 需要完整证据，请接着调用 generate_evidence 工具。
    """
    if not content_list:
        return {
            "anomalyScore": 0.0,
            "contentType": "normal",
            "violatedRules": [],
            "violatedLaws": [],
            "judgment": "该用户今日无内容，未打分。",
        }
    # _score_user 是 async 函数，必须 await
    scored = await _score_user(content_list)
    return {
        "anomalyScore": float(scored["anomaly_score"]),
        "contentType": scored["content_type"],
        "violatedRules": scored["violated_rules"],
        "violatedLaws": scored["violated_laws"],
        "judgment": scored["judgment"],
    }


@mcp.tool()
async def generate_evidence(
    content_list: list[str],
    anomaly_score: float,
    violated_rules: list[str] | None = None,
    violated_laws: list[str] | None = None,
    judgment: str = "",
) -> dict:
    """为高危用户生成完整的禁言证据报告（含具体违规条目 + 法条引用）。

    典型用法：先用 detect_user_score 打分，若分数>=0.9，把打分结果连同原内容
    传入本工具，生成可供用户申诉时引用的结构化证据。

    输入：
      content_list:   该用户今日的内容列表（与打分时传入的相同）
      anomaly_score:  打分阶段得到的异常分数
      violated_rules: 打分阶段得到的违反平台规则列表（可空）
      violated_laws:  打分阶段得到的违反法律条文列表（可空）
      judgment:       打分阶段得到的判定说明（可空）

    输出（dict）：
      evidenceDetail:  完整结构化证据报告（Markdown 文本，含违规条目/规则/法律/处置依据）
      violatingItems:  被判定为违规的具体帖子/评论原文字符串列表

    何时调用：当某用户已被判定为高危（异常分>=0.9）需要生成禁言证据时调用。
    """
    if not content_list:
        return {"evidenceDetail": "无内容，无法生成证据。", "violatingItems": []}

    graph = _get_evidence_graph()
    # 图含 async retrieve_node，需用 ainvoke（【官方 LangGraph】异步执行）
    final_state = await graph.ainvoke({
        "content_list": content_list,
        "anomaly_score": anomaly_score,
        "violated_rules": violated_rules or [],
        "violated_laws": violated_laws or [],
        "judgment": judgment,
    })
    return {
        "evidenceDetail": final_state.get("evidence_detail", ""),
        "violatingItems": final_state.get("violating_items", []),
    }
