# 审核异步：RabbitMQ + Redis

## 背景

原实现用 FastAPI `BackgroundTasks` + 进程内 `_task_store`：

- Web 进程与慢链路（灰区 LLM/RAG）耦合，难水平扩 Worker
- 重启丢失内存中的任务状态
- 无法利用已部署的 RabbitMQ（`192.168.150.101:5672`）做削峰与可靠投递

## 现状架构（Java 契约不变）

```
Java POST /ai/moderate
  → Python 写 Redis pending + publish ai.moderate.request
  → 立即返回 taskId

Python Worker（FastAPI lifespan 内）
  → 消费 ai.moderate.queue
  → graph.ainvoke
  → Redis done/error

Java GET /ai/moderate/result/{taskId}  （仍每 2s 轮询）
```

| 资源 | 名称 |
|------|------|
| Exchange | `shillguard.exchange`（Topic，与 Java 一致） |
| Routing Key | `ai.moderate.request` |
| Queue | `ai.moderate.queue` |
| 任务状态 Key | `moderation:task:{taskId}`（Redis，TTL 1h） |

## 配置

`.env` / `app/config.py`：

- `MODERATION_QUEUE_ENABLED=true`：走 MQ；`false` 回退 BackgroundTasks
- `MODERATION_QUEUE_STRICT=false`：入队失败时默认降级 BackgroundTasks，不丢单
- `RABBITMQ_*` / Redis 默认指向 VM `192.168.150.101`（见 `agent项目选择/deploy`）

## Java

`shill-agent` 的 `RabbitMqConfig` 声明了同名 Queue/Binding，便于控制台可见；**审核主路径仍 HTTP**，由 Python 内部入队。禁言通知等仍用既有 `user.mute`。

## 本地验证

1. VM 上 `docker compose ps` 确认 `shill-rabbitmq` / `shill-redis` 健康
2. 启动 `uvicorn app.main:app --port 8000`
3. `POST /ai/moderate` 后，在 http://192.168.150.101:15672 查看 `ai.moderate.queue` 消费
4. 轮询 `GET /ai/moderate/result/{taskId}` 直到 `done`
