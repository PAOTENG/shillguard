"""直接调用 MCP 工具函数（与 stdio MCP 同源，评测更快）。"""
from __future__ import annotations

import time
from typing import Any

from eval.shillguard_agent_eval.runners.bootstrap import bootstrap

bootstrap()

from app.mcp.tools_detect import detect_user_score, generate_evidence  # noqa: E402
from app.mcp.tools_moderation import moderate_content  # noqa: E402
from app.mcp.tools_rag import rag_search_laws  # noqa: E402


async def run_mcp_tool(tool: str, input_data: dict) -> dict:
    t0 = time.perf_counter()
    try:
        if tool == "rag_search_laws":
            result = await rag_search_laws(
                query=input_data["query"],
                top_k=int(input_data.get("top_k", 5)),
            )
        elif tool == "moderate_content":
            result = await moderate_content(
                content_list=input_data["content_list"],
                report_category=int(input_data.get("report_category", 0)),
            )
        elif tool == "detect_user_score":
            result = await detect_user_score(content_list=input_data["content_list"])
        elif tool == "generate_evidence":
            result = await generate_evidence(
                content_list=input_data["content_list"],
                anomaly_score=float(input_data["anomaly_score"]),
                violated_rules=input_data.get("violated_rules"),
                violated_laws=input_data.get("violated_laws"),
                judgment=input_data.get("judgment", ""),
            )
        else:
            return {
                "tool": tool,
                "error": f"unknown tool: {tool}",
                "ms": (time.perf_counter() - t0) * 1000,
            }
        return {
            "tool": tool,
            "result": result,
            "ms": (time.perf_counter() - t0) * 1000,
        }
    except Exception as e:
        return {
            "tool": tool,
            "error": str(e),
            "ms": (time.perf_counter() - t0) * 1000,
        }


async def run_pipeline(name: str, input_data: dict) -> dict:
    t0 = time.perf_counter()
    if name == "rag_then_moderate":
        rag = await run_mcp_tool(
            "rag_search_laws",
            {"query": input_data["rag_query"], "top_k": 5},
        )
        if "error" in rag:
            return {"pipeline": name, "error": rag["error"], "rag_result": rag, "ms": 0}
        mod = await run_mcp_tool(
            "moderate_content",
            {
                "content_list": input_data["content_list"],
                "report_category": input_data.get("report_category", 0),
            },
        )
        return {
            "pipeline": name,
            "tool": "moderate_content",
            "rag_result": rag.get("result"),
            "result": mod.get("result"),
            "error": mod.get("error"),
            "ms": (time.perf_counter() - t0) * 1000,
        }

    if name == "detect_then_evidence":
        det = await run_mcp_tool("detect_user_score", {"content_list": input_data["content_list"]})
        if "error" in det:
            return {"pipeline": name, "error": det["error"], "ms": 0}
        scored = det.get("result") or {}
        score = float(scored.get("anomalyScore", 0))
        if score < 0.85:
            return {
                "pipeline": name,
                "tool": "detect_user_score",
                "result": scored,
                "error": f"score {score} too low for evidence pipeline",
                "ms": (time.perf_counter() - t0) * 1000,
            }
        ev = await run_mcp_tool(
            "generate_evidence",
            {
                "content_list": input_data["content_list"],
                "anomaly_score": score,
                "violated_rules": scored.get("violatedRules", []),
                "violated_laws": scored.get("violatedLaws", []),
                "judgment": scored.get("judgment", ""),
            },
        )
        return {
            "pipeline": name,
            "tool": "generate_evidence",
            "detect_result": scored,
            "result": ev.get("result"),
            "error": ev.get("error"),
            "ms": (time.perf_counter() - t0) * 1000,
        }

    return {"pipeline": name, "error": f"unknown pipeline: {name}", "ms": 0}


async def run_cascade_case(cascade_id: str) -> dict:
    """E3：级联 pre_filter（无 LLM）。"""
    import time

    from eval.golden_set import GOLDEN_CASCADE

    case = next((c for c in GOLDEN_CASCADE if c.id == cascade_id), None)
    if not case:
        return {"error": f"cascade case not found: {cascade_id}"}

    from app.agents.moderation.cascade import pre_filter_node

    t0 = time.perf_counter()
    try:
        state = {
            "content_list": case.content_list,
            "report_category": case.report_category,
        }
        out = pre_filter_node(state)
        verdict = out.get("filter_verdict")
        tier = out.get("filter_tier")
        score = out.get("anomaly_score")
        return {
            "cascade_id": cascade_id,
            "verdict": verdict,
            "tier": tier,
            "score": score,
            "expected_verdict": case.expected_verdict,
            "expected_tier": case.expected_tier,
            "expected_score": case.expected_score,
            "ms": (time.perf_counter() - t0) * 1000,
        }
    except Exception as e:
        return {"cascade_id": cascade_id, "error": str(e), "ms": (time.perf_counter() - t0) * 1000}
