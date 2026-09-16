"""
CI Gate — 评测总入口

将所有评测模块串联成一条"门禁流水线"，按顺序执行：
  Phase-1（快速·无LLM·< 30s）
    ① Cascade 评测    —— 复用 loadtest/cascade_eval.py
    ② Citation Check  —— 引用完整性（幻觉探测，预存样本）
  Phase-2（可选·有LLM·> 60s）
    ③ RAG 召回评测    —— 对 GOLDEN_RAG 运行 retrieve()
    ④ 全链路审核评测  —— 对 GOLDEN_MODERATION 跑完整 graph

快速模式（--mode fast）：只跑 Phase-1，适合 git hook / 提交前本地检查
完整模式（--mode full）：跑全部，适合 CI PR 检查

退出码约定：
  0  全部通过
  1  一个或多个 Phase 未过 CI 阈值
  2  执行时发生异常

用法（从项目根运行）：
  python eval/run_eval.py               # 默认 fast 模式
  python eval/run_eval.py --mode full   # 完整模式（需要 LLM API）
  python eval/run_eval.py --rag-k 3     # 自定义 top-k
"""
import asyncio
import sys
import time
import traceback
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ═══════════════════════════════════════════════════════════════
#  CI 阈值
# ═══════════════════════════════════════════════════════════════

THRESHOLDS = {
    "cascade_accuracy":   0.90,   # Cascade 用例正确率 ≥ 90%
    "cascade_llm_reduction": 0.50,  # LLM 减少率 ≥ 50%
    "citation_hallucinations": 0,   # 幻觉引用数 = 0
    "rag_recall":         0.75,   # RAG recall@k ≥ 75%
    "moderation_accuracy": 0.75,  # 全链路 action 准确率 ≥ 75%
}


# ═══════════════════════════════════════════════════════════════
#  Phase-1-A: Cascade 评测（复用 loadtest/cascade_eval.py）
# ═══════════════════════════════════════════════════════════════

def run_phase_cascade() -> tuple[bool, dict]:
    """
    复用 loadtest/cascade_eval.py 里的函数，直接 import + 调用。
    基线评测关闭 T2-api，避免干扰 T2-weighted 用例预期。
    """
    try:
        loadtest_path = Path(__file__).resolve().parent.parent / "loadtest"
        sys.path.insert(0, str(loadtest_path))

        from loadtest.cascade_eval import load_golden_set_cases, run_one, compute_metrics
        from app.config import settings

        async def _run():
            settings.cascade_api_enabled = False
            cases = load_golden_set_cases()
            results = []
            for c in cases:
                results.append(await run_one(c))
            return compute_metrics(results)

        metrics = asyncio.run(_run())

        accuracy = metrics.get("accuracy", 0.0)
        llm_reduction = metrics.get("llm_reduction", 0.0)
        pass_count = metrics.get("pass_count", 0)
        total = metrics.get("total", 0)

        accuracy_ok = accuracy >= THRESHOLDS["cascade_accuracy"]
        reduction_ok = llm_reduction >= THRESHOLDS["cascade_llm_reduction"]
        passed = accuracy_ok and reduction_ok

        return passed, {
            "total": total,
            "pass_count": pass_count,
            "accuracy": accuracy,
            "llm_reduction": llm_reduction,
            "accuracy_ok": accuracy_ok,
            "reduction_ok": reduction_ok,
            "avg_ms": metrics.get("avg_ms", 0),
            "p95_ms": metrics.get("p95_ms", 0),
            "false_violation": metrics.get("false_violation", 0),
            "false_normal": metrics.get("false_normal", 0),
        }
    except Exception as e:
        return False, {"error": str(e), "traceback": traceback.format_exc()}


# ═══════════════════════════════════════════════════════════════
#  Phase-1-B: Citation Check
# ═══════════════════════════════════════════════════════════════

