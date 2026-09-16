"""ReAct Agent 的 HTTP 接口：POST /ai/react，SSE 流式返回。

【ReAct 模式】
  Reasoning + Acting：LLM 思考 → 决定是否调工具 → 执行工具 → 再思考 → 回答

【与 /ai/chat 的区别】
  chat:  有 RAG + 多轮记忆(PostgreSQL) + Tavily 搜索
  react: 教学/演示用，calculator + search_web，无记忆，SSE 额外推送 tool_start/tool_end 事件

【astream_events 事件类型】
  on_chat_model_stream — LLM 逐 token 输出
  on_tool_start        — 开始执行工具（前端可显示「正在搜索...」）
  on_tool_end          — 工具返回结果
"""
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage

from app.agents.react.graph import build_graph
from app.schemas import ChatRequest

router = APIRouter()


@router.post("/react")
async def react(req: ChatRequest):
    """流式 ReAct 对话。

    请求体 ChatRequest: { message, thread_id }（thread_id 当前未用，图无 checkpointer）
    """
    graph = build_graph()
    inputs = {"messages": [HumanMessage(content=req.message)]}

    async def event_stream():
        async for event in graph.astream_events(inputs, version="v2"):
            etype = event["event"]

            if etype == "on_chat_model_stream":
                chunk = event["data"].get("chunk")
                content = getattr(chunk, "content", "") if chunk else ""
                if content:
                    yield f"data: {json.dumps({'delta': content}, ensure_ascii=False)}\n\n"

            elif etype == "on_tool_start":
                tname = event.get("name", "")
                yield f"data: {json.dumps({'tool_start': tname}, ensure_ascii=False)}\n\n"

            elif etype == "on_tool_end":
                out = event["data"].get("output", "")
                yield f"data: {json.dumps({'tool_end': str(out)}, ensure_ascii=False)}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
