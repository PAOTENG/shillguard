"""离线评测：父子切分是否保住完整条款（对照固定窗口基线）。

用法（cmd）：
  cd /d d:\\project\\shill-guard-ai
  D:\\Environment\\Anaconda\\envs\\agent\\python.exe -m eval.chunk_boundary_suite.run_parent_child_integrity
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from app.rag.parent_child_splitter import split_document

ROOT = Path(__file__).resolve().parent
SOURCES = ROOT / "sources"
CASES = ROOT / "test_cases.json"
REPORT = ROOT / "reports" / "parent_child_integrity_report.json"
BASELINE = ROOT / "reports" / "baseline_fixed_window_500_50" / "chunk_integrity_report.json"
SNAPSHOT_DIR = ROOT / "reports" / "parent_child_article_section"


def score_chunk_for_query(text: str, hooks: list[str]) -> int:
    return sum(1 for h in hooks if h in text)


def eval_one_case(case: dict, doc_text: str) -> dict:
    full = case["expected_full_article"]
    hooks = case["must_include_hooks"]
    anchor = case["must_include_anchor"]
    source = case["source_file"]

    result = split_document(doc_text, source_file=source)
    children = [{"index": i, "text": c.text, "parent_id": c.parent_id, "article_no": c.article_no}
                for i, c in enumerate(result.children)]
    parent_map = {p.parent_id: p.text for p in result.parents}

    intact_child = any(full in c["text"] for c in children)
    # 模拟 child 检索：按 hook 命中数排序
    ranked = sorted(
        children,
        key=lambda c: score_chunk_for_query(c["text"], hooks),
        reverse=True,
    )
    top = ranked[0] if ranked else None
    top_score = score_chunk_for_query(top["text"], hooks) if top else 0
    top_has_full = bool(top and full in top["text"])
    top_has_anchor = bool(top and anchor and anchor in top["text"])

    parent_text = parent_map.get(top["parent_id"], "") if top else ""
    parent_has_full = bool(parent_text and full in parent_text)
    parent_has_anchor = bool(parent_text and anchor and anchor in parent_text)
    parent_has_all_hooks = bool(parent_text and all(h in parent_text for h in hooks))

    # 父子成功：top child 能靠 hook 命中，且回填 parent 含完整条款+锚点
    parent_cover_ok = (
        top is not None
        and top_score > 0
        and parent_has_full
        and parent_has_anchor
    )
    # 半条失败（旧病）：命中但 parent 仍缺完整条款/锚点
    half_fail = (
        top is not None
        and top_score > 0
        and (not parent_has_full or not parent_has_anchor)
    )

    return {
        "id": case["id"],
        "article_id": case["article_id"],
        "query": case["query"],
        "source_file": source,
        "num_children": len(children),
        "num_parents": len(result.parents),
        "intact_in_single_child": intact_child,
        "top_child_index": top["index"] if top else None,
        "top_child_article_no": top.get("article_no") if top else None,
        "top_hook_score": top_score,
        "top_child_has_full_article": top_has_full,
        "top_child_has_anchor": top_has_anchor,
        "parent_has_full_article": parent_has_full,
        "parent_has_anchor": parent_has_anchor,
        "parent_has_all_hooks": parent_has_all_hooks,
        "parent_len": len(parent_text),
        "parent_cover_ok": parent_cover_ok,
        "half_article_failure": half_fail,
        "risk": case.get("sliding_window_expected", {}).get("risk"),
    }


def main() -> int:
    if not CASES.exists():
        print("请先运行 build_adversarial_docs 与 build_test_cases")
        return 2

    cases = json.loads(CASES.read_text(encoding="utf-8"))["cases"]
    doc_cache: dict[str, str] = {}
    results = []
    for case in cases:
        fn = case["source_file"]
        if fn not in doc_cache:
            doc_cache[fn] = (SOURCES / fn).read_text(encoding="utf-8")
        results.append(eval_one_case(case, doc_cache[fn]))

    total = len(results)
    intact = sum(1 for r in results if r["intact_in_single_child"])
    cover = sum(1 for r in results if r["parent_cover_ok"])
    half_fail = sum(1 for r in results if r["half_article_failure"])

    summary = {
        "strategy": "article_child_section_parent",
        "total_cases": total,
        "intact_in_single_child_rate": intact / total if total else 0,
        "parent_cover_ok_rate": cover / total if total else 0,
        "half_article_failure_rate": half_fail / total if total else 0,
    }

    baseline_summary = None
    if BASELINE.exists():
        baseline_summary = json.loads(BASELINE.read_text(encoding="utf-8")).get("summary")

    comparison = {
        "baseline_fixed_window": baseline_summary,
        "parent_child": summary,
        "delta": {
            "intact_rate": summary["intact_in_single_child_rate"]
            - (baseline_summary or {}).get("intact_in_single_chunk_rate", 0),
            "failure_rate_drop": (baseline_summary or {}).get(
                "sliding_window_failure_reproduced_rate", 0
            )
            - summary["half_article_failure_rate"],
        },
    }

    # 门禁：parent 覆盖率 ≥ 0.90，半条失败 ≤ 0.10
    passed = (
        summary["parent_cover_ok_rate"] >= 0.90
        and summary["half_article_failure_rate"] <= 0.10
    )

    report = {
        "summary": summary,
        "comparison": comparison,
        "passed": passed,
        "results": results,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPORT, SNAPSHOT_DIR / "parent_child_integrity_report.json")
    (SNAPSHOT_DIR / "README.md").write_text(
        "# 父子切分评测快照\n\n"
        f"- parent_cover_ok_rate: {summary['parent_cover_ok_rate']:.3f}\n"
        f"- half_article_failure_rate: {summary['half_article_failure_rate']:.3f}\n"
        f"- intact_in_single_child_rate: {summary['intact_in_single_child_rate']:.3f}\n"
        f"- passed: {passed}\n",
        encoding="utf-8",
    )

    print(json.dumps({"summary": summary, "comparison": comparison, "passed": passed},
                     ensure_ascii=False, indent=2))
    print(f"report -> {REPORT}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
