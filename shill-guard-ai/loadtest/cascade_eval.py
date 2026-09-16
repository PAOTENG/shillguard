"""审核级联前置过滤的评测脚本：量化指标 + 用例正确性校验。

用法：
    python loadtest/cascade_eval.py                  # 默认 golden_set.json 110 条
    python loadtest/cascade_eval.py --with-api       # 110 条 + T2-api 专项 mock 用例
    python loadtest/cascade_eval.py --smoke          # 仅 13 条严格 tier 冒烟用例
    python loadtest/cascade_eval.py --no-api         # 强制关闭 T2-api（对比基线）

默认加载 loadtest/golden_set.json（110 条，与 ragas_eval 同源）。
本脚本只测 pre_filter_node（级联前置层），不调 LLM、不走 LangGraph，故速度快；
LangSmith 轨迹请用 ragas_eval.py（全链路 HTTP）或开启服务后压测。

指标：
  1. 各 tier 命中率（T1/T2-api/T2-weighted/T3-llm）
  2. LLM 调用减少率 = 1 - (退回LLM数 / 总数)
  3. 级联层安全准确率（clear_normal 不被误拦；违规不被误放）
  4. 延迟 P50/P95
"""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

# Windows 控制台默认 GBK 编码，强制 UTF-8 防止 ✓/✗ 等字符报错
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 让脚本能 import app 包（loadtest/ 在项目根下，脚本从项目根运行）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.agents.moderation.cascade import pre_filter_node

GOLDEN_SET_PATH = Path(__file__).parent / "golden_set.json"

# golden_set category → 级联层期望（非全链路 action）
# not_violation: clear_normal 类绝不能被级联判违规
# not_normal:    违规类绝不能被级联判正常
# "":            只统计 tier 分布，不做 verdict 硬匹配
_CASCADE_EXPECT_BY_CATEGORY: dict[str, str] = {
    "clear_normal": "not_violation",
    "clear_violation": "not_normal",
    "ambiguous": "",
    "borderline": "",
    "sarcasm": "",
    "coded_insult": "",
    "topic_hijack": "",
    "prompt_injection": "",
}


def load_golden_set_cases() -> list[dict]:
    """从 golden_set.json 加载 110 条，转为 cascade_eval 用例格式。"""
    raw = json.loads(GOLDEN_SET_PATH.read_text(encoding="utf-8"))
    cases = []
    for item in raw:
        cat = item["category"]
        cases.append({
            "id": item["id"],
            "content_list": [item["content"]],
            "report_category": item["report_category"],
            "golden_category": cat,
            "expect_verdict": _CASCADE_EXPECT_BY_CATEGORY.get(cat, ""),
            "expect_tier": "",
            "desc": f"{item['id']} ({cat})",
        })
    return cases