def run_phase_citation() -> tuple[bool, dict]:
    try:
        from eval.citation_check import run_citation_eval, EVIDENCE_SAMPLES
        summary = run_citation_eval(EVIDENCE_SAMPLES)
        passed = summary["real_hallucinations"] <= THRESHOLDS["citation_hallucinations"]
        return passed, summary
    except Exception as e:
        return False, {"error": str(e), "traceback": traceback.format_exc()}


# ═══════════════════════════════════════════════════════════════
#  Phase-2-A: RAG 召回评测
# ═══════════════════════════════════════════════════════════════

async def run_phase_rag(k: int = 5) -> tuple[bool, dict]:
    try:
        from eval.rag_eval import run_rag_eval
        from eval.golden_set import GOLDEN_RAG
        summary = await run_rag_eval(GOLDEN_RAG, k=k)
        passed = summary["recall_k"] >= THRESHOLDS["rag_recall"]
        return passed, summary
    except Exception as e:
        return False, {"error": str(e), "traceback": traceback.format_exc()}


# ═══════════════════════════════════════════════════════════════
#  Phase-2-B: 全链路审核评测
# ═══════════════════════════════════════════════════════════════

async def run_phase_moderation() -> tuple[bool, dict]:
    try:
        from eval.moderation_eval import run_moderation_eval
        from eval.golden_set import GOLDEN_MODERATION
        summary = await run_moderation_eval(GOLDEN_MODERATION)
        passed = summary["action_accuracy"] >= THRESHOLDS["moderation_accuracy"]
        return passed, summary
    except Exception as e:
        return False, {"error": str(e), "traceback": traceback.format_exc()}


# ═══════════════════════════════════════════════════════════════
#  结果打印辅助
# ═══════════════════════════════════════════════════════════════

def _status(ok: bool) -> str:
    return "[PASS]" if ok else "[FAIL]"


def print_phase_result(name: str, passed: bool, detail: dict):
    if "error" in detail:
        print(f"  {name:<30} [ERROR] {detail['error'][:60]}")
        if "traceback" in detail:
            for line in detail["traceback"].splitlines()[-5:]:
                print(f"    {line}")
        return

    print(f"  {name:<30} {_status(passed)}")


# ═══════════════════════════════════════════════════════════════
#  主流程
# ═══════════════════════════════════════════════════════════════

