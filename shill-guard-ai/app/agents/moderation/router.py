"""审核 Agent 的 FastAPI 接口（Moderation Agent 举报审核链路的对外入口）。

============================================================================
异步模式（RabbitMQ）
============================================================================
  1. POST /ai/moderate 立刻返回 taskId，写入 task_store(pending)。
  2. 默认将任务投递到 RabbitMQ（shillguard.exchange / ai.moderate.request）；
     Worker 消费后跑 graph.ainvoke，结果写入 Redis/内存 task_store。
  3. MODERATION_QUEUE_ENABLED=false 时回退 FastAPI BackgroundTasks（本地无 MQ）。
  4. Java 仍每 2s 轮询 GET /ai/moderate/result/{taskId}（契约不变）。

生产收益：任务持久化、可多 Worker 扩缩、进程重启不丢队列中的待处理消息；
任务状态优先落 Redis，避免纯内存 dict 多实例不一致。
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.agents.moderation.graph import build_graph
from app.agents.moderation.schemas import (
    ModerateRequest,
    ModerateResult,
    ModerateSubmitResponse,
    ModerateTaskResult,
)
from app.config import settings
from app.queue.task_store import task_store

logger = logging.getLogger(__name__)

router = APIRouter()

_graph_instance = None
_METRICS_LOG = Path("data/cascade_metrics.jsonl")
_METRICS_LOCK = asyncio.Lock()
_METRICS_FP = None


def get_graph():
    """懒加载审核图单例。"""
    global _graph_instance
    if _graph_instance is None:
        _graph_instance = build_graph()
    return _graph_instance


def _append_metric_line(line: str) -> None:
    global _METRICS_FP
    if _METRICS_FP is None:
        _METRICS_LOG.parent.mkdir(parents=True, exist_ok=True)
        _METRICS_FP = _METRICS_LOG.open("a", encoding="utf-8")
    _METRICS_FP.write(line + "\n")
    _METRICS_FP.flush()


async def _log_cascade_metric(request: ModerateRequest, final_state: dict) -> None:
    record = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "report_id": request.reportId,
        "reported_user_id": request.reportedUserId,
        "report_category": request.reportCategory,
        "content_count": len(request.contentList),
        "tier_verdict": final_state.get("tier_verdict", "ambiguous"),
        "filter_tier": final_state.get("filter_tier", "T3-llm"),
        "filter_reason": final_state.get("filter_reason", ""),
        "anomaly_score": final_state.get("anomaly_score", 0.0),
        "content_type": final_state.get("content_type", "normal"),
        "action": final_state.get("action", "none"),
        "cascade_enabled": settings.cascade_enabled,
        "cascade_api_enabled": settings.cascade_api_enabled,
        "api_risk_score": final_state.get("api_risk_score"),
        "api_primary_label": final_state.get("api_primary_label"),
        "hallucinated_laws": final_state.get("hallucinated_laws", []),
        "queue": "rabbitmq" if settings.moderation_queue_enabled else "background",
    }
    line = json.dumps(record, ensure_ascii=False)
    async with _METRICS_LOCK:
        await asyncio.to_thread(_append_metric_line, line)


async def _run_moderate_task(task_id: str, request: ModerateRequest, graph) -> None:
    """执行完整审核链路，结果写入 task_store（供 GET 轮询）。"""
    await task_store.set(task_id, {"status": "processing"})
    try:
        initial_state = {
            "content_list": request.contentList,
            "report_category": request.reportCategory,
        }
        final_state = await graph.ainvoke(initial_state)
        await _log_cascade_metric(request, final_state)

        result = ModerateResult(
            reportId=request.reportId,
            reportedUserId=request.reportedUserId,
            anomalyScore=final_state.get("anomaly_score", 0.0),
            contentType=final_state.get("content_type", "normal"),
            violatedRules=final_state.get("violated_rules", []),
            violatedLaws=final_state.get("violated_laws", []),
            evidenceSummary=final_state.get("judgment", ""),
            evidenceDetail=final_state.get("evidence_detail", ""),
            action=final_state.get("action", "none"),
            tierVerdict=final_state.get("tier_verdict", "ambiguous"),
            filterTier=final_state.get("filter_tier", "T3-llm"),
        )
        await task_store.set(task_id, {"status": "done", "result": result})
    except Exception as e:
        logger.exception("moderate task failed taskId=%s", task_id)
        await task_store.set(task_id, {"status": "error", "error": str(e)})


async def handle_moderate_job(task_id: str, request_dict: dict) -> None:
    """MQ Worker 入口：反序列化请求后跑审核图。"""
    request = ModerateRequest.model_validate(request_dict)
    await _run_moderate_task(task_id, request, get_graph())


@router.post("/moderate")
async def moderate(
    request: ModerateRequest,
    background_tasks: BackgroundTasks,
) -> ModerateSubmitResponse:
    """提交审核任务，立即返回 taskId。"""
    task_id = str(uuid.uuid4())
    await task_store.set(task_id, {"status": "pending"})

    if settings.moderation_queue_enabled:
        try:
            from app.queue.moderation_mq import publish_moderate_job

            await publish_moderate_job(
                task_id,
                request.model_dump(),
            )
        except Exception as e:
            logger.exception("RabbitMQ publish failed, fallback BackgroundTasks")
            # 入队失败不丢单：回退进程内后台任务
            background_tasks.add_task(_run_moderate_task, task_id, request, get_graph())
            # 可选：让调用方感知降级（仍返回 taskId 保证兼容）
            if settings.moderation_queue_strict:
                raise HTTPException(status_code=503, detail=f"mq_publish_failed: {e}") from e
    else:
        background_tasks.add_task(_run_moderate_task, task_id, request, get_graph())

    return ModerateSubmitResponse(taskId=task_id)


@router.get("/moderate/result/{task_id}")
async def moderate_result(task_id: str) -> ModerateTaskResult:
    """轮询审核结果。Java 建议每 2s 轮询，status=done/error 后停止。"""
    entry = await task_store.get(task_id)
    if entry is None:
        return ModerateTaskResult(taskId=task_id, status="not_found")
    return ModerateTaskResult(
        taskId=task_id,
        status=entry["status"],
        result=entry.get("result"),
        error=entry.get("error"),
    )
