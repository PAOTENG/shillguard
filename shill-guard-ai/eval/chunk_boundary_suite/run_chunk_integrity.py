"""离线评测：固定窗口是否把完整条款切断，以及 query hooks 是否半条命中。

不依赖 Chroma/ES/LLM，只验证切分对抗样本本身成立。

用法（cmd）：
  cd /d d:\\project\\shill-guard-ai
  D:\\Environment\\Anaconda\\envs\\agent\\python.exe -m eval.chunk_boundary_suite.run_chunk_integrity
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from eval.chunk_boundary_suite.chunk_utils import analyze_article_split, chunk_text

ROOT = Path(__file__).resolve().parent
SOURCES = ROOT / "sources"
MANIFEST = ROOT / "manifest.json"
CASES = ROOT / "test_cases.json"
REPORT = ROOT / "reports" / "chunk_integrity_report.json"


def score_chunk_for_query(chunk_text_s: str, hooks: list[str]) -> int:
    return sum(1 for h in hooks if h in chunk_text_s)


def eval_one_case(case: dict, doc_text: str) -> dict:
    full = case["expected_full_article"]
    hooks = case["must_include_hooks"]
    anchor = case["must_include_anchor"]
    analysis = analyze_article_split(doc_text, full)
    chunks = analysis.get("chunks") or chunk_text(doc_text)

    # 模拟「关键词检索」：按 hook 命中数排序
    ranked = sorted(
        chunks,
        key=lambda c: score_chunk_for_query(c["text"], hooks),
        reverse=True,
    )
    top = ranked[0] if ranked else None
    top_score = score_chunk_for_query(top["text"], hooks) if top else 0
    top_has_full = bool(top and full in top["text"])
    top_has_anchor = bool(top and anchor and anchor in top["text"])
    top_has_all_hooks = bool(top and all(h in top["text"] for h in hooks))

    # 滑动窗口「出错」判定（本套件要复现的失败）：
    # 1) 完整条款不被任一单 chunk 完整覆盖
    # 2) top 命中块不含完整条款
    # 3) top 命中块缺锚点（后半段）
    # 4) 但 top 仍命中至少一个 hook（说明会检索到半条）
    sliding_fail = (
        analysis.get("half_hit_possible")
        and top is not None
        and top_score > 0
        and not top_has_full
        and not top_has_anchor
    )

    return {
        "id": case["id"],
        "article_id": case["article_id"],
        "query": case["query"],
        "source_file": case["source_file"],
        "straddling_boundary": analysis.get("straddling_boundary"),
        "intact_in_single_chunk": analysis.get("intact_in_single_chunk"),
        "half_hit_possible": analysis.get("half_hit_possible"),
        "top_chunk_index": top["index"] if top else None,
        "top_hook_score": top_score,
        "top_has_full_article": top_has_full,
        "top_has_anchor": top_has_anchor,
        "top_has_all_hooks": top_has_all_hooks,
        "sliding_window_failure_reproduced": sliding_fail,
        "risk": case["sliding_window_expected"]["risk"],
    }


def main() -> int:
    if not MANIFEST.exists() or not CASES.exists():
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
    fail_repro = sum(1 for r in results if r["sliding_window_failure_reproduced"])
    intact = sum(1 for r in results if r["intact_in_single_chunk"])
    half = sum(1 for r in results if r["half_hit_possible"])

    summary = {
        "total_cases": total,
        "half_hit_possible_rate": half / total if total else 0,
        "intact_in_single_chunk_rate": intact / total if total else 0,
        "sliding_window_failure_reproduced_rate": fail_repro / total if total else 0,
        "interpretation": {
            "sliding_window": (
                "failure_reproduced_rate 应尽量高（说明对抗样本成功让固定窗口半条命中）"
            ),
            "parent_child_ideal": (
                "实现父子后，同批用例的 parent 上下文应包含 full_article 与 must_include_anchor，"
                "failure_reproduced_rate 应接近 0"
            ),
        },
    }

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    payload = {"summary": summary, "results": results}
    REPORT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 72)
    print("  chunk_boundary_suite · 滑动窗口完整性报告")
    print("=" * 72)
    print(f"  用例数                              : {total}")
    print(f"  半条命中可构造率 half_hit_possible   : {summary['half_hit_possible_rate']*100:.1f}%")
    print(f"  单 chunk 完整覆盖率（应低）          : {summary['intact_in_single_chunk_rate']*100:.1f}%")
    print(f"  ★ 滑动窗口失败复现率                : {summary['sliding_window_failure_reproduced_rate']*100:.1f}%")
    print(f"  报告 → {REPORT}")
    print("=" * 72)

    # 套件自检门禁：对抗样本必须能复现失败
    ok = (
        summary["sliding_window_failure_reproduced_rate"] >= 0.80
        and summary["intact_in_single_chunk_rate"] <= 0.15
    )
    print("  套件自检:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