# ═══════════════════════════════════════════════════════════════
#  冒烟用例（13 条）：严格校验 tier，用于 CI 快速回归
# ═══════════════════════════════════════════════════════════════
SMOKE_TEST_CASES: list[dict] = [
    # —— T1 黑名单应命中 (clear_violation) ——
    {
        "content_list": [
            "姐妹们别划走！最近宝妈群里都在传一个内部兼职，说是刷单兼职，"
            "每天花1小时就能日赚过千，我一开始也怀疑，后来真的到账了。"
            "零基础在家就能做，不用押金，扫码领福利进群还有导师一对一带，"
            "名额有限先到先得，感兴趣的私我了解详情，错过等半年。"
        ],
        "report_category": 1,  # 违法
        "expect_verdict": "clear_violation",
        "expect_tier": "T1-blacklist",
        "desc": "长文诈骗引流帖，含'刷单兼职'+'日赚过千'+'扫码领福利'",
    },
    {
        "content_list": [
            "最近私信问同城交友的太多了，我说直白点：这个约炮群不是那种乱七八糟的，"
            "女生多男生少，氛围还行，不限年龄但要实名认证。"
            "想进的别在评论区问了，直接扫码进群，懂的都懂，别举报我。"
        ],
        "report_category": 3,  # 涉黄
        "expect_verdict": "clear_violation",
        "expect_tier": "T1-blacklist",
        "desc": "长文涉黄引流帖，含'约炮'",
    },
    {
        "content_list": [
            "各位烟民朋友看过来！本人有稳定渠道，电子烟批发，香烟低价出售，"
            "比便利店便宜三成，支持同城闪送，量大从优。"
            "需要的加我微信详聊，非诚勿扰，骗子绕道，老客可带新客。"
        ],
        "report_category": 0,  # 广告
        "expect_verdict": "clear_violation",
        "expect_tier": "T1-blacklist",
        "desc": "长文违禁品带货帖，含'电子烟批发'+'香烟低价'",
    },
    {
        "content_list": [
            "这人太过分了，之前骗我朋友钱还装无辜，现在还在装受害者。"
            "我已经号召姐妹们一起去人肉他，把他的公司地址电话全扒出来挂墙上，"
            "看他还怎么嚣张。有料的私我，咱们不能放过这种人。"
        ],
        "report_category": 2,  # 辱骂
        "expect_verdict": "clear_violation",
        "expect_tier": "T1-blacklist",
        "desc": "长文人肉搜索帖，含'人肉他'",
    },

    # —— T1 白名单应判正常 (clear_normal) ——
    # 必须满足：长度<15 + 无信号 + 无联系方式/URL + report_category=4(其他)
    {
        "content_list": ["好的"],
        "report_category": 4,  # 其他
        "expect_verdict": "clear_normal",
        "expect_tier": "T1-whitelist",
        "desc": "短文本'好的'+其他分类",
    },
    {
        "content_list": ["谢谢"],
        "report_category": 4,
        "expect_verdict": "clear_normal",
        "expect_tier": "T1-whitelist",
        "desc": "短文本'谢谢'+其他分类",
    },
    {
        "content_list": ["已收到"],
        "report_category": 4,
        "expect_verdict": "clear_normal",
        "expect_tier": "T1-whitelist",
        "desc": "短文本'已收到'+其他分类",
    },

    # —— T2 加权应判违规 (clear_violation) ——
    # 长文软信号叠加 + 联系方式
    {
        "content_list": [
            "最近平台限流太狠了，想继续搞副业的姐妹看过来。"
            "我们这边有内部渠道，加我微信abc123有优惠，进群还能领代理名额，"
            "手把手教你怎么引流，日入几百不是梦，名额不多先到先得。"
        ],
        "report_category": 0,  # 广告
        "expect_verdict": "clear_violation",
        "expect_tier": "T2-weighted",
        "desc": "长文引流帖：联系方式0.25+有优惠0.1+进群0.1+代理0.1=0.55",
    },
    {
        "content_list": [
            "我真的受够了，每次发言都被你阴阳怪气怼，你个废物脑子有病去死吧，"
            "还天天在评论区带节奏。再敢来我帖子底下跳，我就曝光你，"
            "加我微信abc123咱们私下说清楚，别装无辜。"
        ],
        "report_category": 2,  # 辱骂
        "expect_verdict": "clear_violation",
        "expect_tier": "T2-weighted",
        "desc": "长文人身攻击+联系方式：0.15+0.15+0.2+0.25=0.75",
    },

    # —— T3 应退回 LLM (ambiguous) ——
    {
        "content_list": ["你这个人真的很有意思"],
        "report_category": 2,  # 辱骂
        "expect_verdict": "ambiguous",
        "expect_tier": "T3-llm",
        "desc": "无任何信号，语境不明，需LLM判断",
    },
    {
        "content_list": ["我觉得这个产品体验一般般吧，有待改进"],
        "report_category": 4,  # 其他
        "expect_verdict": "ambiguous",
        "expect_tier": "T3-llm",
        "desc": "长度>15，不满足白名单；无违规信号，退回LLM",
    },
    {
        "content_list": ["这首歌真的太好听了，单曲循环"],
        "report_category": 4,
        "expect_verdict": "clear_normal",
        "expect_tier": "T1-whitelist",
        "desc": "长度14<15，无信号，其他分类，满足白名单全部条件",
    },
    {
        "content_list": ["他说的话让我很不舒服"],
        "report_category": 2,
        "expect_verdict": "ambiguous",
        "expect_tier": "T3-llm",
        "desc": "无信号但举报分类非其他，退回LLM",
    },
]

API_TEST_CASES: list[dict] = [
    {
        "content_list": ["整天装什么清高，小婊子一个，真以为自己有多干净"],
        "report_category": 2,
        "expect_verdict": "clear_violation",
        "expect_tier": "T2-api",
        "desc": "辱骂变体，T1无关键词，mock API block",
    },
    {
        "content_list": ["你这个人真的很有意思，说话总是让人捉摸不透"],
        "report_category": 2,
        "expect_verdict": "ambiguous",
        "expect_tier": "T3-llm",
        "desc": "阴阳怪气，mock API review 灰区",
    },
]

