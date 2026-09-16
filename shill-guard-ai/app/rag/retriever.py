"""混合检索 + 重排序主模块（RAG 核心入口）。

【整体 pipeline】
  query
    ├─ 向量检索 (ChromaDB + 百炼 embedding)  → top rag_recall_k（Child）
    ├─ BM25 检索 (Elasticsearch)              → top rag_recall_k（Child）
    └─ RRF 融合 → Cross-Encoder Rerank（均在 Child 上）
         └─ 按 parent_id 去重回填 Parent 文本 → 注入 LLM

【RRF 公式】score(doc) = Σ 1/(k + rank_i + 1)，k=60

【MCP 特殊路径】环境变量 SHILLGUARD_DISABLE_RERANK=1 时跳过 rerank。
"""
from functools import lru_cache
import os
import asyncio
import chromadb
from langchain_openai import OpenAIEmbeddings

from app.config import settings
from app.rag.es_client import es_search
from app.rag.reranker import rerank_api
from app.rag.parent_store import get_parent_text

COLLECTION_NAME = "shillguard_kg"


@lru_cache
def _get_collection():
    client = chromadb.PersistentClient(path=settings.chroma_dir)
    return client.get_or_create_collection(COLLECTION_NAME)


@lru_cache
def _get_embed():
    return OpenAIEmbeddings(
        model=settings.embedding_model,
        api_key=settings.embed_api_key,
        base_url=settings.embed_base_url,
        check_embedding_ctx_length=False,
    )


async def _vector_search_async(query: str, top_k: int) -> list[tuple[str, float, dict]]:
    try:
        vec = await asyncio.wait_for(
            _get_embed().aembed_query(query),
            timeout=8.0,
        )
        results = await asyncio.to_thread(
            _get_collection().query,
            query_embeddings=[vec],
            n_results=top_k,
        )
        docs = results["documents"][0] if results["documents"] else []
        dists = results["distances"][0] if results.get("distances") else []
        metas = results["metadatas"][0] if results.get("metadatas") else []
        return [
            (d, dist, m or {}) for d, dist, m in zip(docs, dists, metas)
            if dist < settings.rag_distance_threshold
        ]
    except Exception:
        return []


def _rrf_fusion(
    vec_results: list[tuple[str, float, dict]],
    bm25_results: list[tuple[str, float, dict]],
    k: int = 60,
) -> list[tuple[str, float, dict]]:
    """按 child 文本融合；优先用 child_id / parent_id 做稳定键，避免同文冲突。"""
    scores: dict[str, float] = {}
    payload: dict[str, tuple[str, dict]] = {}

    def _key(chunk: str, meta: dict) -> str:
        cid = (meta or {}).get("child_id") or (meta or {}).get("chunk_id")
        if cid:
            return f"id:{cid}"
        return f"text:{chunk}"

    for rank, (chunk, _, meta) in enumerate(vec_results):
        key = _key(chunk, meta)
        scores[key] = scores.get(key, 0) + 1 / (k + rank + 1)
        payload[key] = (chunk, meta or {})

    for rank, (chunk, _, meta) in enumerate(bm25_results):
        key = _key(chunk, meta)
        scores[key] = scores.get(key, 0) + 1 / (k + rank + 1)
        if key not in payload:
            payload[key] = (chunk, meta or {})

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [(payload[key][0], score, payload[key][1]) for key, score in ranked]


def _expand_parents(
    ordered: list[tuple[str, dict]],
    top_k: int,
) -> list[str]:
    """Child 命中序列 → 按 parent_id 去重回填 Parent 文本。"""
    seen_parent: set[str] = set()
    out: list[str] = []
    for chunk, meta in ordered:
        meta = meta or {}
        parent_id = meta.get("parent_id") or ""
        dedupe_key = parent_id or f"raw:{meta.get('child_id') or chunk[:64]}"
        if dedupe_key in seen_parent:
            continue
        if parent_id:
            parent_text = get_parent_text(parent_id)
            text = parent_text if parent_text else chunk
        else:
            text = chunk
        seen_parent.add(dedupe_key)
        out.append(text)
        if len(out) >= top_k:
            break
    return out


async def retrieve(query: str, top_k: int = None) -> list[str]:
    """混合检索主入口：搜 Child，返回 Parent 文本列表。"""
    import time
    t0 = time.perf_counter()

    if top_k is None:
        top_k = settings.rag_rerank_top_k
    recall_k = settings.rag_recall_k

    vec_results, bm25_results = await asyncio.gather(
        _vector_search_async(query, top_k=recall_k),
        es_search(query, top_k=recall_k),
    )
    t1 = time.perf_counter()

    if not vec_results and not bm25_results:
        return []

    fused = _rrf_fusion(vec_results, bm25_results)
    # 多取一些 child，以便 parent 去重后仍能凑满 top_k
    child_pool = fused[: max(20, top_k * 4)]

    if os.environ.get("SHILLGUARD_DISABLE_RERANK"):
        ordered = [(c, m) for c, _, m in child_pool]
        return _expand_parents(ordered, top_k=top_k)

    try:
        candidates = [chunk for chunk, _, _ in child_pool[:10]]
        meta_by_text: dict[str, dict] = {}
        for chunk, _, meta in child_pool[:10]:
            # 同文保留首次 meta
            meta_by_text.setdefault(chunk, meta or {})

        reranked = await rerank_api(query, candidates, top_k=min(10, len(candidates)))
        t2 = time.perf_counter()

        ordered: list[tuple[str, dict]] = []
        for chunk, score in reranked:
            if score < settings.rag_min_relevance_score:
                continue
            ordered.append((chunk, meta_by_text.get(chunk, {})))

        # rerank 过滤后不足时，用剩余 RRF 顺序补齐
        seen_child = {c for c, _ in ordered}
        for chunk, _, meta in child_pool:
            if chunk in seen_child:
                continue
            ordered.append((chunk, meta or {}))

        parents = _expand_parents(ordered, top_k=top_k)
        print(
            f"[TIMER] embed+bm25={int((t1 - t0) * 1000)}ms "
            f"rerank={int((t2 - t1) * 1000)}ms  "
            f"[RAG] child={len(reranked)}→parent={len(parents)} "
            f"(min_score={settings.rag_min_relevance_score})",
            flush=True,
        )
        return parents
    except Exception as _e:
        t2 = time.perf_counter()
        ordered = [(c, m) for c, _, m in child_pool]
        parents = _expand_parents(ordered, top_k=top_k)
        print(
            f"[TIMER] embed+bm25={int((t1 - t0) * 1000)}ms "
            f"rerank=skip({int((t2 - t1) * 1000)}ms,{type(_e).__name__})  "
            f"[RAG] parent={len(parents)} from RRF (rerank unavailable)",
            flush=True,
        )
        return parents
