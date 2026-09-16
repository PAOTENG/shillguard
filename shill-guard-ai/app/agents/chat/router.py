"""对话 Agent 的 HTTP 接口：POST /ai/chat（Chat Agent 的对外入口）。

============================================================================
本文件对应总体流程的哪一部分
============================================================================
对应 __init__.py 总体流程编号 ①②：
  ① chat()           —— HTTP 入口：接收请求、并发控制、解析文档、构建 inputs、返回 SSE
  ② event_stream()   —— SSE 生成器：流式推送 chat 节点 token + 结束后写双轨存储/更新 mem0

调用关系：
  - app/main.py 挂载本文件的 router（POST /ai/chat）。
  - 本文件调用 graph.py::get_graph/get_pg_pool 驱动图执行、
    memory.py::add_memories_background 异步更新 mem0、
    history_store.py::append_message 写 UI 历史表、
    app/rag/doc_parser.py::parse_document 解析上传文档。
执行入口：前端 POST /ai/chat → chat() → 返回 StreamingResponse(event_stream())。

============================================================================
【协议】
  请求: multipart/form-data（message + thread_id + user_id + 可选 files）
  响应: SSE (text/event-stream)
        每条: data: {"delta": "token"}
        结束: data: [DONE]

【并发控制】
  _CHAT_IN_FLIGHT 全局计数 + settings.chat_max_concurrent → 超过返回 429

【多轮记忆（三层）】
  1. 滑动窗口：chat_node 内只取最近 keep_recent_messages 条消息传给 LLM
  2. LLM 摘要：history 超阈值时，memory_node 压缩旧消息写入 state.summary（独立字段）
  3. mem0 跨会话：SSE 流结束后，用 asyncio.create_task 异步更新 mem0
     - 传入完整对话对（user + assistant），mem0 内置 LLM 提取双方事实
     - 写入前经 OWASP Agent Memory Guard (ASI06) 校验

【双轨存储（工业标准）】
  - 每轮对话写入 chat_messages 表（UI 历史，append-only，永不压缩）
  - LangGraph checkpointer 独立维护（LLM 工作记忆，可被摘要压缩）
  - UI 永远读 chat_messages，不读 checkpointer

【SSE 过滤】
  只推送 langgraph_node == "chat" 的 stream 事件，
  避免 Worker LLM（context_processor）的结构化 JSON 输出泄漏给用户。

【thread_id vs user_id】
  - thread_id：LangGraph checkpointer 的会话 ID
  - user_id：mem0 + chat_messages 的用户 ID，建议由 Java 后端传入

【流式实现】
  graph.astream_events(version="v2") 监听 on_chat_model_stream 事件逐 token 推送。
  官方文档: https://langchain-ai.github.io/langgraph/how-tos/streaming/
"""
# ── 标准库导入 ──────────────────────────────────────────────────────────────
# asyncio：create_task 异步写库/更新 mem0（不阻塞 SSE 流）
import asyncio
# json：把 delta token 序列化为 SSE data 行
import json
# List：类型注解（files: List[UploadFile]）
from typing import List

# ── FastAPI ─────────────────────────────────────────────────────────────────
# APIRouter：路由对象；File/Form/UploadFile：multipart 表单与文件上传；
# HTTPException：抛 HTTP 错误（如 429）；StreamingResponse：SSE 流式响应
from fastapi import APIRouter, File, Form, UploadFile, HTTPException
# StreamingResponse：返回 text/event-stream 流
from fastapi.responses import StreamingResponse
# HumanMessage：构造用户消息传入图
from langchain_core.messages import HumanMessage

# ── 项目内模块导入 ──────────────────────────────────────────────────────────
# parse_document：解析上传的 pdf/docx/txt 为纯文本
from app.rag.doc_parser import parse_document
# get_graph：取编译后的对话图单例；get_pg_pool：取 PG 连接池（写历史表用）
from app.agents.chat.graph import get_graph, get_pg_pool
# add_memories_background：SSE 结束后异步把对话对写入 mem0（Layer3 跨会话记忆）
from app.agents.chat.memory import add_memories_background
# append_message：向 chat_messages 双轨表追加一条消息（append-only UI 历史）
from app.agents.chat.history_store import append_message
# settings：全局配置（chat_max_concurrent 并发上限等）
from app.config import settings