# 向后兼容旧 import（冒烟集）
TEST_CASES = SMOKE_TEST_CASES
BASELINE_TEST_CASES = SMOKE_TEST_CASES

# ═══════════════════════════════════════════════════════════════
#  单条用例运行
# ═══════════════════════════════════════════════════════════════

def _check_pass(case: dict, verdict: str, tier: str) -> tuple[bool, bool, bool]:
    """返回 (passed, verdict_ok, tier_ok)。"""
    ev = case.get("expect_verdict", "")
    et = case.get("expect_tier", "")

    if ev == "not_violation":
        verdict_ok = verdict != "clear_violation"
    elif ev == "not_normal":
        verdict_ok = verdict != "clear_normal"
    elif ev == "":
        verdict_ok = True
    else:
        verdict_ok = verdict == ev

    tier_ok = (et == "" or tier.startswith(et))
    return verdict_ok and tier_ok, verdict_ok, tier_ok


async def run_one(case: dict) -> dict:
    """跑一条用例，直接调用 pre_filter_node（不经过 LangGraph）。

    输入 state 只需 content_list + report_category，与 graph 首节点一致。
    输出 tier_verdict: clear_violation / clear_normal / ambiguous
         filter_tier: T1-blacklist / T1-whitelist / T2-api / T2-weighted / T3-llm
    """
    state = {
        "content_list": case["content_list"],
        "report_category": case["report_category"],
    }
    t0 = time.perf_counter()
    out = await pre_filter_node(state)
    ms = (time.perf_counter() - t0) * 1000
    verdict = out.get("tier_verdict", "ambiguous")
    tier = out.get("filter_tier", "")
    reason = out.get("filter_reason", "")

    passed, verdict_ok, tier_ok = _check_pass(case, verdict, tier)
    strict_check = case.get("expect_verdict", "") != ""

    return {
        "id": case.get("id", ""),
        "desc": case["desc"],
        "golden_category": case.get("golden_category", ""),
        "content": case["content_list"][0][:30],
        "expect_verdict": case["expect_verdict"],
        "actual_verdict": verdict,
        "expect_tier": case["expect_tier"],
        "actual_tier": tier,
        "reason": reason,
        "ms": ms,
        "pass": passed,
        "strict_check": strict_check,
        "verdict_ok": verdict_ok,
        "tier_ok": tier_ok,
        # 级联判定违规时附带的 score / content_type，便于观察
        "score": out.get("anomaly_score"),
        "content_type": out.get("content_type"),
    }


# ═══════════════════════════════════════════════════════════════
#  指标计算
# ═══════════════════════════════════════════════════════════════

def compute_metrics(results: list[dict]) -> dict:
    """聚合级联层指标。

    核心 KPI：
      llm_reduction — ambiguous 占比的补数，即「被级联拦下、无需 LLM」的比例
      false_violation — clear_normal 被误拦（最严重，直接影响用户体验）
      false_normal — clear_violation 被误放（漏判风险）
      strict_accuracy — 仅对有 expect_verdict 约束的用例计算通过率
    """
    total = len(results)
    if total == 0:
        return {}

    # tier 分布
    tier_counts: dict[str, int] = {}
    for r in results:
        tier_counts[r["actual_tier"]] = tier_counts.get(r["actual_tier"], 0) + 1

    # verdict 分布
    verdict_counts: dict[str, int] = {}
    for r in results:
        verdict_counts[r["actual_verdict"]] = verdict_counts.get(r["actual_verdict"], 0) + 1

    # 退回 LLM 数 = verdict == ambiguous
    llm_count = verdict_counts.get("ambiguous", 0)
    # LLM 调用减少率：被级联拦下的比例
    llm_reduction = 1 - (llm_count / total)

    # 正确率
    pass_count = sum(1 for r in results if r["pass"])
    accuracy = pass_count / total

    # 误判细分（级联层安全指标）
    false_violation = sum(
        1 for r in results
        if (r.get("golden_category") == "clear_normal"
            or r.get("expect_verdict") == "not_violation")
        and r["actual_verdict"] == "clear_violation"
    )
    false_normal = sum(
        1 for r in results
        if (r.get("golden_category") == "clear_violation"
            or r.get("expect_verdict") == "not_normal")
        and r["actual_verdict"] == "clear_normal"
    )

    # 延迟统计
    latencies = sorted(r["ms"] for r in results)
    avg_ms = sum(latencies) / total
    p50_ms = latencies[int(total * 0.50)]
    p95_ms = latencies[min(int(total * 0.95), total - 1)]

    strict_total = sum(1 for r in results if r.get("strict_check", True))
    strict_pass = sum(1 for r in results if r.get("strict_check", True) and r["pass"])

    return {
        "total": total,
        "tier_counts": tier_counts,
        "verdict_counts": verdict_counts,
        "llm_count": llm_count,
        "llm_reduction": llm_reduction,
        "accuracy": accuracy,
        "pass_count": pass_count,
        "strict_total": strict_total,
        "strict_pass": strict_pass,
        "strict_accuracy": strict_pass / strict_total if strict_total else 1.0,
        "false_violation": false_violation,
        "false_normal": false_normal,
        "avg_ms": avg_ms,
        "p50_ms": p50_ms,
        "p95_ms": p95_ms,
    }


