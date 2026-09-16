"""
ShillGuard-AgentEval v0 — 领域 Agent 主验收入口

任务分层（见 cases/manifest.json）：
  E1  单 MCP 工具
  E2  多工具编排（查法→审核、打分→证据）
  E3  级联路由（pre_filter，无 LLM）

用法（项目根，cmd）：
  D:\\Environment\\Anaconda\\envs\\agent\\python.exe -m eval.shillguard_agent_eval.run_agent_eval
  D:\\Environment\\Anaconda\\envs\\agent\\python.exe -m eval.shillguard_agent_eval.run_agent_eval --mode fast
  D:\\Environment\\Anaconda\\envs\\agent\\python.exe -m eval.shillguard_agent_eval.run_agent_eval --suite e1 --mode full
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

if sys.platform == "win32":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from eval.shillguard_agent_eval.runners.bootstrap import bootstrap  # noqa: E402

bootstrap()

from eval.shillguard_agent_eval.runners.mcp_runner import (  # noqa: E402
    run_cascade_case,
    run_mcp_tool,
    run_pipeline,
)
from eval.shillguard_agent_eval.verifiers.checks import verify_task_result  # noqa: E402

_MANIFEST = Path(__file__).resolve().parent / "cases" / "manifest.json"
_REPORTS = Path(__file__).resolve().parent / "reports"


def load_manifest() -> dict:
    with _MANIFEST.open(encoding="utf-8") as f:
        return json.load(f)


def filter_tasks(manifest: dict, suite: str | None, mode: str) -> list[dict]:
    tasks = manifest.get("tasks", [])
    if suite and suite != "all":
        tasks = [t for t in tasks if t.get("suite") == suite]
    if mode == "fast":
        tasks = [t for t in tasks if t.get("fast", False)]
    return tasks


async def run_one_task(task: dict) -> dict:
    suite = task.get("suite", "e1")
    t0 = time.perf_counter()

    if suite == "e3":
        cid = task.get("cascade_id", "")
        outcome = {"cascade": await run_cascade_case(cid)}
    elif suite == "e2":
        pname = task.get("pipeline", "")
        outcome = await run_pipeline(pname, task.get("input", {}))
    else:
        tool = task.get("tool", "")
        outcome = await run_mcp_tool(tool, task.get("input", {}))

    verification = verify_task_result(task, outcome)
    return {
        "id": task.get("id"),
        "suite": suite,
        "description": task.get("description", ""),
        "passed": verification["passed"],
        "reasons": verification["reasons"],
        "ms": (time.perf_counter() - t0) * 1000,
        "outcome": outcome,
    }


def summarize(results: list[dict], thresholds: dict) -> dict:
    by_suite: dict[str, list[dict]] = {}
    for r in results:
        by_suite.setdefault(r["suite"], []).append(r)

    summary: dict = {"suites": {}, "overall_pass_rate": 0.0, "total": len(results), "passed": 0}
    for suite, rows in by_suite.items():
        n = len(rows)
        p = sum(1 for x in rows if x["passed"])
        rate = p / n if n else 0.0
        key = f"{suite}_pass_rate"
        threshold = thresholds.get(key, 0.75)
        summary["suites"][suite] = {
            "total": n,
            "passed": p,
            "pass_rate": rate,
            "threshold": threshold,
            "ok": rate >= threshold if n else True,
        }
        summary["passed"] += p

    summary["overall_pass_rate"] = summary["passed"] / summary["total"] if summary["total"] else 0.0
    summary["all_ok"] = all(s["ok"] for s in summary["suites"].values())
    return summary


def write_report(results: list[dict], summary: dict, mode: str, suite: str) -> Path:
    _REPORTS.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = _REPORTS / f"agent_eval_{ts}.json"
    payload = {
        "generated_at": ts,
        "mode": mode,
        "suite_filter": suite,
        "summary": summary,
        "results": results,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    md_path = _REPORTS / f"agent_eval_{ts}.md"
    lines = [
        f"# ShillGuard-AgentEval Report ({ts})",
        "",
        f"- mode: `{mode}`",
        f"- suite: `{suite}`",
        f"- overall pass@1: **{summary['overall_pass_rate']:.1%}** ({summary['passed']}/{summary['total']})",
        "",
        "## By suite",
        "",
    ]
    for sname, s in summary["suites"].items():
        flag = "PASS" if s["ok"] else "FAIL"
        lines.append(
            f"- **{sname.upper()}** [{flag}] {s['passed']}/{s['total']} "
            f"({s['pass_rate']:.1%}, threshold {s['threshold']:.0%})"
        )
    lines.extend(["", "## Failed tasks", ""])
    failed = [r for r in results if not r["passed"]]
    if not failed:
        lines.append("_none_")
    else:
        for r in failed:
            lines.append(f"- `{r['id']}`: {'; '.join(r['reasons'])}")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


async def main_async(args: argparse.Namespace) -> int:
    manifest = load_manifest()
    thresholds = manifest.get("thresholds", {})
    tasks = filter_tasks(manifest, args.suite, args.mode)

    print("\n" + "=" * 72)
    print(f"  ShillGuard-AgentEval v0  (mode={args.mode}, suite={args.suite}, tasks={len(tasks)})")
    print("=" * 72)

    results: list[dict] = []
    for i, task in enumerate(tasks, 1):
        print(f"\n[{i}/{len(tasks)}] {task.get('id')} — {task.get('description', '')[:50]}")
        row = await run_one_task(task)
        results.append(row)
        status = "PASS" if row["passed"] else "FAIL"
        print(f"  [{status}] {row['ms']:.0f}ms — {'; '.join(row['reasons'][:3])}")

    summary = summarize(results, thresholds)
    report_path = write_report(results, summary, args.mode, args.suite)

    print("\n" + "═" * 72)
    print("  SUMMARY")
    for sname, s in summary["suites"].items():
        print(
            f"  {sname.upper():<6} {s['passed']}/{s['total']} "
            f"({s['pass_rate']:.1%}) threshold {s['threshold']:.0%} "
            f"{'[OK]' if s['ok'] else '[FAIL]'}"
        )
    print(f"\n  overall pass@1: {summary['overall_pass_rate']:.1%}")
    print(f"  report: {report_path}")
    print(f"  markdown: {report_path.with_suffix('.md')}")
    print("═" * 72 + "\n")

    return 0 if summary["all_ok"] else 1


def main() -> None:
    ap = argparse.ArgumentParser(description="ShillGuard-AgentEval v0")
    ap.add_argument("--mode", choices=["fast", "full"], default="fast",
                    help="fast=仅无LLM任务(E1-RAG+E3)，full=含审核/检测/编排")
    ap.add_argument("--suite", choices=["all", "e1", "e2", "e3"], default="all")
    args = ap.parse_args()
    try:
        code = asyncio.run(main_async(args))
        sys.exit(code)
    except KeyboardInterrupt:
        print("\n[中断]")
        sys.exit(2)


if __name__ == "__main__":
    main()