# 当前在途 chat 请求数（进程内计数，非精确分布式限流）
# 用于在单进程内限制同时处理的 chat 请求数，超过上限返回 429
_CHAT_IN_FLIGHT = 0

# FastAPI 路由对象，由 app/main.py 挂载
router = APIRouter()


@router.post("/chat")
async def chat(
    message: str = Form(...),
    thread_id: str = Form("default"),
    user_id: str = Form(""),          # mem0 用户 ID；空时回退到 thread_id
    files: List[UploadFile] = File(None),
):
    """流式对话接口（含三层记忆管理）。

    【功能 / 流程定位】
      总体流程 ①。Chat Agent 的对外 HTTP 入口，由前端 POST /ai/chat 触发。
      本函数结束后返回 StreamingResponse(event_stream())，后续流式生成走 ②。

    【思路 / 代码流程】
      1. 并发控制：在途计数超 chat_max_concurrent → 抛 429
      2. 计算 effective_user_id（空则回退 thread_id）
      3. 解析上传文件 → doc_context
      4. 取图实例 + 连接池，构造 configurable.thread_id 与 inputs
      5. 异步写用户消息到 chat_messages（不阻塞）
      6. 返回 StreamingResponse(event_stream())，流式输出交给 ②

    参数:
        message:   用户输入文字（Form 必填）
        thread_id: 会话 ID，相同 ID 共享 PostgreSQL 中的对话历史（默认 "default"）
        user_id:   用户真实 ID（用于 mem0 跨会话记忆隔离），建议由 Java 后端传入
        files:     可选上传文件（pdf/docx/txt），解析后注入 doc_context

    返回:
        StreamingResponse（media_type="text/event-stream"），逐 token 推送
    """
    # 声明修改全局在途计数（函数内赋值全局需 global）
    global _CHAT_IN_FLIGHT
    # 并发上限检查：在途数 ≥ 配置上限 → 直接拒绝，返回 429 + Retry-After 头
    if _CHAT_IN_FLIGHT >= settings.chat_max_concurrent:
        raise HTTPException(
            status_code=429,
            detail="服务器繁忙，请稍后重试",
            headers={"Retry-After": "3"},  # 建议客户端 3s 后重试
        )
    # 占用一个并发槽位
    _CHAT_IN_FLIGHT += 1

    # user_id 为空时用 thread_id 作为 mem0 用户标识（单会话降级方案）
    # strip() 去空白后若为空才回退，避免 "  " 这种伪非空
    effective_user_id = user_id.strip() or thread_id

    try:
        # ── 解析上传文档 → doc_context ──
        # 逐文件解析，拼接为带文件名标题的文本块列表
        doc_text_parts = []
        # files 可能为 None，用 `or []` 兜底
        for f in files or []:
            # 无文件名的跳过
            if not f.filename:
                continue
            # 异步读取文件字节流
            data = await f.read()
            # parse_document：按扩展名分发解析（pdf/docx/txt），返回纯文本
            text = parse_document(data, f.filename)
            # 加文件名标题，便于 LLM 区分多文档
            doc_text_parts.append(f"## 文件：{f.filename}\n{text}")
        # 双换行拼接所有文档文本为单一 doc_context
        doc_text = "\n\n".join(doc_text_parts)

        # 取编译后的对话图单例（graph.py::get_graph）
        graph = await get_graph()
        # 取 PG 连接池单例（写 chat_messages 用）
        pool = await get_pg_pool()
        # configurable.thread_id: 【官方 LangGraph】checkpointer 用来区分会话
        # 相同 thread_id 共享同一份工作记忆（messages/summary 等）
        config = {"configurable": {"thread_id": thread_id}}
        # 构造图输入：用户消息 + 上传文档 + user_id
        inputs = {
            # HumanMessage：用户角色消息，作为本轮新问题（messages 末条）
            "messages": [HumanMessage(content=message)],
            # doc_context：上传文档文本，chat_node 通过 system prompt 使用
            "doc_context": doc_text,
            # user_id：传给 memory_node，用于 mem0 按 user 隔离检索
            "user_id": effective_user_id,
        }

        # 双轨存储：写入用户消息（append-only，与 checkpointer 分离）
        # asyncio.create_task：异步执行，不阻塞当前请求返回 SSE 流
        # append_message 在 history_store.py：向 chat_messages 表 INSERT 一条
        asyncio.create_task(
            append_message(pool, thread_id, effective_user_id, "user", message)
        )

        # ── SSE 生成器（闭包，捕获上方变量）──
        async def event_stream():
            """SSE 生成器：只推 chat 节点的 token，结束后写双轨存储 + 更新 mem0。

            【功能 / 流程定位】
              总体流程 ②。由 StreamingResponse 驱动逐事件产出 SSE data 行。
              本生成器结束后（finally），写助手回复 + 异步更新 mem0，一次请求完结。

            【思路】
              astream_events(version="v2") 监听所有 LangChain 事件；
              只放行 event=="on_chat_model_stream" 且 node=="chat" 的事件
              （过滤掉 context_processor 的 Worker LLM 结构化 JSON 输出）；
              finally 块无论正常结束还是异常都会执行收尾写库。
            """
            # 累积完整助手回复（用于结束后写 chat_messages + 更新 mem0）
            full_response_parts: list[str] = []
            try:
                # astream_events：LangGraph 流式事件迭代器（v2 协议）
                # inputs=图输入；config=thread_id；version="v2" 事件协议版本
                async for event in graph.astream_events(inputs, config=config, version="v2"):
                    # 只取 chat 节点的流式输出，过滤掉 Worker LLM（context_processor）
                    # 的结构化 JSON，避免内部数据泄漏给前端
                    # event.metadata.langgraph_node：当前产出事件的节点名
                    node_name = event.get("metadata", {}).get("langgraph_node", "")
                    # 双重判断：是 LLM 流式 token 事件 + 来自 chat 节点
                    if (
                        event["event"] == "on_chat_model_stream"
                        and node_name == "chat"
                    ):
                        # chunk：本次流式增量（AIMessageChunk）
                        chunk = event["data"].get("chunk")
                        # 取 chunk.content；chunk 为 None 时取空串
                        content = getattr(chunk, "content", "") if chunk else ""
                        if content:
                            # 累积完整回复（结束后落库用）
                            full_response_parts.append(content)
                            # 序列化为 SSE data 行：{"delta": "token"}，ensure_ascii=False 保留中文
                            yield f"data: {json.dumps({'delta': content}, ensure_ascii=False)}\n\n"
                # 流正常结束：发送结束标记，前端据此停止接收
                yield "data: [DONE]\n\n"
            finally:
                # ── 收尾：无论正常/异常都执行 ──
                # 释放并发槽位（声明修改全局）
                global _CHAT_IN_FLIGHT
                _CHAT_IN_FLIGHT -= 1

                # 拼接完整助手回复
                full_response = "".join(full_response_parts)

                # 双轨存储：写入助手回复（append-only UI 历史）
                # 非空才写，避免空回复污染历史表
                if full_response.strip():
                    asyncio.create_task(
                        append_message(pool, thread_id, effective_user_id, "assistant", full_response)
                    )

                # Layer 3：SSE 结束后更新 mem0（完整对话对 + AMG 校验）
                # 仅当用户消息非空才更新；add_memories_background 内部含 AMG 安全校验 + 静默降级
                if message.strip():
                    asyncio.create_task(
                        add_memories_background(
                            user_message=message,
                            user_id=effective_user_id,
                            assistant_message=full_response,
                        )
                    )

        # 返回 SSE 流式响应；media_type 声明 text/event-stream 让浏览器/前端按 SSE 解析
        return StreamingResponse(event_stream(), media_type="text/event-stream")
    except Exception:
        # 异常时释放并发槽位（正常路径在 finally 已释放，此处覆盖抛异常前的 +1）
        _CHAT_IN_FLIGHT -= 1
        # 重新抛出，由 FastAPI 转为错误响应
        raise