# ═══════════════════════════════════════════════════════════════
#  对照实验：级联关闭 vs 开启
# ═══════════════════════════════════════════════════════════════

async def run_controlled_comparison(cases: list[dict]) -> dict:
    """同一批用例，分别跑 cascade_enabled=True/False，对比 LLM 调用数。"""
    settings.cascade_enabled = True
    res_on = []
    for c in cases:
        res_on.append(await run_one(c))
    llm_on = sum(1 for r in res_on if r["actual_verdict"] == "ambiguous")

    settings.cascade_enabled = False
    res_off = []
    for c in cases:
        res_off.append(await run_one(c))
    llm_off = sum(1 for r in res_off if r["actual_verdict"] == "ambiguous")

    settings.cascade_enabled = True

    return {
        "llm_calls_cascade_off": llm_off,
        "llm_calls_cascade_on": llm_on,
        "saved": llm_off - llm_on,
        "reduction_rate": 1 - (llm_on / llm_off) if llm_off else 0.0,
    }

# ═══════════════════════════════════════════════════════════════
#  报告打印
# ═══════════════════════════════════════════════════════════════

async def run_suite(cases: list[dict], *, api_enabled: bool, api_mock: bool) -> tuple[list[dict], dict, dict]:
    """在指定 API 配置下跑一批用例。"""
    settings.cascade_api_enabled = api_enabled
    settings.cascade_api_mock = api_mock
    results = []
    for c in cases:
        results.append(await run_one(c))
    metrics = compute_metrics(results)
    compare = await run_controlled_comparison(cases)
    return results, metrics, compare


async def main(*, smoke: bool = False, with_api: bool = False, no_api: bool = False):
    if smoke:
        cases = SMOKE_TEST_CASES
        suite_name = "冒烟（13 条严格 tier）"
        api_enabled = False
        api_mock = False
    else:
        cases = load_golden_set_cases()
        suite_name = f"golden_set.json（{len(cases)} 条）"
        api_enabled = False if no_api else settings.cascade_api_enabled
        api_mock = settings.cascade_api_mock

    print("开始审核级联评测...")
    print(f"评测范围: pre_filter_node 级联前置层（不调 LLM / 不走 LangGraph）")
    print(f"用例集: {suite_name}")
    print(f"级联配置: enabled={settings.cascade_enabled}, "
          f"api_enabled={api_enabled}, api_mock={api_mock}, "
          f"weighted_high={settings.cascade_weighted_high_threshold}")
    print("提示: LangSmith 需全链路评测 → python loadtest/ragas_eval.py（需先起服务）")

    results, metrics, compare = await run_suite(
        cases, api_enabled=api_enabled, api_mock=api_mock,
    )
    print_report(results, metrics, compare, title=suite_name)

    if with_api and not smoke:
        print("\n【T2-api 专项】cascade_api_enabled=True, cascade_api_mock=True")
        api_results, api_metrics, api_compare = await run_suite(
            API_TEST_CASES, api_enabled=True, api_mock=True,
        )
        print_report(api_results, api_metrics, api_compare, title="T2-api 专项 mock")


