"""Elasticsearch BM25 关键词检索客户端（混合检索的第二路召回）。

【与向量检索的分工】
  向量检索(Chroma): 语义相似，「网络暴力」能匹配「侮辱谩骂」
  BM25(ES):         关键词匹配，「刑法第二百四十六条」精确命中法条号

索引对象：父子切分后的 Child（不是 Parent，也不是旧 500/50 窗口）。
"""
from functools import lru_cache
import hashlib

from elasticsearch import AsyncElasticsearch

from app.config import settings

INDEX_NAME = "shillguard_kg"

INDEX_MAPPING = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
    },
    "mappings": {
        "properties": {
            "content": {
                "type": "text",
                "analyzer": "ik_max_word",
                "search_analyzer": "ik_smart",
            },
            "source": {"type": "keyword"},
            "chunk_id": {"type": "keyword"},
            "parent_id": {"type": "keyword"},
            "child_id": {"type": "keyword"},
            "law_name": {"type": "keyword"},
            "article_no": {"type": "keyword"},
            "chapter": {"type": "keyword"},
            "section": {"type": "keyword"},
            "strategy": {"type": "keyword"},
        }
    },
}


def _es_doc_id(chunk_id: str) -> str:
    """ES _id 使用稳定 ASCII，避免中文/过长 id 导致 bulk 部分失败。"""
    return hashlib.sha1((chunk_id or "").encode("utf-8")).hexdigest()


@lru_cache
def _get_es() -> AsyncElasticsearch:
    return AsyncElasticsearch(
        hosts=[settings.es_url.strip()],
        request_timeout=120,
    )


async def ensure_index() -> None:
    es = _get_es()
    if not await es.indices.exists(index=INDEX_NAME):
        await es.indices.create(index=INDEX_NAME, body=INDEX_MAPPING)


async def es_recreate_index() -> None:
    """建库时重建索引，确保 mapping 含 parent_id 等字段。"""
    es = _get_es()
    if await es.indices.exists(index=INDEX_NAME):
        await es.indices.delete(index=INDEX_NAME)
    await es.indices.create(index=INDEX_NAME, body=INDEX_MAPPING)


async def es_index_chunks(chunks: list[str], metadatas: list[dict], ids: list[str]) -> dict:
    """批量写入 child chunks 到 ES。返回 {indexed, errors, total}。"""
    es = _get_es()
    await ensure_index()

    indexed = 0
    error_samples: list[str] = []
    batch_docs = 200

    for start in range(0, len(ids), batch_docs):
        actions: list[dict] = []
        for chunk_id, chunk, meta in zip(
            ids[start : start + batch_docs],
            chunks[start : start + batch_docs],
            metadatas[start : start + batch_docs],
        ):
            doc_id = _es_doc_id(chunk_id)
            actions.append({"index": {"_index": INDEX_NAME, "_id": doc_id}})
            actions.append({
                "content": chunk or "",
                "source": meta.get("source", "") or "",
                "chunk_id": chunk_id,
                "parent_id": meta.get("parent_id", "") or "",
                "child_id": meta.get("child_id", chunk_id) or chunk_id,
                "law_name": meta.get("law_name", "") or "",
                "article_no": meta.get("article_no", "") or "",
                "chapter": meta.get("chapter", "") or "",
                "section": meta.get("section", "") or "",
                "strategy": meta.get("strategy", "") or "",
            })

        resp = await es.bulk(body=actions, refresh=False)
        if resp.get("errors"):
            for item in resp.get("items", []):
                idx = item.get("index") or {}
                if idx.get("error"):
                    if len(error_samples) < 8:
                        err = idx["error"]
                        error_samples.append(
                            f"{idx.get('_id')}: {err.get('type')} {err.get('reason', '')[:160]}"
                        )
                else:
                    indexed += 1
        else:
            indexed += len(actions) // 2

    await es.indices.refresh(index=INDEX_NAME)
    return {"indexed": indexed, "errors": error_samples, "total": len(ids)}


async def es_delete_by_source(source: str) -> int:
    """按 source 删除 ES 文档，返回 deleted 数。"""
    es = _get_es()
    try:
        resp = await es.delete_by_query(
            index=INDEX_NAME,
            body={"query": {"term": {"source": source}}},
            refresh=True,
        )
        return int(resp.get("deleted", 0))
    except Exception:
        return 0


async def es_search(query: str, top_k: int = 20) -> list[tuple[str, float, dict]]:
    """BM25 关键词检索，返回格式与向量检索一致便于 RRF 融合。"""
    es = _get_es()
    try:
        resp = await es.search(
            index=INDEX_NAME,
            body={
                "query": {
                    "match": {
                        "content": {
                            "query": query,
                            "analyzer": "ik_smart",
                            "operator": "or",
                            "minimum_should_match": "30%",
                        }
                    }
                },
                "size": top_k,
                "_source": [
                    "content",
                    "source",
                    "chunk_id",
                    "parent_id",
                    "child_id",
                    "law_name",
                    "article_no",
                    "chapter",
                    "section",
                    "strategy",
                ],
            },
        )
    except Exception:
        return []

    results = []
    for hit in resp["hits"]["hits"]:
        src = hit["_source"]
        results.append((
            src["content"],
            float(hit["_score"]),
            {
                "source": src.get("source", ""),
                "chunk_id": src.get("chunk_id", ""),
                "parent_id": src.get("parent_id", ""),
                "child_id": src.get("child_id", ""),
                "law_name": src.get("law_name", ""),
                "article_no": src.get("article_no", ""),
                "chapter": src.get("chapter", ""),
                "section": src.get("section", ""),
                "strategy": src.get("strategy", ""),
            },
        ))
    return results
