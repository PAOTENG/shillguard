"""FastAPI 应用入口：挂载各 Agent 的 HTTP 路由。

【架构】
  Java 微服务 → HTTP → 本 FastAPI 应用 → LangGraph Agent → LLM/RAG

【挂载的路由一览】（均在 /ai 前缀下）
  POST /ai/chat              对话助手（SSE 流式）
  POST /ai/moderate          内容审核（异步 taskId + 轮询）
  POST /ai/detect-users      恶意用户批量打分
  POST /ai/detect-evidence   高危用户证据生成
  POST /ai/write             帖子续写
  POST /ai/react             ReAct 工具调用示例
  GET  /health               健康检查

【启动方式】
  uvicorn app.main:app --reload --port 8000
  或 python run.py（Windows 推荐，确保事件循环策略生效）
"""
# ── Windows 事件循环兼容 ──
# psycopg3 异步只兼容 SelectorEventLoop，Windows 默认是 ProactorEventLoop。
# 必须在任何事件循环创建之前切换策略。
import sys
import asyncio
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# ── HuggingFace 离线模式 ──
# reranker 本地有缓存，但 transformers 默认联网校验 tokenizer_config.json，
# 国内连 huggingface.co 会超时 ~70-120s。必须在 import transformers/chroma 之前设置。
import os
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

# ── 关闭第三方遥测出网噪音 ──
# mem0 默认上报 PostHog 遥测（us.i.posthog.com），国内 SSL 握手超时会导致
# 每次 search/add 都产生错误日志，并轻微拖慢进程。
# 必须在 mem0 import 之前设置。
os.environ.setdefault("MEM0_TELEMETRY", "false")      # mem0 官方遥测开关
os.environ.setdefault("ANONYMIZED_TELEMETRY", "false") # ChromaDB 遥测开关（mem0 内部依赖）

# ── LangSmith tracing 初始化 ──
# 必须在任何 LangChain/LangGraph import 之前调用，确保 .env 里的
# LANGCHAIN_PROJECT / LANGSMITH_API_KEY 写入 os.environ 供 tracing 读取。
from app.observability.langsmith_setup import setup_langsmith_tracing
setup_langsmith_tracing()

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 各 Agent 的 APIRouter（每个 router 定义自己的路径，如 @router.post("/chat")）
from app.admin_router import router as admin_router
from app.agents.chat.router import router as chat_router
from app.agents.react.router import router as react_router
from app.agents.writer.router import router as write_router
from app.rag.admin_router import router as rag_admin_router
from app.agents.chat.history_router import router as history_router
from app.agents.moderation.router import router as moderation_router
from app.agents.moderation.detect_router import router as detect_router
from app.agents.moderation.detect_stream_router import router as detect_stream_router
from app.agents.detect.router import router as detect_evidence_router
from app.config import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时拉起审核 MQ 消费者；关闭时断开连接。"""
    if settings.moderation_queue_enabled:
        try:
            from app.agents.moderation.router import handle_moderate_job
            from app.queue.moderation_mq import close_moderation_mq, start_moderation_consumer

            await start_moderation_consumer(handle_moderate_job)
            logger.info("moderation RabbitMQ consumer started")
        except Exception:
            logger.exception(
                "failed to start moderation MQ consumer; "
                "POST /ai/moderate will fallback to BackgroundTasks on publish failure"
            )
    yield
    if settings.moderation_queue_enabled:
        try:
            from app.queue.moderation_mq import close_moderation_mq

            await close_moderation_mq()
        except Exception:
            logger.exception("error closing moderation MQ")


# FastAPI 应用实例；title/version 显示在 /docs Swagger UI
app = FastAPI(title="ShillGuard AI", version="0.1.0", lifespan=lifespan)

# CORS 中间件：开发期 allow_origins=["*"]；生产应改为具体前端域名
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# include_router: 【官方 FastAPI】挂载子路由
# prefix="/ai": 该 router 下所有路径加 /ai 前缀
# tags: Swagger UI 分组标签
app.include_router(admin_router, prefix="/ai", tags=["admin"])
app.include_router(chat_router, prefix="/ai", tags=["chat"])
app.include_router(react_router, prefix="/ai", tags=["react"])
app.include_router(write_router, prefix="/ai", tags=["writer"])
app.include_router(rag_admin_router, prefix="/ai", tags=["rag-admin"])
app.include_router(history_router, prefix="/ai")
app.include_router(moderation_router, prefix="/ai", tags=["moderation"])
app.include_router(detect_router, prefix="/ai", tags=["detect"])
app.include_router(detect_stream_router, prefix="/ai", tags=["detect-stream"])
app.include_router(detect_evidence_router, prefix="/ai", tags=["detect-evidence"])


@app.get("/health")
def health():
    """健康检查，Java/K8s 探针用。"""
    return {"status": "ok"}


from fastapi.responses import HTMLResponse
from pathlib import Path

_STATIC_DIR = Path(__file__).parent / "static"


@app.get("/", response_class=HTMLResponse)
def index():
    """本地测试前端页面。"""
    return (_STATIC_DIR / "index.html").read_text(encoding="utf-8")


if __name__ == "__main__":
    import uvicorn
    # uvicorn.run: 【官方 uvicorn】ASGI 服务器
    # "app.main:app" = 模块路径:FastAPI实例名
    uvicorn.run("app.main:app", reload=True, port=8000)
