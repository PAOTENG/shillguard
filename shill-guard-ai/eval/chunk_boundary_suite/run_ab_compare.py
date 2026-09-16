"""A/B 对比：固定窗口 500/50 vs 父子切分（对抗套件 39 用例）。

包含两层：
  1) 离线切分完整性（不调 embedding，必跑）
  2) 真实向量检索探针（需 embed_api_key；写入独立 chroma，不污染主库）

用法（cmd）：
  cd /d d:\\project\\shill-guard-ai
  D:\\Environment\\Anaconda\\envs\\agent\\python.exe -m eval.chunk_boundary_suite.run_ab_compare

  REM 跳过真实向量检索（只跑离线）：
  set AB_SKIP_RETRIEVE=1
  D:\\Environment\\Anaconda\\envs\\agent\\python.exe -m eval.chunk_boundary_suite.run_ab_compare
"""
from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCES = ROOT / "sources"
CASES = ROOT / "test_cases.json"
REPORT_DIR = ROOT / "reports" / "ab_compare"
BASELINE_DIR = ROOT / "reports" / "baseline_fixed_window_500_50"
CHROMA_DIR = ROOT / "data" / "chroma_ab_compare"


def _load_cases() -> list[dict]:
    if not CASES.exists():
        raise FileNotFoundError("缺少 test_cases.json，请先 build_test_cases")
    return json.loads(CASES.read_text(encoding="utf-8"))["cases"]


def _score(text: str, hooks: list[str]) -> int:
    return sum(1 for h in hooks if h in text)


def eval_offline_fixed(cases: list[dict]) -> dict:
    from eval.chunk_boundary_suite.chunk_utils import analyze_article_split, chunk_text

    doc_cache: dict[str, str] = {}
    results = []
    for case in cases:
        fn = case["source_file"]
        if fn not in doc_cache:
            doc_cache[fn] = (SOURCES / fn).read_text(encoding="utf-8")
        text = doc_cache[fn]
        full = case["expected_full_article"]
        hooks = case["must_include_hooks"]
        anchor = case["must_include_anchor"]
        analysis = analyze_article_split(text, full)
        chunks = analysis.get("chunks") or chunk_text(text)
        ranked = sorted(chunks, key=lambda c: _score(c["text"], hooks), reverse=True)
        top = ranked[0] if ranked else None
        top_score = _score(top["text"], hooks) if top else 0
        top_has_full = bool(top and full in top["text"])
        top_has_anchor = bool(top and anchor and anchor in top["text"])
        sliding_fail = (
            analysis.get("half_hit_possible")
            and top is not None
            and top_score > 0
            and not top_has_full
            and not top_has_anchor
        )
        results.append(
            {
                "id": case["id"],
                "query": case["query"],
                "source_file": fn,
                "intact_in_single_chunk": analysis.get("intact_in_single_chunk"),
                "half_hit_possible": analysis.get("half_hit_possible"),
                "top_has_full_article": top_has_full,
                "top_has_anchor": top_has_anchor,
                "context_cover_ok": bool(top_has_full and top_has_anchor),
                "sliding_window_failure_reproduced": sliding_fail,
                "injected_preview": (top["text"][:120] + "…") if top else "",
            }
        )

    n = len(results) or 1
    summary = {
        "strategy": "fixed_sliding_window_500_50",
        "total_cases": len(results),
        "intact_rate": sum(1 for r in results if r["intact_in_single_chunk"]) / n,
        "context_cover_ok_rate": sum(1 for r in results if r["context_cover_ok"]) / n,
        "half_article_failure_rate": sum(
            1 for r in results if r["sliding_window_failure_reproduced"]
        )
        / n,
    }
    return {"summary": summary, "results": results}


