"""可选：把对抗样本建到独立 collection，跑真实 retrieve，观察 top chunk 是否缺锚点。

默认写入独立目录 / collection，不污染主库 shillguard_kg。

用法（cmd，需可用的 embedding；ES 可选）：
  cd /d d:\\project\\shill-guard-ai
  set CHUNK_BOUNDARY_SUITE=1
  D:\\Environment\\Anaconda\\envs\\agent\\python.exe -m eval.chunk_boundary_suite.run_retrieve_probe

说明：
  - 本脚本用与 indexer 相同的 500/50 切分写入临时 Chroma；
  - 检索只用向量（不依赖 ES），验证「半条 chunk 可被语义命中且缺锚点」；
  - 若未配置 embed key，将跳过并提示。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCES = ROOT / "sources"
CASES = ROOT / "test_cases.json"
REPORT = ROOT / "reports" / "retrieve_probe_report.json"
CHROMA_DIR = ROOT / "data" / "chroma_boundary_probe"
COLLECTION = "chunk_boundary_probe"


def main() -> int:
    sys.path.insert(0, str(ROOT.parent.parent))
    try:
        import chromadb
        from langchain_openai import OpenAIEmbeddings
        from app.config import settings
        from eval.chunk_boundary_suite.chunk_utils import chunk_text
    except Exception as e:
        print(f"导入失败: {e}")
        return 2

    if not settings.embed_api_key:
        print("未配置 embed_api_key，跳过 retrieve probe。离线请用 run_chunk_integrity。")
        return 0

    cases = json.loads(CASES.read_text(encoding="utf-8"))["cases"]
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    try:
        client.delete_collection(COLLECTION)
    except Exception:
        pass
    col = client.get_or_create_collection(COLLECTION)

    embed = OpenAIEmbeddings(
        model=settings.embedding_model,
        api_key=settings.embed_api_key,
        base_url=settings.embed_base_url,
        check_embedding_ctx_length=False,
        chunk_size=10,
    )

    ids, docs, metas = [], [], []
    for fp in sorted(SOURCES.glob("*.md")):
        text = fp.read_text(encoding="utf-8")
        for c in chunk_text(text):
            cid = f"{fp.stem}_{c['index']}"
            ids.append(cid)
            docs.append(c["text"])
            metas.append({"source": fp.name, "chunk_index": c["index"]})

    print(f"写入 {len(docs)} 个 chunk → {CHROMA_DIR} / {COLLECTION}")
    # 分批 embedding
    batch = 10
    for i in range(0, len(docs), batch):
        sl = slice(i, i + batch)
        vecs = embed.embed_documents(docs[sl])
        col.upsert(ids=ids[sl], embeddings=vecs, documents=docs[sl], metadatas=metas[sl])

    results = []
    for case in cases:
        q = case["query"]
        vec = embed.embed_query(q)
        hit = col.query(query_embeddings=[vec], n_results=3)
        top_doc = hit["documents"][0][0] if hit["documents"] and hit["documents"][0] else ""
        top_meta = hit["metadatas"][0][0] if hit["metadatas"] and hit["metadatas"][0] else {}
        full = case["expected_full_article"]
        anchor = case["must_include_anchor"]
        results.append(
            {
                "id": case["id"],
                "query": q,
                "top_source": top_meta.get("source"),
                "top_chunk_index": top_meta.get("chunk_index"),
                "top_has_full_article": full in top_doc,
                "top_has_anchor": bool(anchor) and anchor in top_doc,
                "top_preview": top_doc[:160] + "…",
                "sliding_window_risk": (full not in top_doc) and (not (anchor and anchor in top_doc)),
            }
        )

    rate = sum(1 for r in results if r["sliding_window_risk"]) / len(results)
    summary = {
        "total": len(results),
        "top_missing_full_and_anchor_rate": rate,
        "note": "比率越高，越说明真实向量检索也会命中半条/缺锚点 chunk",
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"报告 → {REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
