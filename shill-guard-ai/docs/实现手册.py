"""实现手册 —— ChatAgent 剩余功能
======================================
按第2步 → 第3步 → 第4步顺序实现，每步完成后可独立测试。
此文件仅作参考，不可直接运行。
"""

# ══════════════════════════════════════════════════════════════
#  第2步：持久化 Memory（改2处，5分钟）
# ══════════════════════════════════════════════════════════════

# ---- [改] app/config.py ----
# 在 chroma_dir 下方添加一行：
#
#     chroma_dir: str = "./data/chroma"
#     memory_db_path: str = "./data/memory.db"   ← 新增（第2步已改）
#
#     # Embedding（阿里百炼，与 LLM 的 DeepSeek 账号分开）
#     embed_api_key: str = ""                                              ← 新增
#     embed_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"  ← 新增
#     embedding_model: str = "text-embedding-v3"                           ← 新增
#
# .env 文件同时新增（年已有的 DeepSeek 配置不动）：
#     EMBED_API_KEY=sk-xxxxxxxxxxxx    # 阿里百炼的 API Key
#     # EMBED_BASE_URL 可不写，默认已是 dashscope 地址
#
# 注意：./data/ 目录要提前手动创建，或在启动时自动创建（见下方说明）

# ---- [改] app/agents/chat/graph.py ----
# 把 MemorySaver 换成 SqliteSaver，其他不变

"""
# 改前（删除这两行）
from langgraph.checkpoint.memory import MemorySaver
return g.compile(checkpointer=MemorySaver())

# 改后（替换为）
from langgraph.checkpoint.sqlite import SqliteSaver
from app.config import settings
import os
os.makedirs(os.path.dirname(settings.memory_db_path), exist_ok=True)  # 自动建 data/ 目录
checkpointer = SqliteSaver.from_conn_string(settings.memory_db_path)
return g.compile(checkpointer=checkpointer)
"""


# ══════════════════════════════════════════════════════════════
#  第3步：支持用户上传文档（改3个文件）
# ══════════════════════════════════════════════════════════════

# ---- [改] app/agents/chat/prompts.py ----
# 完整替换为以下内容：

"""
SYSTEM_PROMPT 完整新版（替换整个文件）
------------------------------------------------------------
\"\"\"对话 Agent 的系统提示词。\"\"\"

SYSTEM_PROMPT = "你是 ShillGuard 平台的 AI 助手，友好、简洁地回答用户问题。"


def build_system_prompt(doc_context: str = "", rag_context: str = "") -> str:
    \"\"\"动态构建 system prompt：按需注入文档上下文和 RAG 知识片段。\"\"\"
    prompt = SYSTEM_PROMPT
    if rag_context:
        prompt += f"\\n\\n## 参考知识库\\n{rag_context}"
    if doc_context:
        prompt += f"\\n\\n## 用户上传的文档\\n请基于以下文档内容回答用户问题：\\n{doc_context}"
    return prompt
"""

# ---- [改] app/agents/chat/graph.py ----
# 完整替换为以下内容（包含第2步+第3步所有改动，第4步再改一次）：

"""
graph.py 第3步版本（替换整个文件）
------------------------------------------------------------
\"\"\"对话 Agent：SqliteSaver 持久化记忆 + 文档上下文支持。\"\"\"
import os
from typing import Annotated, Optional, TypedDict

from langchain_core.messages import BaseMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.sqlite import SqliteSaver

from app.llm import get_llm
from app.agents.chat.prompts import build_system_prompt
from app.config import settings


class ChatState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    doc_context: Optional[str]   # 用户上传文档的文字内容（第3步新增）


def chat_node(state: ChatState) -> dict:
    llm = get_llm()
    sys = build_system_prompt(doc_context=state.get("doc_context") or "")
    msgs = [SystemMessage(content=sys)] + list(state["messages"])
    response = llm.invoke(msgs)
    return {"messages": [response]}


def build_graph():
    g = StateGraph(ChatState)
    g.add_node("chat", chat_node)
    g.set_entry_point("chat")
    g.add_edge("chat", END)
    os.makedirs(os.path.dirname(settings.memory_db_path), exist_ok=True)
    checkpointer = SqliteSaver.from_conn_string(settings.memory_db_path)
    return g.compile(checkpointer=checkpointer)
"""