def print_report(results: list[dict], metrics: dict, compare: dict, title: str = ""):
    header = f"  审核级联评测报告 (Cascade Evaluation)"
    if title:
        header += f" — {title}"
    print("\n" + "=" * 72)
    print(header)
    print("=" * 72)
    # —— 逐条结果 ——
    print("\n【逐条结果】")
    print(f"{'#':>3} {'结果':<6} {'verdict':<18} {'tier':<16} {'ms':>7}  内容/说明")
    print("-" * 72)
    for i, r in enumerate(results, 1):
        flag = "[PASS]" if r["pass"] else "[FAIL]"
        print(f"{i:>3} {flag:<7} {r['actual_verdict']:<18} {r['actual_tier']:<16} "
              f"{r['ms']:>6.2f}ms {r['desc']}")
        if not r["pass"]:
            print(f"      期望: verdict={r['expect_verdict']}, tier={r['expect_tier']}")
            print(f"      实际: verdict={r['actual_verdict']}, tier={r['actual_tier']}")
            if not r["verdict_ok"]:
                print(f"      ! verdict 不符")
            if not r["tier_ok"]:
                print(f"      ! tier 不符")
    print("-" * 72)

    # —— 指标汇总 ——
    print("\n【指标汇总】")
    print(f"  用例总数          : {metrics['total']}")
    print(f"  通过率(全量)      : {metrics['pass_count']}/{metrics['total']} "
          f"= {metrics['accuracy']*100:.1f}%")
    if metrics.get("strict_total", 0) < metrics["total"]:
        print(f"  通过率(有约束)    : {metrics.get('strict_pass', 0)}/{metrics.get('strict_total', 0)} "
              f"= {metrics.get('strict_accuracy', 0)*100:.1f}%  "
              f"（仅 clear_normal/clear_violation 有硬约束）")
    print(f"  平均延迟          : {metrics['avg_ms']:.3f} ms")
    print(f"  P50 延迟          : {metrics.get('p50_ms', metrics['avg_ms']):.3f} ms")
    print(f"  P95 延迟          : {metrics['p95_ms']:.3f} ms")

    print(f"\n  Tier 分布:")
    for tier, cnt in sorted(metrics["tier_counts"].items()):
        pct = cnt / metrics["total"] * 100
        bar = "#" * int(pct / 2)
        print(f"    {tier:<16} {cnt:>3} ({pct:5.1f}%) {bar}")

    print(f"\n  Verdict 分布:")
    for v, cnt in sorted(metrics["verdict_counts"].items()):
        pct = cnt / metrics["total"] * 100
        print(f"    {v:<18} {cnt:>3} ({pct:5.1f}%)")

    print(f"\n  ★ LLM 调用减少率  : {metrics['llm_reduction']*100:.1f}%  "
          f"(退回LLM {metrics['llm_count']}/{metrics['total']})")

    print(f"\n  误判分析:")
    print(f"    期望正常却判违规 (false_violation): {metrics['false_violation']}")
    print(f"    期望违规却判正常 (false_normal)  : {metrics['false_normal']}")

    # —— 对照实验 ——
    print("\n【对照实验：级联开启 vs 关闭】")
    print(f"  级联关闭 (全走LLM) : {compare['llm_calls_cascade_off']} 次 LLM 调用")
    print(f"  级联开启           : {compare['llm_calls_cascade_on']} 次 LLM 调用")
    print(f"  节省               : {compare['saved']} 次")
    print(f"  ★ LLM 调用减少率   : {compare['reduction_rate']*100:.1f}%")

    print("\n" + "=" * 72)
    print("  简历可用指标:")
    print(f"  - 级联前置过滤将 LLM 调用量降低 {compare['reduction_rate']*100:.1f}%")
    print(f"  - 确定性层平均延迟 {metrics['avg_ms']:.2f}ms (P95 {metrics['p95_ms']:.2f}ms)")
    print(f"  - 测试用例通过率 {metrics['accuracy']*100:.1f}%")
    print("=" * 72 + "\n")


# ═══════════════════════════════════════════════════════════════
#  主入口
# ═══════════════════════════════════════════════════════════════

def cli():
    parser = argparse.ArgumentParser(description="审核级联评测")
    parser.add_argument(
        "--smoke", action="store_true",
        help="仅跑 13 条严格 tier 冒烟用例（非默认）",
    )
    parser.add_argument(
        "--with-api", action="store_true",
        help="在 110 条之外额外跑 T2-api mock 专项用例",
    )
    parser.add_argument(
        "--no-api", action="store_true",
        help="强制关闭 T2-api（忽略 .env 的 CASCADE_API_ENABLED）",
    )
    args = parser.parse_args()
    asyncio.run(main(smoke=args.smoke, with_api=args.with_api, no_api=args.no_api))


if __name__ == "__main__":
    cli()