async def _run_all(mode: str, rag_k: int):
    overall_start = time.perf_counter()
    phase_results = {}
    all_passed = True

    print("\n" + "=" * 72)
    print(f"  ShillGuard Eval CI Gate  (mode={mode})")
    print(f"  阈值: cascade≥{THRESHOLDS['cascade_accuracy']:.0%}  "
          f"llm_reduction≥{THRESHOLDS['cascade_llm_reduction']:.0%}  "
          f"幻觉=0  rag_recall≥{THRESHOLDS['rag_recall']:.0%}  "
          f"moderation≥{THRESHOLDS['moderation_accuracy']:.0%}")
    print("=" * 72)

    # ── Phase-1: 快速·无LLM ──────────────────────────────────
    print("\n【Phase-1  快速评测（无LLM）】")

    t = time.perf_counter()
    print(f"  1/4  Cascade 评测 ...")
    cascade_ok, cascade_det = run_phase_cascade()
    print(f"       accuracy={cascade_det.get('accuracy', 0):.1%}  "
          f"llm_reduction={cascade_det.get('llm_reduction', 0):.1%}  "
          f"({time.perf_counter() - t:.1f}s)")
    print_phase_result("Cascade 准确率", cascade_det.get("accuracy_ok", False), cascade_det)
    print_phase_result("Cascade LLM减少率", cascade_det.get("reduction_ok", False), cascade_det)
    if not cascade_ok:
        all_passed = False
    phase_results["cascade"] = {"passed": cascade_ok, "detail": cascade_det}

    t = time.perf_counter()
    print(f"\n  2/4  Citation 引用完整性检查 ...")
    citation_ok, citation_det = run_phase_citation()
    halluc = citation_det.get("real_hallucinations", "?")
    print(f"       幻觉数={halluc}  detector_accuracy={citation_det.get('detector_accuracy', 0):.0%}  "
          f"({time.perf_counter() - t:.1f}s)")
    print_phase_result("Citation 幻觉=0", citation_ok, citation_det)
    if not citation_ok:
        all_passed = False
    phase_results["citation"] = {"passed": citation_ok, "detail": citation_det}

    # ── Phase-2: LLM-dependent（仅 full 模式）────────────────
    if mode == "full":
        print("\n【Phase-2  完整评测（含LLM，可能较慢）】")

        t = time.perf_counter()
        print(f"  3/4  RAG 召回评测 (top-{rag_k}) ...")
        rag_ok, rag_det = await run_phase_rag(rag_k)
        recall = rag_det.get("recall_k", 0)
        print(f"       recall@{rag_k}={recall:.1%}  avg_precision={rag_det.get('avg_precision', 0):.1%}  "
              f"({time.perf_counter() - t:.1f}s)")
        print_phase_result(f"RAG recall@{rag_k}", rag_ok, rag_det)
        if not rag_ok:
            all_passed = False
        phase_results["rag"] = {"passed": rag_ok, "detail": rag_det}

        t = time.perf_counter()
        print(f"\n  4/4  全链路审核评测 ...")
        mod_ok, mod_det = await run_phase_moderation()
        action_acc = mod_det.get("action_accuracy", 0)
        print(f"       action_accuracy={action_acc:.1%}  "
              f"score_mae={mod_det.get('score_mae', 0):.3f}  "
              f"({time.perf_counter() - t:.1f}s)")
        print_phase_result("全链路 action_accuracy", mod_ok, mod_det)
        if not mod_ok:
            all_passed = False
        phase_results["moderation"] = {"passed": mod_ok, "detail": mod_det}
    else:
        print("\n  3/4  RAG 召回评测         [SKIP] (--mode fast)")
        print("  4/4  全链路审核评测         [SKIP] (--mode fast)")

    # ── 最终汇总 ─────────────────────────────────────────────
    elapsed = time.perf_counter() - overall_start
    print("\n" + "═" * 72)
    print("  SUMMARY")
    print("═" * 72)

    rows = [
        ("Cascade",      phase_results.get("cascade", {}).get("passed"), True),
        ("Citation",     phase_results.get("citation", {}).get("passed"), True),
        ("RAG Recall",   phase_results.get("rag", {}).get("passed"),      mode == "full"),
        ("Moderation",   phase_results.get("moderation", {}).get("passed"), mode == "full"),
    ]
    for label, ok, active in rows:
        if active:
            status_str = _status(ok) if ok is not None else "[SKIP]"
            print(f"  {label:<20} {status_str}")
        else:
            print(f"  {label:<20} [SKIP]")

    final = "ALL PASSED" if all_passed else "FAILED"
    print(f"\n  总耗时: {elapsed:.1f}s")
    print(f"  最终结果: [{final}]")
    print("═" * 72 + "\n")
    return all_passed


def main():
    import argparse
    ap = argparse.ArgumentParser(description="ShillGuard Eval CI Gate")
    ap.add_argument("--mode", choices=["fast", "full"], default="fast",
                    help="fast=无LLM快速检查（默认），full=含LLM完整检查")
    ap.add_argument("--rag-k", type=int, default=5,
                    help="RAG top-k（默认5）")
    args = ap.parse_args()

    try:
        passed = asyncio.run(_run_all(args.mode, args.rag_k))
        sys.exit(0 if passed else 1)
    except KeyboardInterrupt:
        print("\n[中断] 评测已取消")
        sys.exit(2)
    except Exception as e:
        print(f"\n[FATAL] {e}")
        traceback.print_exc()
        sys.exit(2)


if __name__ == "__main__":
    main()
