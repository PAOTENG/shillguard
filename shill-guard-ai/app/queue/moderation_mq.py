"""审核任务 RabbitMQ：与 Java `shillguard.exchange` Topic 对齐。

流程：
  POST /ai/moderate → publish(ai.moderate.request) → Worker consume → 跑图 → task_store
  Java 仍轮询 GET /ai/moderate/result/{taskId}（契约不变）
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable, Awaitable

import aio_pika
from aio_pika import DeliveryMode, ExchangeType
from aio_pika.abc import AbstractIncomingMessage

from app.config import settings

logger = logging.getLogger(__name__)

_connection: aio_pika.RobustConnection | None = None
_channel: aio_pika.abc.AbstractChannel | None = None
_exchange: aio_pika.abc.AbstractExchange | None = None
_consumer_tag: str | None = None
_consume_task: asyncio.Task | None = None


def _amqp_url() -> str:
    user = settings.rabbitmq_username
    pwd = settings.rabbitmq_password
    host = settings.rabbitmq_host
    port = settings.rabbitmq_port
    vhost = settings.rabbitmq_vhost or "/"
    # vhost "/" → 空 path 段需编码为 %2F
    vhost_enc = "" if vhost == "/" else vhost.lstrip("/")
    if vhost == "/":
        return f"amqp://{user}:{pwd}@{host}:{port}/%2F"
    return f"amqp://{user}:{pwd}@{host}:{port}/{vhost_enc}"


async def _ensure_topology() -> aio_pika.abc.AbstractExchange:
    """声明 durable exchange + queue + binding（与 Java RabbitMqConfig 同名）。"""
    global _connection, _channel, _exchange
    if _exchange is not None and _channel is not None and not _channel.is_closed:
        return _exchange

    _connection = await aio_pika.connect_robust(_amqp_url())
    _channel = await _connection.channel()
    await _channel.set_qos(prefetch_count=settings.moderation_mq_prefetch)

    _exchange = await _channel.declare_exchange(
        settings.rabbitmq_exchange,
        ExchangeType.TOPIC,
        durable=True,
    )
    queue = await _channel.declare_queue(
        settings.moderation_mq_queue,
        durable=True,
    )
    await queue.bind(_exchange, routing_key=settings.moderation_mq_routing_key)
    logger.info(
        "RabbitMQ ready: exchange=%s queue=%s key=%s",
        settings.rabbitmq_exchange,
        settings.moderation_mq_queue,
        settings.moderation_mq_routing_key,
    )
    return _exchange


async def publish_moderate_job(task_id: str, request_payload: dict[str, Any]) -> None:
    """投递审核任务；消息持久化，Worker 崩溃可重投。"""
    exchange = await _ensure_topology()
    body = json.dumps(
        {"taskId": task_id, "request": request_payload},
        ensure_ascii=False,
    ).encode("utf-8")
    message = aio_pika.Message(
        body=body,
        delivery_mode=DeliveryMode.PERSISTENT,
        content_type="application/json",
        message_id=task_id,
    )
    await exchange.publish(
        message,
        routing_key=settings.moderation_mq_routing_key,
    )
    logger.info("published moderate job taskId=%s", task_id)


async def start_moderation_consumer(
    handler: Callable[[str, dict[str, Any]], Awaitable[None]],
) -> None:
    """在 FastAPI lifespan 内启动消费者；handler(task_id, request_dict)。"""
    global _consume_task

    async def _run() -> None:
        global _consumer_tag
        while True:
            try:
                await _ensure_topology()
                assert _channel is not None
                queue = await _channel.declare_queue(
                    settings.moderation_mq_queue,
                    durable=True,
                )

                async with queue.iterator() as queue_iter:
                    logger.info("moderation MQ consumer started")
                    async for message in queue_iter:
                        await _handle_message(message, handler)
            except asyncio.CancelledError:
                logger.info("moderation MQ consumer cancelled")
                raise
            except Exception as e:
                logger.exception("moderation MQ consumer error, retry in 3s: %s", e)
                await asyncio.sleep(3)

    _consume_task = asyncio.create_task(_run(), name="moderation-mq-consumer")


async def _handle_message(
    message: AbstractIncomingMessage,
    handler: Callable[[str, dict[str, Any]], Awaitable[None]],
) -> None:
    async with message.process(requeue=True):
        try:
            payload = json.loads(message.body.decode("utf-8"))
            task_id = payload["taskId"]
            request = payload["request"]
        except Exception:
            logger.exception("invalid moderate job payload, drop")
            return
        await handler(task_id, request)


async def close_moderation_mq() -> None:
    """关闭消费者与连接。"""
    global _connection, _channel, _exchange, _consume_task, _consumer_tag
    if _consume_task is not None:
        _consume_task.cancel()
        try:
            await _consume_task
        except asyncio.CancelledError:
            pass
        _consume_task = None
    if _connection is not None and not _connection.is_closed:
        await _connection.close()
    _connection = None
    _channel = None
    _exchange = None
    _consumer_tag = None
    logger.info("moderation MQ closed")
