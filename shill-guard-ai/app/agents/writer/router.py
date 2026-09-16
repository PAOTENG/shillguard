"""续写 Agent 的 HTTP 接口：POST /ai/write，SSE 流式返回。

【用途】
  用户给出帖子原文 + 续写要求，LLM 流式输出续写内容。

【图结构】
  单节点 write（见 writer/graph.py），无 RAG、无工具、无记忆。

【请求体 WriteRequest】
  content:     原文
  requirement: 续写要求（风格、长度等）
"""
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage

from app.agents.writer.graph import build_graph
from app.schemas import WriteRequest

router = APIRouter()


@router.post("/write")
async def write_post(req: WriteRequest):
    """流式续写。返回 SSE：data: {"delta": "..."}，结尾 data: [DONE]。"""
    graph = build_graph()
    inputs = {
        "messages": [
            HumanMessage(content=f"【原文】: {req.content}\n【续写要求】: {req.requirement}")
        ]
    }

    async def event_stream():
        async for event in graph.astream_events(inputs, version="v2"):
            if event["event"] == "on_chat_model_stream":
                chunk = event["data"].get("chunk")
                content = getattr(chunk, "content", "") if chunk else ""
                if content:
                    yield f"data: {json.dumps({'delta': content}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
