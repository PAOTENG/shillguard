"""审核任务状态存储：优先 Redis，失败时回退进程内 dict。

GET /ai/moderate/result/{taskId} 只读本 store，HTTP 契约不变。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.agents.moderation.schemas import ModerateResult
from app.config import settings

logger = logging.getLogger(__name__)

_MEMORY: dict[str, dict[str, Any]] = {}
_redis = None
_redis_ok: bool | None = None


def _key(task_id: str) -> str:
    return f"{settings.moderation_task_key_prefix}{task_id}"


async def _get_redis():
    """懒连接 Redis；连不上则永久回退内存（本进程内）。"""
    global _redis, _redis_ok
    if _redis_ok is False:
        return None
    if _redis is not None:
        return _redis
    try:
        from redis.asyncio import Redis

        client = Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            password=settings.redis_password or None,
            db=settings.redis_db,
            decode_responses=True,
        )
        await client.ping()
        _redis = client
        _redis_ok = True
        logger.info("moderation task_store: using Redis %s:%s", settings.redis_host, settings.redis_port)
        return _redis
    except Exception as e:
        _redis_ok = False
        logger.warning("moderation task_store: Redis unavailable, fallback to memory (%s)", e)
        return None


def _serialize(entry: dict[str, Any]) -> str:
    payload = {"status": entry["status"]}
    if "error" in entry and entry["error"] is not None:
        payload["error"] = entry["error"]
    if "result" in entry and entry["result"] is not None:
        result = entry["result"]
        if isinstance(result, ModerateResult):
            payload["result"] = result.model_dump(by_alias=True)
        elif hasattr(result, "model_dump"):
            payload["result"] = result.model_dump(by_alias=True)
        else:
            payload["result"] = result
    return json.dumps(payload, ensure_ascii=False)


def _deserialize(raw: str) -> dict[str, Any]:
    data = json.loads(raw)
    if data.get("result") is not None:
        data["result"] = ModerateResult.model_validate(data["result"])
    return data


class TaskStore:
    """统一 get/set，供 router 与 MQ consumer 共用。"""

    async def set(self, task_id: str, entry: dict[str, Any]) -> None:
        _MEMORY[task_id] = entry
        client = await _get_redis()
        if client is None:
            return
        try:
            await client.set(
                _key(task_id),
                _serialize(entry),
                ex=settings.moderation_task_ttl_seconds,
            )
        except Exception as e:
            logger.warning("task_store Redis set failed: %s", e)

    async def get(self, task_id: str) -> dict[str, Any] | None:
        client = await _get_redis()
        if client is not None:
            try:
                raw = await client.get(_key(task_id))
                if raw:
                    return _deserialize(raw)
            except Exception as e:
                logger.warning("task_store Redis get failed: %s", e)
        return _MEMORY.get(task_id)


task_store = TaskStore()
