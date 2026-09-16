"""
全链路审核评测（LLM-dependent）

对 GOLDEN_MODERATION 里每条 ModerationCase 跑完整 graph：
  pre_filter → [T3路径] classify → retrieve → judge → evidence → action

评测指标：
  action_accuracy  = 最终 action 与期望一致的比例
  score_mae        = anomaly_score 与期望区间中点的均绝对误差
  citation_rate    = evidence 里法条引用合法率（复用 citation_check）
  laws_coverage    = expected_laws_contain 里关键词出现在 evidence 的比例

注意：此模块会消耗 LLM API 调用，串行运行避免 429 限流。

用法（从项目根运行）：
  python eval/moderation_eval.py
  python eval/moderation_eval.py --limit 5    # 只跑前5条（调试省钱）
"""
import asyncio
import sys
import time
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agents.moderation.graph import build_graph
from eval.golden_set import GOLDEN_MODERATION, ModerationCase
from eval.citation_check import check_evidence


# ═══════════════════════════════════════════════════════════════
#  单条用例全链路评测
# ═══════════════════════════════════════════════════════════════

async def eval_one_moderation(case: ModerationCase, graph) -> dict:
    """运行完整审核 graph，把输出与期望值逐项比对。"""
    initial_state = {
        "content_list": case.content_list,
        "report_category": case.report_category,
    }

    t0 = time.perf_counter()
    try:
        final_state = await graph.ainvoke(initial_state)
    except Exception as e:
        return {
            "id": case.id,
            "description": case.description,
            "error": str(e),
            "action_match": False,
            "score_in_range": False,
            "citation_passed": True,
            "laws_covered": [],
            "laws_missing": [],
            "expected_action": case.expected_action,
            "actual_action": None,
            "expected_score_range": f"[{case.expected_score_min}, {case.expected_score_max}]",
            "actual_score": None,
            "tier": None,
            "ms": (time.perf_counter() - t0) * 1000,
            "citation_detail": None,
        }
    elapsed_ms = (time.perf_counter() - t0) * 1000

    actual_action = final_state.get("action", "none")
    actual_score = float(final_state.get("anomaly_score", 0.0))
    evidence_detail = final_state.get("evidence_detail", "")
    violated_laws = final_state.get("violated_laws", [])
    tier = final_state.get("filter_tier", "T3-llm")

    # ── action 准确率 ──────────────────────────────────────
    action_match = (actual_action == case.expected_action)

    # ── score 区间检查 ─────────────────────────────────────
    score_in_range = (case.expected_score_min <= actual_score <= case.expected_score_max)

    # ── citation 完整性（复用 citation_check）──────────────
    citation_result = None
    citation_passed = True
    if evidence_detail:
        citation_result = check_evidence(evidence_detail, violated_laws)
        citation_passed = citation_result["passed"]

    # ── laws 覆盖度（期望关键词是否出现在 evidence 里）────
    laws_covered = []
    laws_missing = []
    for kw in case.expected_laws_contain:
        if kw in evidence_detail:
            laws_covered.append(kw)
        else:
            laws_missing.append(kw)

    return {
        "id": case.id,
        "description": case.description,
        "error": None,
        "action_match": action_match,
        "score_in_range": score_in_range,
        "citation_passed": citation_passed,
        "laws_covered": laws_covered,
        "laws_missing": laws_missing,
        "expected_action": case.expected_action,
        "actual_action": actual_action,
        "expected_score_range": f"[{case.expected_score_min}, {case.expected_score_max}]",
        "actual_score": actual_score,
        "tier": tier,
        "ms": elapsed_ms,
        "citation_detail": citation_result,
    }


# ═══════════════════════════════════════════════════════════════
#  批量评测（串行，避免并发触发 LLM 限流）
# ═══════════════════════════════════════════════════════════════

