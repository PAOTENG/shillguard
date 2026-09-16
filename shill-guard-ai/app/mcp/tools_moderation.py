"""内容审核类 MCP Tools。

【职责】
  把 moderation Agent 的完整 LangGraph 流程封装成一个 MCP tool，
  供 Cursor 等 AI 客户端直接调用，与 FastAPI POST /ai/moderate 共用同一套 graph。

【与 HTTP 接口的区别】
  /ai/moderate: 异步 taskId + 轮询（适合 Java 长连接场景）
  moderate_content: 同步等待完整结果（适合 Cursor 单次 tool call）
"""
from app.mcp import mcp
from app.agents.moderation.graph import build_graph

_graph_instance = None


def _get_graph():
    """懒加载审核图单例（compile 有开销，避免每次 tool call 重建）。"""
    global _graph_instance
    if _graph_instance is None:
        _graph_instance = build_graph()
    return _graph_instance


@mcp.tool()
async def moderate_content(content_list: list[str], report_category: int = 0) -> dict:
    """审核被举报的用户内容，走完整审核流程（级联→分类→RAG→判定→证据→处置）。

    输入：
      content_list: 被举报的帖子/评论内容列表（每条一个字符串）
      report_category: 举报分类编号（0=广告/机器人, 1=违法信息, 2=辱骂/人身攻击, 3=色情低俗, 4=其他；与 prompts.REPORT_CATEGORY_MAP 一致）

    输出（dict）：
      anomalyScore:    异常分数 0~1（越高越严重）
      contentType:     违规类型（normal/spam/fraud/cyberbullying/...）
      violatedRules:   违反的平台规则列表
      violatedLaws:    违反的法律条文列表
      judgment:        判定说明
      evidenceDetail:  完整结构化证据报告（Markdown 文本）
      action:          处置建议（none/manual_review/auto_mute）

    何时调用：当需要审核一批被举报内容、判断是否违规并生成证据时调用此工具。
    """
    graph = _get_graph()
    # 图含 async 节点（pre_filter/retrieve），需 ainvoke
    final_state = await graph.ainvoke({
        "content_list": content_list,
        "report_category": report_category,
    })
    return {
        "anomalyScore": final_state.get("anomaly_score", 0.0),
        "contentType": final_state.get("content_type", "normal"),
        "violatedRules": final_state.get("violated_rules", []),
        "violatedLaws": final_state.get("violated_laws", []),
        "judgment": final_state.get("judgment", ""),
        "evidenceDetail": final_state.get("evidence_detail", ""),
        "action": final_state.get("action", "none"),
    }
