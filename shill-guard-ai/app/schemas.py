"""通用请求/响应模型 —— chat、react、writer 等 Agent 共用的 HTTP 契约。

【Pydantic BaseModel】
  Field(...): ... 表示必填；Field("default"): 有默认值的可选字段
  官方: https://docs.pydantic.dev/latest/
"""
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """POST /ai/react 的请求体（JSON）。

    注意：/ai/chat 用 multipart/form-data（Form 字段），不用本类；
    本类目前只被 react router 使用，thread_id 在 react 中未启用（图无 checkpointer）。
    """
    message: str = Field(..., description="用户输入")
    thread_id: str = Field("default", description="会话 ID；chat agent 用于 PostgreSQL 多轮记忆")


class WriteRequest(BaseModel):
    """POST /ai/write 的请求体。"""
    content: str = Field(..., description="原文内容")
    requirement: str = Field("", description="续写要求，如字数、风格、方向")


class ChatChunk(BaseModel):
    """（可选）流式响应 chunk 的结构化模型；当前 router 直接 json.dumps 未用此类。"""
    delta: str = Field("", description="流式增量 token")