def eval_offline_parent_child(cases: list[dict]) -> dict:
    from app.rag.parent_child_splitter import split_document

    doc_cache: dict[str, str] = {}
    results = []
    for case in cases:
        fn = case["source_file"]
        if fn not in doc_cache:
            doc_cache[fn] = (SOURCES / fn).read_text(encoding="utf-8")
        text = doc_cache[fn]
        full = case["expected_full_article"]
        hooks = case["must_include_hooks"]
        anchor = case["must_include_anchor"]
        split = split_document(text, source_file=fn)
        children = [
            {"index": i, "text": c.text, "parent_id": c.parent_id}
            for i, c in enumerate(split.children)
        ]
        parent_map = {p.parent_id: p.text for p in split.parents}
        intact = any(full in c["text"] for c in children)
        ranked = sorted(children, key=lambda c: _score(c["text"], hooks), reverse=True)
        top = ranked[0] if ranked else None
        top_score = _score(top["text"], hooks) if top else 0
        parent_text = parent_map.get(top["parent_id"], "") if top else ""
        parent_full = bool(parent_text and full in parent_text)
        parent_anchor = bool(parent_text and anchor and anchor in parent_text)
        cover_ok = bool(top and top_score > 0 and parent_full and parent_anchor)
        half_fail = bool(top and top_score > 0 and (not parent_full or not parent_anchor))
        results.append(
            {
                "id": case["id"],
                "query": case["query"],
                "source_file": fn,
                "intact_in_single_child": intact,
                "top_child_has_full_article": bool(top and full in top["text"]),
                "top_child_has_anchor": bool(top and anchor and anchor in top["text"]),
                "parent_has_full_article": parent_full,
                "parent_has_anchor": parent_anchor,
                "context_cover_ok": cover_ok,
                "half_article_failure": half_fail,
                "parent_len": len(parent_text),
                "injected_preview": (parent_text[:120] + "…") if parent_text else "",
            }
        )

    n = len(results) or 1
    summary = {
        "strategy": "article_child_section_parent",
        "total_cases": len(results),
        "intact_rate": sum(1 for r in results if r["intact_in_single_child"]) / n,
        "context_cover_ok_rate": sum(1 for r in results if r["context_cover_ok"]) / n,
        "half_article_failure_rate": sum(1 for r in results if r["half_article_failure"]) / n,
    }
    return {"summary": summary, "results": results}


def _embed_upsert(col, embed, ids, docs, metas, batch: int = 10):
    for i in range(0, len(docs), batch):
        sl = slice(i, i + batch)
        vecs = embed.embed_documents(docs[sl])
        col.upsert(ids=ids[sl], embeddings=vecs, documents=docs[sl], metadatas=metas[sl])