# ---- [改] app/agents/chat/router.py ----
# 完整替换为以下内容（支持 multipart/form-data + 可选文件上传）：

"""
router.py 新版（替换整个文件）
------------------------------------------------------------
\"\"\"对话 Agent 的 HTTP 接口：POST /ai/chat，支持文件上传，SSE 流式返回。\"\"\"
import json

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage

from app.agents.chat.graph import build_graph
from app.rag.doc_parser import parse_document

router = APIRouter()


@router.post("/chat")
async def chat(
    message: str = Form(...),
    thread_id: str = Form("default"),
    file: UploadFile | None = File(None),
):
    \"\"\"流式对话。
    - 纯文字请求：multipart/form-data，只填 message 和 thread_id
    - 带文件请求：multipart/form-data，额外附 file 字段
    返回 text/event-stream，每条 `data: {\"delta\": \"...\"}`, 结尾 `data: [DONE]`
    \"\"\"
    # 如果携带了文件，解析成纯文本
    doc_text = ""
    if file and file.filename:
        data = await file.read()
        doc_text = parse_document(data, file.filename)

    graph = build_graph()
    config = {"configurable": {"thread_id": thread_id}}
    inputs = {
        "messages": [HumanMessage(content=message)],
        "doc_context": doc_text,
    }

    async def event_stream():
        async for event in graph.astream_events(inputs, config=config, version="v2"):
            if event["event"] == "on_chat_model_stream":
                chunk = event["data"].get("chunk")
                content = getattr(chunk, "content", "") if chunk else ""
                if content:
                    yield f"data: {json.dumps({'delta': content}, ensure_ascii=False)}\\n\\n"
        yield "data: [DONE]\\n\\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
"""


# ══════════════════════════════════════════════════════════════
#  第4步：RAG 知识库（新建2个文件 + 改 graph.py）
# ══════════════════════════════════════════════════════════════

# ---- [新建] app/rag/sources/ ----
# 手动在该目录下放入知识库文档（PDF / TXT / DOCX 均可）
# 建立目录即可，无需写代码

# ---- [新建] app/rag/indexer.py ----
# 完整内容如下（建好后运行一次：python -m app.rag.indexer）：

"""
indexer.py 完整内容（新建文件）
------------------------------------------------------------
\"\"\"RAG 知识库索引器：遍历 sources/ → 切块 → embedding → 写 ChromaDB。
使用数据：app/rag/sources/ 下所有文档
输出：ChromaDB 向量库（存储路径 settings.chroma_dir）
运行方式：python -m app.rag.indexer
\"\"\"
from pathlib import Path

import chromadb
from langchain_openai import OpenAIEmbeddings

from app.config import settings
from app.rag.doc_parser import parse_document

SOURCES_DIR = Path(__file__).parent / "sources"
COLLECTION_NAME = "kg"
CHUNK_SIZE = 500      # 每块最大字符数
CHUNK_OVERLAP = 50    # 相邻块重叠字符数（保留上下文衔接）


def _chunk_text(text: str) -> list[str]:
    \"\"\"按字符数滑动窗口切块。\"\"\"
    chunks, step = [], CHUNK_SIZE - CHUNK_OVERLAP
    for i in range(0, len(text), step):
        chunk = text[i: i + CHUNK_SIZE]
        if chunk.strip():
            chunks.append(chunk)
    return chunks


def build_index():
    if not SOURCES_DIR.exists():
        print(f"[indexer] sources 目录不存在，请先创建 {SOURCES_DIR}")
        return

    client = chromadb.PersistentClient(path=settings.chroma_dir)
    collection = client.get_or_create_collection(COLLECTION_NAME)
    # ★ 改动：使用阿里百炼独立的 embed_api_key 和 embed_base_url
    # （与 LLM 的 DeepSeek llm_api_key / llm_base_url 完全分开）
    embed = OpenAIEmbeddings(
        model=settings.embedding_model,
        api_key=settings.embed_api_key,
        base_url=settings.embed_base_url,
    )

    for fp in SOURCES_DIR.iterdir():
        if fp.is_dir():
            continue
        print(f"[indexer] 处理：{fp.name}")
        text = parse_document(fp.read_bytes(), fp.name)
        chunks = _chunk_text(text)
        if not chunks:
            continue
        ids = [f"{fp.stem}_{i}" for i in range(len(chunks))]
        collection.upsert(
            ids=ids,
            embeddings=embed.embed_documents(chunks),
            documents=chunks,
            metadatas=[{"source": fp.name}] * len(chunks),
        )
        print(f"[indexer]   → {len(chunks)} chunk 已写入")
    print("[indexer] 完成")


if __name__ == "__main__":
    build_index()
"""

