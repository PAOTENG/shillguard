"""RAG 知识库管理 HTTP 接口（运营/开发用，非生产审核链路）。

【挂载路径】main.py → prefix="/ai"
  POST   /ai/rag/upload         上传文件并增量索引（Child→Chroma/ES，Parent→store）
  GET    /ai/rag/documents      列出已索引文档
  DELETE /ai/rag/documents/{fn} 删除文档及所有 child/parent
  POST   /ai/rag/generate-tests 对上传文件 SSE 生成测试用例
"""
import json
from pathlib import Path
from collections import Counter

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse

from app.config import settings
from app.rag.doc_parser import parse_document
from app.rag.indexer import COLLECTION_NAME, SOURCES_DIR
from app.rag.parent_child_splitter import split_document
from app.rag.parent_store import upsert_parents, delete_parents_by_source
from app.rag.es_client import es_index_chunks, es_delete_by_source
from app.rag.retriever import _get_embed
from app.llm import get_llm
from langchain_core.messages import SystemMessage, HumanMessage

import chromadb

router = APIRouter()


def _get_collection():
    client = chromadb.PersistentClient(path=settings.chroma_dir)
    return client.get_or_create_collection(COLLECTION_NAME)


@router.post("/rag/upload")
async def upload_to_kb(file: UploadFile = File(...)):
    """上传 → 落盘 → 父子切分 → Child 写 Chroma+ES，Parent 写 store。"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="缺少文件名")

    content = await file.read()

    save_path = SOURCES_DIR / file.filename
    save_path.parent.mkdir(parents=True, exist_ok=True)
    save_path.write_bytes(content)

    text = parse_document(content, file.filename)
    result = split_document(text, source_file=file.filename)
    if not result.children:
        return {"status": "skipped", "reason": "文档无文本内容", "file": file.filename}

    # 先清掉同名旧索引，避免残留
    collection = _get_collection()
    old = collection.get(where={"source": file.filename}, include=[])
    old_ids = old.get("ids", [])
    if old_ids:
        collection.delete(ids=old_ids)
    delete_parents_by_source(file.filename)
    await es_delete_by_source(file.filename)

    embed = _get_embed()
    ids = [c.child_id for c in result.children]
    docs = [c.text for c in result.children]
    metas = [c.metadata() for c in result.children]

    embeddings = []
    for i in range(0, len(docs), 10):
        embeddings.extend(embed.embed_documents(docs[i : i + 10]))

    collection.upsert(
        ids=ids,
        embeddings=embeddings,
        documents=docs,
        metadatas=metas,
    )
    upsert_parents([p.to_store_record() for p in result.parents])
    await es_index_chunks(docs, metas, ids)

    return {
        "status": "ok",
        "file": file.filename,
        "children": len(result.children),
        "parents": len(result.parents),
        "chunks": len(result.children),  # 兼容旧字段
        "total_chars": len(text),
        "strategy": "parent_child",
    }


@router.get("/rag/documents")
def list_documents():
    """按 source 文件名聚合统计 child 数量。"""
    try:
        collection = _get_collection()
        data = collection.get(include=["metadatas"])
    except Exception:
        return {"documents": [], "total_chunks": 0}

    sources = Counter(m.get("source", "未知") for m in data.get("metadatas", []))
    docs = [{"file": k, "chunks": v} for k, v in sorted(sources.items())]
    return {"documents": docs, "total_chunks": len(data.get("ids", []))}


@router.delete("/rag/documents/{filename}")
async def delete_document(filename: str):
    """删除 Chroma child + ES + parent store + sources 原文件。"""
    collection = _get_collection()
    data = collection.get(where={"source": filename}, include=[])
    ids = data.get("ids", [])
    if ids:
        collection.delete(ids=ids)
    removed_parents = delete_parents_by_source(filename)
    await es_delete_by_source(filename)
    (SOURCES_DIR / filename).unlink(missing_ok=True)
    return {
        "status": "deleted",
        "file": filename,
        "removed_chunks": len(ids),
        "removed_parents": removed_parents,
    }


@router.post("/rag/generate-tests")
async def generate_tests(file: UploadFile = File(...)):
    """对上传文档 SSE 流式生成「摘要 + 测试用例」（辅助 QA，非审核功能）。"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="缺少文件名")

    content = await file.read()
    text = parse_document(content, file.filename)

    if not text.strip():
        raise HTTPException(status_code=400, detail="文件无文本内容，无法生成测试用例")

    max_chars = 8000
    doc_text = text[:max_chars]
    if len(text) > max_chars:
        doc_text += "\n...(文档已截断)"

    system_prompt = f"""你是ShillGuard平台的测试工程师。请仔细阅读以下文档内容，完成两个任务：

## 任务1：文档摘要
用3-5句话概括文档的核心内容。

## 任务2：测试用例
根据文档内容设计测试用例，覆盖以下方面：
- 功能性测试：文档中描述的功能点是否正常工作
- 边界条件测试：极端情况下的行为
- 异常场景测试：错误输入、非法操作等
- 业务规则验证：文档中提到的规则是否被正确执行

每个测试用例格式如下：
### 用例编号：TC-XXX
- 用例标题：简短描述
- 前置条件：执行前需要满足的条件
- 测试步骤：1. xxx  2. xxx  3. xxx
- 预期结果：应该看到什么结果
- 优先级：高/中/低

请确保测试用例与文档内容直接相关，不要编造文档中未提及的功能。

## 文档内容
文件名：{file.filename}

{doc_text}
"""

    llm = get_llm()
    msgs = [SystemMessage(content=system_prompt), HumanMessage(content="请开始生成摘要和测试用例。")]

    async def event_stream():
        try:
            async for event in llm.astream_events(msgs, version="v2"):
                if event["event"] == "on_chat_model_stream":
                    chunk = event["data"].get("chunk")
                    c = getattr(chunk, "content", "") if chunk else ""
                    if c:
                        yield f"data: {json.dumps({'delta': c}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