def eval_retrieve_ab(cases: list[dict]) -> dict | None:
    """独立 chroma：固定窗口 vs 父子(child检索+parent回填)。"""
    if os.environ.get("AB_SKIP_RETRIEVE"):
        print("[ab] AB_SKIP_RETRIEVE=1，跳过真实向量检索")
        return None

    try:
        import chromadb
        from langchain_openai import OpenAIEmbeddings
        from app.config import settings
        from eval.chunk_boundary_suite.chunk_utils import chunk_text
        from app.rag.parent_child_splitter import split_document
    except Exception as e:
        print(f"[ab] 检索探针导入失败，跳过: {e}")
        return None

    if not settings.embed_api_key:
        print("[ab] 未配置 embed_api_key，跳过真实向量检索")
        return None

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    for name in ("ab_fixed", "ab_parent_child"):
        try:
            client.delete_collection(name)
        except Exception:
            pass
    col_fixed = client.get_or_create_collection("ab_fixed")
    col_pc = client.get_or_create_collection("ab_parent_child")

    embed = OpenAIEmbeddings(
        model=settings.embedding_model,
        api_key=settings.embed_api_key,
        base_url=settings.embed_base_url,
        check_embedding_ctx_length=False,
        chunk_size=10,
    )

    # 建固定窗口索引
    f_ids, f_docs, f_metas = [], [], []
    for fp in sorted(SOURCES.glob("*.md")):
        text = fp.read_text(encoding="utf-8")
        for c in chunk_text(text):
            f_ids.append(f"{fp.stem}_{c['index']}")
            f_docs.append(c["text"])
            f_metas.append({"source": fp.name, "strategy": "fixed"})
    print(f"[ab] index fixed chunks={len(f_docs)}")
    _embed_upsert(col_fixed, embed, f_ids, f_docs, f_metas)

    # 建父子：只索引 child，meta 带 parent_id；parent 文本放本地 map
    parent_store: dict[str, str] = {}
    p_ids, p_docs, p_metas = [], [], []
    for fp in sorted(SOURCES.glob("*.md")):
        text = fp.read_text(encoding="utf-8")
        split = split_document(text, source_file=fp.name)
        for p in split.parents:
            parent_store[p.parent_id] = p.text
        for c in split.children:
            p_ids.append(c.child_id)
            p_docs.append(c.text)
            p_metas.append(
                {
                    "source": fp.name,
                    "parent_id": c.parent_id,
                    "strategy": c.strategy,
                    "article_no": c.article_no or "",
                }
            )
    print(f"[ab] index parent-child children={len(p_docs)} parents={len(parent_store)}")
    _embed_upsert(col_pc, embed, p_ids, p_docs, p_metas)

    results = []
    for case in cases:
        q = case["query"]
        full = case["expected_full_article"]
        anchor = case["must_include_anchor"]
        vec = embed.embed_query(q)

        def _cover(texts: list[str]) -> dict:
            joined_ok = any(
                (full in t) and (bool(anchor) and anchor in t) for t in texts if t
            )
            return {
                "context_cover_ok": joined_ok,
                "has_full": any(full in t for t in texts if t),
                "has_anchor": any(bool(anchor) and anchor in t for t in texts if t),
                "preview": ((texts[0][:100] + "…") if texts and texts[0] else ""),
                "num_injected": len(texts),
            }

        # fixed: 取 top-3 chunk（对齐线上多片段注入）
        hf = col_fixed.query(query_embeddings=[vec], n_results=3)
        f_docs = (hf.get("documents") or [[]])[0] or []
        f_stats = _cover(list(f_docs))

        # parent-child: top-5 child → 按 parent_id 去重回填，取最多 3 个 parent
        hp = col_pc.query(query_embeddings=[vec], n_results=5)
        c_docs = (hp.get("documents") or [[]])[0] or []
        c_metas = (hp.get("metadatas") or [[]])[0] or []
        parents: list[str] = []
        seen = set()
        for doc, meta in zip(c_docs, c_metas):
            pid = (meta or {}).get("parent_id") or ""
            key = pid or doc[:40]
            if key in seen:
                continue
            seen.add(key)
            parents.append(parent_store.get(pid, doc) if pid else doc)
            if len(parents) >= 3:
                break
        p_stats = _cover(parents)
        p_stats["child_has_full"] = any(full in d for d in c_docs if d)

        results.append(
            {
                "id": case["id"],
                "query": q,
                "source_file": case["source_file"],
                "fixed": f_stats,
                "parent_child": p_stats,
                "improved": (not f_stats["context_cover_ok"]) and p_stats["context_cover_ok"],
            }
        )

    n = len(results) or 1
    summary = {
        "total_cases": len(results),
        "fixed_context_cover_ok_rate": sum(1 for r in results if r["fixed"]["context_cover_ok"]) / n,
        "parent_child_context_cover_ok_rate": sum(
            1 for r in results if r["parent_child"]["context_cover_ok"]
        )
        / n,
        "improved_case_rate": sum(1 for r in results if r["improved"]) / n,
        "fixed_still_fail": sum(1 for r in results if not r["fixed"]["context_cover_ok"]),
        "parent_child_still_fail": sum(
            1 for r in results if not r["parent_child"]["context_cover_ok"]
        ),
    }
    return {"summary": summary, "results": results}


