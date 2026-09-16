"""RAG 知识库索引构建脚本（离线运行，非 HTTP 服务）。

【作用】
  把 app/rag/sources/ 下的法规 Markdown/PDF 等文件：
    1. 父子切分（条级 Child + 节/邻条 Parent）
    2. 仅将 Child 写入 ChromaDB（语义检索）与 Elasticsearch（BM25）
    3. Parent 写入 data/rag_parents.json，供检索命中后回填

【运行方式】
  cd /d d:\\project\\shill-guard-ai
  D:\\Environment\\Anaconda\\envs\\agent\\python.exe -m app.rag.indexer
  D:\\Environment\\Anaconda\\envs\\agent\\python.exe -m app.rag.indexer --resume
"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import chromadb
from langchain_openai import OpenAIEmbeddings

from app.config import settings
from app.rag.doc_parser import parse_document
from app.rag.es_client import es_index_chunks, es_recreate_index
from app.rag.parent_child_splitter import EMBED_MAX_CHARS, split_document
from app.rag.parent_store import clear_cache, save_all_parents

SOURCES_DIR = Path(__file__).parent / "sources"
COLLECTION_NAME = "shillguard_kg"

CHUNK_SIZE = None
CHUNK_OVERLAP = None


def _chunk_text(text: str, source_file: str = "unknown.md") -> list[str]:
    """兼容旧接口：返回 child 文本列表。"""
    return split_document(text, source_file=source_file).child_texts()


def _log(msg: str) -> None:
    print(msg, flush=True)


def _reset_chroma_collection(client: chromadb.PersistentClient):
    try:
        client.delete_collection(COLLECTION_NAME)
        _log(f"[indexer] 已删除旧 collection: {COLLECTION_NAME}")
    except Exception:
        pass
    return client.get_or_create_collection(COLLECTION_NAME)


def _iter_collection_meta(collection, include_docs: bool = False, batch: int = 200):
    """分页遍历 collection，避免一次性 get 触发 SQLite too many SQL variables。"""
    offset = 0
    include = ["metadatas"] + (["documents"] if include_docs else [])
    while True:
        data = collection.get(include=include, limit=batch, offset=offset)
        ids = data.get("ids") or []
        if not ids:
            break
        metas = data.get("metadatas") or [None] * len(ids)
        docs = data.get("documents") or [None] * len(ids) if include_docs else [None] * len(ids)
        for cid, meta, doc in zip(ids, metas, docs):
            yield cid, meta, doc
        offset += len(ids)
        if len(ids) < batch:
            break


def _existing_sources(collection) -> set[str]:
    sources: set[str] = set()
    try:
        for _cid, meta, _doc in _iter_collection_meta(collection):
            if meta and meta.get("source"):
                sources.add(meta["source"])
    except Exception as e:
        _log(f"[indexer] 读取已有 source 失败: {e}")
    return sources


def _drop_source(collection, source: str) -> int:
    data = collection.get(where={"source": source}, include=[])
    ids = data.get("ids") or []
    # 分批删除，避免一次 ids 过多
    for i in range(0, len(ids), 200):
        collection.delete(ids=ids[i : i + 200])
    return len(ids)


def _purge_oversize_and_sources(collection) -> set[str]:
    """删除超长 child，返回需要强制重处理的 source 集合。"""
    force_redo: set[str] = set()
    drop_ids: list[str] = []
    try:
        for cid, meta, doc in _iter_collection_meta(collection, include_docs=True):
            if doc and len(doc) > EMBED_MAX_CHARS:
                drop_ids.append(cid)
                if meta and meta.get("source"):
                    force_redo.add(meta["source"])
        for i in range(0, len(drop_ids), 200):
            collection.delete(ids=drop_ids[i : i + 200])
        if drop_ids:
            _log(
                f"[indexer] 删除超长残留 child={len(drop_ids)}，"
                f"将重处理 source={len(force_redo)}"
            )
    except Exception as e:
        _log(f"[indexer] 检查超长残留失败（继续）: {e}")
    return force_redo


def _embed_batches(embed, docs: list[str]) -> list[list[float]]:
    """分批 embedding；批次失败时逐条降级。"""
    embeddings: list[list[float]] = []
    batch = 10
    for i in range(0, len(docs), batch):
        chunk = docs[i : i + batch]
        try:
            embeddings.extend(embed.embed_documents(chunk))
        except Exception as e:
            _log(f"[indexer]   ! 批次 embedding 失败，改逐条: {type(e).__name__}")
            for doc in chunk:
                text = doc if len(doc) <= EMBED_MAX_CHARS else doc[:EMBED_MAX_CHARS]
                if not text.strip():
                    text = " "
                embeddings.append(embed.embed_documents([text])[0])
    return embeddings


def build_index(resume: bool = False):
    """主入口。resume=True 时跳过已有 source，并重处理超长残留。"""
    if not SOURCES_DIR.exists():
        _log(f"[indexer] sources 目录不存在，请先创建 {SOURCES_DIR}")
        return

    client = chromadb.PersistentClient(path=settings.chroma_dir)
    if resume:
        collection = client.get_or_create_collection(COLLECTION_NAME)
        skip_sources = _existing_sources(collection)
        _log(
            f"[indexer] resume 模式：Chroma 已有 {collection.count()} child，"
            f"{len(skip_sources)} 个 source"
        )
        force_redo = _purge_oversize_and_sources(collection)
        if force_redo:
            skip_sources -= force_redo
    else:
        collection = _reset_chroma_collection(client)
        skip_sources = set()

    embed = OpenAIEmbeddings(
        model=settings.embedding_model,
        api_key=settings.embed_api_key,
        base_url=settings.embed_base_url,
        check_embedding_ctx_length=False,
        chunk_size=10,
    )

    parent_map: dict[str, dict] = {}

    files = sorted(
        [fp for fp in SOURCES_DIR.iterdir() if fp.is_file()],
        key=lambda p: p.name,
    )
    _log(
        f"[indexer] 共 {len(files)} 个源文件，策略=条级Child+节/邻条Parent"
        f"{'（resume）' if resume else ''}"
    )

    for fp in files:
        try:
            text = parse_document(fp.read_bytes(), fp.name)
        except Exception as e:
            _log(f"[indexer] 处理：{fp.name}")
            _log(f"[indexer]   ! 解析失败，跳过: {e}")
            continue

        try:
            result = split_document(text, source_file=fp.name)
        except Exception as e:
            _log(f"[indexer] 处理：{fp.name}")
            _log(f"[indexer]   ! 切分失败，跳过: {e}")
            continue

        for p in result.parents:
            parent_map[p.parent_id] = p.to_store_record()

        if not result.children:
            _log(f"[indexer] 处理：{fp.name}")
            _log("[indexer]   → 无 child，跳过")
            continue

        if resume and fp.name in skip_sources:
            _log(
                f"[indexer] 跳过（已索引）：{fp.name} "
                f"（{len(result.children)} child / {len(result.parents)} parent）"
            )
            continue

        _log(f"[indexer] 处理：{fp.name}")
        try:
            if resume:
                _drop_source(collection, fp.name)

            ids = [c.child_id for c in result.children]
            docs = [c.text for c in result.children]
            metas = [c.metadata() for c in result.children]
            docs = [
                d if len(d) <= EMBED_MAX_CHARS else d[:EMBED_MAX_CHARS]
                for d in docs
            ]

            embeddings = _embed_batches(embed, docs)
            collection.upsert(
                ids=ids,
                embeddings=embeddings,
                documents=docs,
                metadatas=metas,
            )
            _log(
                f"[indexer]   → {len(result.children)} child / "
                f"{len(result.parents)} parent"
            )
        except Exception as e:
            _log(f"[indexer]   ! 索引失败，跳过该文件: {type(e).__name__}: {e}")
            continue

    clear_cache()
    save_all_parents(parent_map)
    _log(f"[indexer] Parent 映射已写入：{len(parent_map)} 条")
    _log(f"[indexer] Chroma 总计：{collection.count()} child")

    try:
        # 分页收集后写 ES，避免一次性 get 爆 SQL 变量
        ids: list[str] = []
        docs: list[str] = []
        metas: list[dict] = []
        for cid, meta, doc in _iter_collection_meta(collection, include_docs=True):
            ids.append(cid)
            docs.append(doc or "")
            metas.append(meta or {"source": ""})
        if ids:
            asyncio.run(_write_es(docs, metas, ids))
            _log(f"[indexer] ES 索引已写入：{len(ids)} 个 child")
        else:
            _log("[indexer] ES 跳过：Chroma 为空")
    except Exception as e:
        _log(f"[indexer] ES 写入失败（Chroma/Parent 已完成，可稍后重试）: {e}")

    _log("[indexer] 完成")


async def _write_es(chunks, metadatas, ids):
    await es_recreate_index()
    await es_index_chunks(chunks, metadatas, ids)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RAG parent-child indexer")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="跳过 Chroma 中已有 source，继续未完成文件并重建 Parent/ES",
    )
    args = parser.parse_args()
    build_index(resume=args.resume)