async def run_moderation_eval(cases: list[ModerationCase]) -> dict:
    """串行运行所有 ModerationCase，汇总指标。"""
    graph = build_graph()
    results = []

    for case in cases:
        print(f"  [{case.id}] {case.content_list[0][:35]}...")
        r = await eval_one_moderation(case, graph)
        status = "OK " if (r["action_match"] and not r.get("error")) else "ERR"
        # 原写法（有bug）：f-string 格式化说明符里不能内嵌条件表达式，Python 会把
        # '.2f if r[...] is not None else '?'' 整体当成格式符，抛 ValueError：
        #   f"score={r['actual_score']:.2f if r['actual_score'] is not None else '?'} "
        score_str = f"{r['actual_score']:.2f}" if r["actual_score"] is not None else "?"
        print(f"         → {status} action={r['actual_action']} "
              f"score={score_str} "
              f"tier={r['tier']}  {r['ms']:.0f}ms")
        results.append(r)

    total = len(results)
    errors = sum(1 for r in results if r.get("error"))
    valid = total - errors

    action_correct = sum(1 for r in results
                         if r["action_match"] and not r.get("error"))
    score_correct = sum(1 for r in results
                        if r["score_in_range"] and not r.get("error"))
    citation_ok = sum(1 for r in results
                      if r["citation_passed"] and not r.get("error"))

    action_accuracy = action_correct / valid if valid > 0 else 0.0
    score_accuracy = score_correct / valid if valid > 0 else 0.0
    citation_rate = citation_ok / valid if valid > 0 else 1.0

    # MAE：实际 score 与期望区间中点的平均绝对误差
    maes = []
    for i, r in enumerate(results):
        if not r.get("error") and r["actual_score"] is not None:
            mid = (cases[i].expected_score_min + cases[i].expected_score_max) / 2
            maes.append(abs(r["actual_score"] - mid))
    score_mae = sum(maes) / len(maes) if maes else 0.0

    return {
        "results": results,
        "total": total,
        "valid": valid,
        "errors": errors,
        "action_correct": action_correct,
        "score_correct": score_correct,
        "action_accuracy": action_accuracy,
        "score_accuracy": score_accuracy,
        "score_mae": score_mae,
        "citation_rate": citation_rate,
    }


# ═══════════════════════════════════════════════════════════════
#  报告打印
# ═══════════════════════════════════════════════════════════════

def print_moderation_report(summary: dict) -> bool:
    """打印评测报告，返回是否通过 CI（action_accuracy ≥ 75%）。"""
    results = summary["results"]

    print("\n" + "=" * 72)
    print("  全链路审核评测报告（LLM-dependent）")
    print("=" * 72)

    for r in results:
        if r.get("error"):
            print(f"\n  {r['id']}  [ERROR] {r['error'][:60]}")
            continue

        a_ok = "✓" if r["action_match"] else "✗"
        s_ok = "✓" if r["score_in_range"] else "✗"
        c_ok = "✓" if r["citation_passed"] else "✗"
        print(f"\n  {r['id']}  [{r['tier']:<14}]  {r['ms']:.0f}ms")
        print(f"    action   {a_ok}: 期望={r['expected_action']:<14} "
              f"实际={r['actual_action']}")
        print(f"    score    {s_ok}: 期望{r['expected_score_range']:<20} "
              f"实际={r['actual_score']:.2f}")
        print(f"    citation {c_ok}")
        if r["laws_missing"]:
            print(f"    ! 法条缺失: {r['laws_missing']}")
        if r["citation_detail"] and r["citation_detail"]["hallucinated"]:
            print(f"    ! 幻觉引用: {r['citation_detail']['hallucinated']}")

    print("\n" + "─" * 72)
    print(f"  用例总数 / 有效 / 错误 : "
          f"{summary['total']} / {summary['valid']} / {summary['errors']}")
    print(f"  ★ action accuracy    : {summary['action_accuracy'] * 100:.1f}%  "
          f"({summary['action_correct']}/{summary['valid']})")
    print(f"  ★ score accuracy     : {summary['score_accuracy'] * 100:.1f}%  "
          f"(在期望区间内)")
    print(f"  ★ score MAE          : {summary['score_mae']:.3f}")
    print(f"  ★ citation rate      : {summary['citation_rate'] * 100:.1f}%")

    threshold = 0.75
    passed = summary["action_accuracy"] >= threshold
    status = "PASS" if passed else "FAIL"
    print(f"\n  CI 门禁: action_accuracy = {summary['action_accuracy'] * 100:.1f}% "
          f"(阈值 ≥ {threshold * 100:.0f}%)  [{status}]")
    print("=" * 72)
    return passed


# ═══════════════════════════════════════════════════════════════
#  独立运行入口
# ═══════════════════════════════════════════════════════════════

def main():
    import argparse
    ap = argparse.ArgumentParser(description="全链路审核评测（含LLM）")
    ap.add_argument("--limit", type=int, default=None,
                    help="只跑前 N 条（调试/省钱用）")
    args = ap.parse_args()

    cases = GOLDEN_MODERATION[:args.limit] if args.limit else GOLDEN_MODERATION
    print(f"开始全链路审核评测（{len(cases)} 条用例，会调用 LLM）...")

    summary = asyncio.run(run_moderation_eval(cases))
    passed = print_moderation_report(summary)
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