def _write_markdown(report: dict, path: Path) -> None:
    off_f = report["offline"]["fixed"]["summary"]
    off_p = report["offline"]["parent_child"]["summary"]
    lines = [
        "# 父子切分 vs 固定窗口 A/B 对比报告",
        "",
        f"- 生成时间: {report.get('generated_at')}",
        f"- 用例数: {report.get('total_cases')}",
        f"- 套件: `eval/chunk_boundary_suite`（对抗法规 13 篇 × 3 问法）",
        "",
        "## 一、离线切分完整性（不调 embedding）",
        "",
        "| 指标 | 固定窗口 500/50 | 父子 Child→Parent | 变化 |",
        "|---|---:|---:|---:|",
        f"| 单块含完整条款率 | {off_f['intact_rate']:.1%} | {off_p['intact_rate']:.1%} | "
        f"{off_p['intact_rate']-off_f['intact_rate']:+.1%} |",
        f"| 注入上下文覆盖完整条款+锚点 | {off_f['context_cover_ok_rate']:.1%} | "
        f"{off_p['context_cover_ok_rate']:.1%} | "
        f"{off_p['context_cover_ok_rate']-off_f['context_cover_ok_rate']:+.1%} |",
        f"| 半条失败率 | {off_f['half_article_failure_rate']:.1%} | "
        f"{off_p['half_article_failure_rate']:.1%} | "
        f"{off_p['half_article_failure_rate']-off_f['half_article_failure_rate']:+.1%} |",
        "",
    ]
    retr = report.get("retrieve")
    if retr:
        rs = retr["summary"]
        lines += [
            "## 二、真实向量检索（独立 chroma，child 命中后回填 parent）",
            "",
            "| 指标 | 固定窗口 | 父子 |",
            "|---|---:|---:|",
            f"| 注入上下文覆盖完整条款+锚点 | {rs['fixed_context_cover_ok_rate']:.1%} | "
            f"{rs['parent_child_context_cover_ok_rate']:.1%} |",
            f"| 仍失败用例数 | {rs['fixed_still_fail']} | {rs['parent_child_still_fail']} |",
            f"| 相对固定窗口改善比例 | - | {rs['improved_case_rate']:.1%} |",
            "",
        ]
    else:
        lines += ["## 二、真实向量检索", "", "_本次跳过（无 embed key 或设置了 AB_SKIP_RETRIEVE）_", ""]

    lines += [
        "## 三、结论门禁",
        "",
        f"- offline_passed: **{report['gates']['offline_passed']}** "
        f"（要求父子 context_cover≥90% 且 half_fail≤10%）",
        f"- retrieve_passed: **{report['gates'].get('retrieve_passed')}** "
        f"（若跑了检索，要求父子 cover≥80%）",
        f"- overall_passed: **{report['gates']['overall_passed']}**",
        "",
        "## 四、对照基线快照",
        "",
        f"- 固定窗口历史快照: `{BASELINE_DIR.as_posix()}`",
        f"- 本报告目录: `{REPORT_DIR.as_posix()}`",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    t0 = time.perf_counter()
    cases = _load_cases()
    print(f"[ab] cases={len(cases)}")

    print("[ab] offline fixed window ...")
    fixed = eval_offline_fixed(cases)
    print("[ab] offline parent-child ...")
    pc = eval_offline_parent_child(cases)
    print("[ab] retrieve A/B (optional) ...")
    retrieve = eval_retrieve_ab(cases)

    offline_passed = (
        pc["summary"]["context_cover_ok_rate"] >= 0.90
        and pc["summary"]["half_article_failure_rate"] <= 0.10
    )
    retrieve_passed = None
    if retrieve:
        retrieve_passed = retrieve["summary"]["parent_child_context_cover_ok_rate"] >= 0.80

    overall = offline_passed and (retrieve_passed is not False)

    report = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_cases": len(cases),
        "elapsed_ms": int((time.perf_counter() - t0) * 1000),
        "offline": {"fixed": fixed, "parent_child": pc},
        "retrieve": retrieve,
        "comparison": {
            "offline_context_cover_delta": pc["summary"]["context_cover_ok_rate"]
            - fixed["summary"]["context_cover_ok_rate"],
            "offline_failure_rate_delta": pc["summary"]["half_article_failure_rate"]
            - fixed["summary"]["half_article_failure_rate"],
            "retrieve_context_cover_delta": (
                None
                if not retrieve
                else retrieve["summary"]["parent_child_context_cover_ok_rate"]
                - retrieve["summary"]["fixed_context_cover_ok_rate"]
            ),
        },
        "gates": {
            "offline_passed": offline_passed,
            "retrieve_passed": retrieve_passed,
            "overall_passed": overall,
        },
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "ab_compare_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _write_markdown(report, REPORT_DIR / "AB_COMPARE.md")

    # 同步刷新父子快照
    snap = ROOT / "reports" / "parent_child_article_section"
    snap.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPORT_DIR / "ab_compare_report.json", snap / "ab_compare_report.json")
    shutil.copy2(REPORT_DIR / "AB_COMPARE.md", snap / "AB_COMPARE.md")

    summary_print = {
        "offline_fixed": fixed["summary"],
        "offline_parent_child": pc["summary"],
        "retrieve": None if not retrieve else retrieve["summary"],
        "comparison": report["comparison"],
        "gates": report["gates"],
        "elapsed_ms": report["elapsed_ms"],
    }
    print(json.dumps(summary_print, ensure_ascii=False, indent=2))
    print(f"[ab] report -> {REPORT_DIR / 'ab_compare_report.json'}")
    print(f"[ab] markdown -> {REPORT_DIR / 'AB_COMPARE.md'}")
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
