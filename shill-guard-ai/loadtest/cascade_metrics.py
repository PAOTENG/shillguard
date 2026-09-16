"""级联指标离线聚合脚本：读取 router 写入的 JSONL，计算真实流量下的级联指标。

用法：
    python loadtest/cascade_metrics.py                  # 读 data/cascade_metrics.jsonl
    python loadtest/cascade_metrics.py --file xxx.jsonl
    python loadtest/cascade_metrics.py --watch          # 实时 tail（压测时边跑边看）

设计理念（简历亮点）：
  业务逻辑与观测分离 —— router 逐请求落结构化日志（事件），本脚本离线聚合（指标）。
  这与 Langfuse / Prometheus / ELK 同构：先落事件，再算指标。
  指标是跨请求聚合统计，不该塞进 per-request 的 LangGraph node 里。
"""
import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DEFAULT_LOG = Path("data/cascade_metrics.jsonl")

_TIER_ORDER = ["T1-blacklist", "T1-whitelist", "T2-api", "T2-weighted", "T3-llm"]
_VERDICT_ORDER = ["clear_violation", "clear_normal", "ambiguous"]
_ACTION_ORDER = ["auto_mute", "manual_review", "none"]
_CATEGORY_NAMES = {0: "广告", 1: "违法", 2: "辱骂", 3: "涉黄", 4: "其他"}


def load_records(path: Path) -> list:
    """逐行读取 JSONL；每行一条 moderation router 落盘的级联事件。"""
    if not path.exists():
        return []
    records = []
    with path.open("r", encoding="utf-8") as f:
        for ln, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                print(f"[warn] 第{ln}行JSON解析失败，跳过")
    return records


def compute_metrics(records: list) -> dict:
    """从真实流量 JSONL 聚合级联 KPI（与 cascade_eval.py 离线黄金集互补）。

    reduction = (total - T3-llm) / total：生产环境 LLM 调用减少率
    """
    total = len(records)
    if total == 0:
        return {"total": 0}

    tier_dist = Counter(r.get("filter_tier", "T3-llm") for r in records)
    verdict_dist = Counter(r.get("tier_verdict", "ambiguous") for r in records)
    action_dist = Counter(r.get("action", "none") for r in records)
    cat_dist = Counter(r.get("report_category", -1) for r in records)

    # T3-llm = 退回 LLM；其余 = 级联拦截（无需 LLM）
    llm_calls = tier_dist.get("T3-llm", 0)
    cascaded = total - llm_calls
    reduction = cascaded / total * 100 if total else 0.0

    # T1/T2 命中的，看 LLM 是否真的没被调（evidence 跳过 = 级联生成）
    # 注意：T1-Whitelist 和 T2 也都不调 LLM（直接走 action 或 evidence模板）

    # 按 verdict 看自动处罚 vs 放行
    auto_mute = action_dist.get("auto_mute", 0)
    manual = action_dist.get("manual_review", 0)
    none = action_dist.get("none", 0)

    return {
        "total": total,
        "tier_dist": tier_dist,
        "verdict_dist": verdict_dist,
        "action_dist": action_dist,
        "cat_dist": cat_dist,
        "llm_calls": llm_calls,
        "cascaded": cascaded,
        "reduction": reduction,
        "auto_mute": auto_mute,
        "manual_review": manual,
        "none": none,
    }


def _bar(count: int, total: int, width: int = 24) -> str:
    pct = count / total * 100 if total else 0
    filled = int(pct / 100 * width)
    return "#" * filled + " " * (width - filled)


def print_report(m: dict, source: str):
    total = m["total"]
    print("\n" + "=" * 72)
    print(f"  审核级联 · 真实流量指标报告  ({source})")
    print("=" * 72)

    if total == 0:
        print("  (暂无数据)")
        print("=" * 72)
        return

    print(f"\n  请求总数          : {total}")
    print(f"  级联拦截(免LLM)   : {m['cascaded']}")
    print(f"  退回 LLM          : {m['llm_calls']}")
    print(f"  ★ LLM 调用减少率  : {m['reduction']:.1f}%")

    print("\n  【Tier 分布】(命中层级)")
    for tier in _TIER_ORDER:
        c = m["tier_dist"].get(tier, 0)
        pct = c / total * 100
        print(f"    {tier:<16} {c:>5} ({pct:5.1f}%) {_bar(c, total)}")

    print("\n  【Verdict 分布】(级联判定)")
    for v in _VERDICT_ORDER:
        c = m["verdict_dist"].get(v, 0)
        pct = c / total * 100
        print(f"    {v:<16} {c:>5} ({pct:5.1f}%) {_bar(c, total)}")

    print("\n  【Action 分布】(最终处罚)")
    for a in _ACTION_ORDER:
        c = m["action_dist"].get(a, 0)
        pct = c / total * 100
        print(f"    {a:<16} {c:>5} ({pct:5.1f}%) {_bar(c, total)}")

    print("\n  【举报分类分布】")
    for cat in sorted(m["cat_dist"].keys()):
        c = m["cat_dist"][cat]
        name = _CATEGORY_NAMES.get(cat, f"cat{cat}")
        pct = c / total * 100
        print(f"    {name:<6} ({cat})  {c:>5} ({pct:5.1f}%) {_bar(c, total)}")

    print("\n" + "=" * 72)
    print("  简历可用指标:")
    print(f"  - 级联前置过滤将 LLM 调用量降低 {m['reduction']:.1f}%")
    print(f"  - 确定性层(T1+T2)拦截占比 {(m['tier_dist'].get('T1-blacklist',0)+m['tier_dist'].get('T1-whitelist',0)+m['tier_dist'].get('T2-weighted',0))/total*100:.1f}%")
    print(f"  - 自动禁言 {m['auto_mute']} / 人工复核 {m['manual_review']} / 放行 {m['none']}")
    print("=" * 72)


def main():
    ap = argparse.ArgumentParser(description="级联指标离线聚合")
    ap.add_argument("--file", default=str(DEFAULT_LOG), help="JSONL 日志路径")
    ap.add_argument("--watch", action="store_true", help="实时 tail 模式（压测时边跑边看）")
    ap.add_argument("--interval", type=float, default=3.0, help="watch 模式刷新间隔(秒)")
    args = ap.parse_args()

    path = Path(args.file)

    if args.watch:
        print(f"[watch] 实时监控 {path}，每 {args.interval}s 刷新，Ctrl+C 退出")
        last_size = 0
        try:
            while True:
                records = load_records(path)
                m = compute_metrics(records)
                # 清屏重绘
                print("\033[2J\033[H", end="")
                print_report(m, f"watch · {path}")
                size = path.stat().st_size if path.exists() else 0
                if size != last_size:
                    last_size = size
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\n[watch] 已停止")
        return

    records = load_records(path)
    m = compute_metrics(records)
    print_report(m, str(path))


if __name__ == "__main__":
    main()
