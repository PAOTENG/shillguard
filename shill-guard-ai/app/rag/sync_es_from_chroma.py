"""从本地 Chroma（父子 Child）全量重建 ES BM25 索引。

用法（Windows cmd，需能访问 ES HTTP）：
  cd /d d:\\project\\shill-guard-ai
  set PYTHONUNBUFFERED=1
  D:\\Environment\\Anaconda\\envs\\agent\\python.exe -m app.rag.sync_es_from_chroma

若宿主机访问 127.0.0.1:9201 失败，确认 Docker Desktop 中 shill-elasticsearch 已启动。
  set ES_URL=http://127.0.0.1:9201
  D:\\Environment\\Anaconda\\envs\\agent\\python.exe -m app.rag.sync_es_from_chroma
"""
from __future__ import annotations

import asyncio
import os
import time

import chromadb

from app.config import settings
from app.rag.es_client import INDEX_NAME, es_index_chunks, es_recreate_index
from app.rag.indexer import COLLECTION_NAME, _iter_collection_meta


def _log(msg: str) -> None:
    print(msg, flush=True)


async def sync_es_from_chroma() -> None:
    # 允许临时覆盖 ES 地址（隧道/换 IP 场景）；去掉首尾空白（cmd set 易带空格）
    es_url = (os.environ.get("ES_URL") or settings.es_url or "").strip()
    if not es_url:
        raise RuntimeError("ES_URL / settings.es_url 为空")
    settings.es_url = es_url
    from app.rag import es_client as es_mod
    es_mod._get_es.cache_clear()

    _log(f"[sync-es] target={es_url!r} index={INDEX_NAME}")

    client = chromadb.PersistentClient(path=settings.chroma_dir)
    collection = client.get_or_create_collection(COLLECTION_NAME)
    total = collection.count()
    _log(f"[sync-es] chroma children={total}")

    ids: list[str] = []
    docs: list[str] = []
    metas: list[dict] = []
    t0 = time.perf_counter()
    for cid, meta, doc in _iter_collection_meta(collection, include_docs=True, batch=200):
        ids.append(cid)
        docs.append(doc or "")
        m = dict(meta or {})
        m.setdefault("source", "")
        m.setdefault("parent_id", "")
        m.setdefault("child_id", cid)
        m.setdefault("law_name", "")
        m.setdefault("article_no", "")
        m.setdefault("chapter", "")
        m.setdefault("section", "")
        m.setdefault("strategy", "")
        metas.append(m)
        if len(ids) % 5000 == 0:
            _log(f"[sync-es] loaded {len(ids)}/{total}")

    _log(f"[sync-es] loaded done n={len(ids)} in {int((time.perf_counter()-t0)*1000)}ms")
    if not ids:
        _log("[sync-es] chroma empty, abort")
        return

    # 抽样校验父子字段
    with_parent = sum(1 for m in metas if m.get("parent_id"))
    _log(f"[sync-es] with_parent_id={with_parent}/{len(metas)}")
    if with_parent == 0:
        _log("[sync-es] ABORT: chroma 无 parent_id，拒绝写入（避免覆盖成残缺数据）")
        return

    _log("[sync-es] deleting old index + creating parent-child mapping ...")
    await es_recreate_index()
    _log("[sync-es] old index deleted (if existed), new mapping ready")

    _log("[sync-es] bulk indexing children ...")
    t1 = time.perf_counter()
    stats = await es_index_chunks(docs, metas, ids)
    _log(
        f"[sync-es] bulk done in {int((time.perf_counter()-t1)*1000)}ms "
        f"indexed={stats.get('indexed')} total={stats.get('total')}"
    )
    if stats.get("errors"):
        _log(f"[sync-es] bulk error samples ({len(stats['errors'])}):")
        for e in stats["errors"]:
            _log(f"  - {e}")

    # 校验
    from app.rag.es_client import _get_es
    es = _get_es()
    try:
        await es.indices.refresh(index=INDEX_NAME)
        cnt = await es.count(index=INDEX_NAME)
        mapping = await es.indices.get_mapping(index=INDEX_NAME)
        props = mapping[INDEX_NAME]["mappings"].get("properties", {})
        # strategy 分布
        agg = await es.search(
            index=INDEX_NAME,
            size=0,
            aggs={
                "by_strategy": {"terms": {"field": "strategy", "size": 20, "missing": "__MISSING__"}},
                "missing_parent": {"missing": {"field": "parent_id"}},
                "sources": {"cardinality": {"field": "source"}},
            },
        )
        _log(f"[sync-es] es_count={cnt.get('count')} fields={sorted(props.keys())}")
        _log(f"[sync-es] aggs={agg.get('aggregations')}")
        if cnt.get("count") != len(ids):
            _log(f"[sync-es] WARN count mismatch chroma={len(ids)} es={cnt.get('count')}")
        else:
            _log("[sync-es] OK count matches chroma")

        # 冒烟检索
        probe = await es.search(
            index=INDEX_NAME,
            size=2,
            query={"match": {"content": "网络暴力"}},
        )
        hits = probe.get("hits", {}).get("hits", [])
        _log(f"[sync-es] smoke_hits={len(hits)}")
        for h in hits:
            src = h.get("_source", {})
            _log(
                f"  hit strategy={src.get('strategy')} parent_id={bool(src.get('parent_id'))} "
                f"len={len(src.get('content') or '')}"
            )
    finally:
        await es.close()

    _log("[sync-es] 完成")


if __name__ == "__main__":
    asyncio.run(sync_es_from_chroma())