# ---- [新建] app/rag/retriever.py ----

"""
retriever.py 完整内容（新建文件）
------------------------------------------------------------
\"\"\"RAG 检索器：根据 query 从 ChromaDB 返回最相关知识片段。\"\"\"
from functools import lru_cache

import chromadb
from langchain_openai import OpenAIEmbeddings

from app.config import settings

COLLECTION_NAME = "kg"
TOP_K = 3


@lru_cache
def _get_collection():
    client = chromadb.PersistentClient(path=settings.chroma_dir)
    return client.get_or_create_collection(COLLECTION_NAME)


@lru_cache
def _get_embed():
    # ★ 改动：使用阿里百炼独立的 embed_api_key 和 embed_base_url
    # （与 LLM 的 DeepSeek llm_api_key / llm_base_url 完全分开）
    return OpenAIEmbeddings(
        model=settings.embedding_model,
        api_key=settings.embed_api_key,
        base_url=settings.embed_base_url,
    )


def retrieve(query: str, top_k: int = TOP_K) -> list[str]:
    \"\"\"返回与 query 最相关的 top_k 个文本片段。知识库为空时返回 []。\"\"\"
    try:
        vec = _get_embed().embed_query(query)
        results = _get_collection().query(query_embeddings=[vec], n_results=top_k)
        return results["documents"][0] if results["documents"] else []
    except Exception:
        return []
"""

# ---- [改] app/agents/chat/graph.py ----
# 第4步最终版本（在第3步版本基础上加 rag_node）：

"""
graph.py 第4步最终版（替换整个文件）
------------------------------------------------------------
\"\"\"对话 Agent：SqliteSaver + 文档上下文 + RAG 检索。\"\"\"
import os
from typing import Annotated, Optional, TypedDict

from langchain_core.messages import BaseMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.sqlite import SqliteSaver

from app.llm import get_llm
from app.agents.chat.prompts import build_system_prompt
from app.rag.retriever import retrieve
from app.config import settings


class ChatState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    doc_context: Optional[str]   # 用户上传文档
    rag_context: Optional[str]   # RAG 检索结果


def rag_node(state: ChatState) -> dict:
    \"\"\"检索知识库，把相关片段写入 rag_context。\"\"\"
    query = getattr(state["messages"][-1], "content", "")
    snippets = retrieve(query)
    return {"rag_context": "\\n\\n".join(snippets)}


def chat_node(state: ChatState) -> dict:
    \"\"\"调 LLM，system prompt 中注入 doc_context 和 rag_context。\"\"\"
    llm = get_llm()
    sys = build_system_prompt(
        doc_context=state.get("doc_context") or "",
        rag_context=state.get("rag_context") or "",
    )
    msgs = [SystemMessage(content=sys)] + list(state["messages"])
    return {"messages": [llm.invoke(msgs)]}


def build_graph():
    g = StateGraph(ChatState)
    g.add_node("rag", rag_node)
    g.add_node("chat", chat_node)
    g.set_entry_point("rag")
    g.add_edge("rag", "chat")
    g.add_edge("chat", END)
    os.makedirs(os.path.dirname(settings.memory_db_path), exist_ok=True)
    checkpointer = SqliteSaver.from_conn_string(settings.memory_db_path)
    return g.compile(checkpointer=checkpointer)
"""

# ══════════════════════════════════════════════════════════════
#  依赖安装（实现前先运行）
# ══════════════════════════════════════════════════════════════
# pip install chromadb langchain-chroma python-multipart
# （pymupdf、python-docx、python-pptx、openpyxl、easyocr 等文档解析依赖已在第1步装好）

# ══════════════════════════════════════════════════════════════
#  测试命令（每步完成后验证）
# ══════════════════════════════════════════════════════════════
# 第2步完成：重启服务，发一条消息，重启再发一条，历史应仍在
# 第3步完成：curl -F "message=总结这个文件" -F "thread_id=t1" -F "file=@test.pdf" http://localhost:8000/ai/chat
# 第4步建索引：python -m app.rag.indexer
# 第4步完成：直接提问知识库相关内容，看回答是否引用了知识库
