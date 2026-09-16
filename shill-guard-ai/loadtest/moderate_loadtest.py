"""审核级联 · 真实流量压测脚本

向 /ai/moderate 端点批量并发发送真实风格举报内容，
每个请求会被 router 自动落一条 JSONL 到 data/cascade_metrics.jsonl，
跑完后用 cascade_metrics.py 离线聚合即可得到真实流量指标。

用法：
    # 1. 先起服务：python run.py
    # 2. 发压（默认 120 条 × 10 并发）：
    python loadtest/moderate_loadtest.py
    # 3. 放大请求量（120 条重复 5 次 = 600 请求，20 并发）：
    python loadtest/moderate_loadtest.py --repeat 5 --concurrency 20
    # 4. 跑完自动出指标报告：
    python loadtest/moderate_loadtest.py --repeat 3 --report
"""
import argparse
import asyncio
import json
import random
import sys
import time
from collections import Counter

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

try:
    import httpx
except ImportError:
    print("[error] 需要安装 httpx: pip install httpx")
    sys.exit(1)


# ═══════════════════════════════════════════════════════════════
#  真实流量测试数据集（120 条，按生产分布）
#  每条: (content_list, report_category, expected_tier)
#  report_category: 0广告/1违法/2辱骂/3涉黄/4其他
#  expected_tier: T1-blacklist/T1-whitelist/T2-weighted/T3-llm (仅参考，不发送)
# ═══════════════════════════════════════════════════════════════

DATASET = [

    # ── T1-黑名单·涉黄 (report_category=3) ──
    (["约炮加我微信abc12345"], 3, "T1-blacklist"),
    (["妹妹裸聊视频私我"], 3, "T1-blacklist"),
    (["色情服务联系13800001234"], 3, "T1-blacklist"),
    (["同城一夜情找她"], 3, "T1-blacklist"),
    (["找小姐电话同上"], 3, "T1-blacklist"),
    (["有没有约炮的加我"], 3, "T1-blacklist"),

    # ── T1-黑名单·诈骗 (report_category=1) ──
    (["刷单兼职日入500不是梦"], 1, "T1-blacklist"),
    (["日赚过千带你飞"], 1, "T1-blacklist"),
    (["投资返利稳赚项目"], 1, "T1-blacklist"),
    (["稳赚不赔快上车"], 1, "T1-blacklist"),
    (["高息返本年化30%"], 1, "T1-blacklist"),
    (["免费领红包啦点链接"], 1, "T1-blacklist"),
    (["点赞赚钱攻略分享"], 1, "T1-blacklist"),
    (["扫码领福利限时"], 1, "T1-blacklist"),

    # ── T1-黑名单·违禁品 (report_category=1) ──
    (["处方药代购万艾可"], 1, "T1-blacklist"),
    (["万艾可代购便宜出"], 1, "T1-blacklist"),
    (["电子烟批发价量大"], 1, "T1-blacklist"),
    (["香烟低价出售联系"], 1, "T1-blacklist"),
    (["野生动物制品回收"], 1, "T1-blacklist"),

    # ── T1-黑名单·人肉 (report_category=2) ──
    (["大家人肉他全家"], 2, "T1-blacklist"),
    (["挂人避雷这个骗子"], 2, "T1-blacklist"),
    (["曝光他身份证号123456789012345678"], 2, "T1-blacklist"),
    (["扒他底细人肉出来"], 2, "T1-blacklist"),

    # ── T1-黑名单·混合(广告分类但涉黄/诈骗词) ──
    (["约炮加薇信abc12345"], 0, "T1-blacklist"),
    (["刷单兼职扫码领福利"], 0, "T1-blacklist"),

    # ── T1-白名单 (report_category=4, len<15, 无信号) ──
    (["好的"], 4, "T1-whitelist"),
    (["谢谢"], 4, "T1-whitelist"),
    (["已收到"], 4, "T1-whitelist"),
    (["没问题"], 4, "T1-whitelist"),
    (["可以的"], 4, "T1-whitelist"),
    (["嗯嗯"], 4, "T1-whitelist"),
    (["了解"], 4, "T1-whitelist"),
    (["收到"], 4, "T1-whitelist"),
    (["明白"], 4, "T1-whitelist"),
    (["好的呢"], 4, "T1-whitelist"),
    (["谢谢啦"], 4, "T1-whitelist"),
    (["没事"], 4, "T1-whitelist"),
    (["哈哈"], 4, "T1-whitelist"),
    (["好滴"], 4, "T1-whitelist"),
    (["收到啦"], 4, "T1-whitelist"),
    (["了解啦"], 4, "T1-whitelist"),
    (["可以的哦"], 4, "T1-whitelist"),
    (["嗯好的"], 4, "T1-whitelist"),

    # ── T2-加权违规·引流类 (report_category=0 广告) ──
    (["加我微信abc123有优惠进群代理"], 0, "T2-weighted"),
    (["进群有优惠代理招商加微信xyz789"], 0, "T2-weighted"),
    (["加v:abc12345有优惠进群"], 0, "T2-weighted"),
    (["薇信abc12345代理进群有优惠"], 0, "T2-weighted"),
    (["加我微信qq12345代理招商进群"], 0, "T2-weighted"),
    (["tg:abc12345有优惠进群代理"], 0, "T2-weighted"),

    # ── T2-加权违规·辱骂+引流 (report_category=2) ──
    (["你个废物脑子有病去死吧加我微信abc123"], 2, "T2-weighted"),
    (["脑残白痴去死加v:abc12345"], 2, "T2-weighted"),
    (["傻子去死废物加我wx:abcdef123"], 2, "T2-weighted"),
    (["你个废物加我微信abc12345进群"], 2, "T2-weighted"),
    (["脑子有病去死加微信qq123456"], 2, "T2-weighted"),

    # ── T2-加权违规·辱骂叠加 (report_category=2，需加权≥0.55) ──
    # 注：纯辱骂词叠加需≥0.55才触发T2，否则退回T3由LLM判断
    (["废物傻子去死脑子有病"], 2, "T2-weighted"),  # 0.15+0.1+0.2+0.15=0.6
    (["脑残白痴去死废物脑子有病"], 2, "T2-weighted"),  # 0.15+0.15+0.2+0.15+0.15=0.8

    # ── T3-灰区·辱骂分类但无明确信号 (report_category=2) ──
    (["你这个人真的很有意思"], 2, "T3-llm"),
    (["我觉得你说话方式有问题"], 2, "T3-llm"),
    (["这人怎么这样啊"], 2, "T3-llm"),
    (["你能不能别这样说话"], 2, "T3-llm"),
    (["真是服了你了"], 2, "T3-llm"),
    (["你怎么想的我不理解"], 2, "T3-llm"),
    (["大家看看这话说的对吗"], 2, "T3-llm"),
    (["你这人怎么这样"], 2, "T3-llm"),
    (["我觉得这人不太靠谱"], 2, "T3-llm"),
    (["说话注意点行不行"], 2, "T3-llm"),

    # ── T3-灰区·广告分类但软信号不足 (report_category=0) ──
    (["这个产品体验一般般吧"], 0, "T3-llm"),
    (["大家觉得这个怎么样"], 0, "T3-llm"),
    (["有没有人用过这个"], 0, "T3-llm"),
    (["这个价格合理吗"], 0, "T3-llm"),
    (["推荐个好用的呗"], 0, "T3-llm"),
    (["这个牌子怎么样有人知道吗"], 0, "T3-llm"),

    # ── T3-灰区·涉黄分类但无黑名单词 (report_category=3) ──
    (["这段内容不太合适吧"], 3, "T3-llm"),
    (["这个图片看着怪怪的"], 3, "T3-llm"),
    (["总觉得哪里不对"], 3, "T3-llm"),
    (["这内容发出来合适吗"], 3, "T3-llm"),

    # ── T3-灰区·违法分类但无黑名单词 (report_category=1) ──
    (["这个行为合法吗"], 1, "T3-llm"),
    (["这样做不会有问题吗"], 1, "T3-llm"),
    (["感觉这事不太对劲"], 1, "T3-llm"),
    (["这个操作合规吗"], 1, "T3-llm"),

    # ── T3-灰区·其他分类长文本(>15字不满足白名单长度条件) (report_category=4) ──
    (["今天天气真不错很适合出去走走放松一下"], 4, "T3-llm"),
    (["这首歌真的太好听了我已经单曲循环一整天了"], 4, "T3-llm"),
    (["关于这个话题我有自己的一些不同看法想分享"], 4, "T3-llm"),
    (["看到这个新闻的事情经过我真的很无语了"], 4, "T3-llm"),
    (["这个电影真的很值得一看推荐给大家去看看"], 4, "T3-llm"),
    (["最近工作压力有点大真的好想休息一段时间"], 4, "T3-llm"),
    (["这个饭店的菜味道还可以环境也挺好的"], 4, "T3-llm"),
    (["周末打算去爬山放松一下有人想一起吗"], 4, "T3-llm"),
    (["这本书写得真的很不错强烈推荐给大家看"], 4, "T3-llm"),
    (["这个游戏真的挺好玩的已经上瘾了停不下来"], 4, "T3-llm"),

    # ── T3-灰区·边界讽刺/阴阳 (report_category=2) ──
    (["真是个人才这种话都说得出口"], 2, "T3-llm"),
    (["你可真行啊佩服佩服"], 2, "T3-llm"),
    (["这智商我也是醉了"], 2, "T3-llm"),
    (["真佩服你的逻辑能力"], 2, "T3-llm"),
    (["你是怎么做到这么理直气壮的"], 2, "T3-llm"),
    # 纯辱骂信号不足(<0.55)，退回LLM判断是否构成网暴
    (["你这个废物脑子有病去死吧"], 2, "T3-llm"),  # 加权0.5<0.55
    (["脑残白痴去死吧你"], 2, "T3-llm"),          # 加权0.5<0.55

    # ── T3-灰区·混合举报分类错配 (真实场景常见：用户选错分类) ──
    (["这家店服务态度很差"], 2, "T3-llm"),
    (["这个产品质量太差了别买"], 4, "T3-llm"),
    (["物流太慢了等了一周"], 4, "T3-llm"),
    (["客服态度敷衍不解决问题"], 2, "T3-llm"),
    (["商品跟描述完全不符"], 4, "T3-llm"),
    (["退货流程太麻烦了"], 4, "T3-llm"),

    # ── T3-灰区·正常但举报分类非其他(不满足白名单category条件) ──
    (["好的没问题"], 2, "T3-llm"),   # 正常内容但category=2→不满足白名单
    (["谢谢分享"], 0, "T3-llm"),     # 正常但category=0→不满足白名单
    (["收到明白"], 3, "T3-llm"),     # 正常但category=3→不满足白名单
    (["哈哈有趣"], 1, "T3-llm"),     # 正常但category=1→不满足白名单
]


# ═══════════════════════════════════════════════════════════════
#  并发发送
# ═══════════════════════════════════════════════════════════════

async def _send_one(client: httpx.AsyncClient, url: str, payload: dict,
                    idx: int, sem: asyncio.Semaphore, results: list):
    async with sem:
        t0 = time.perf_counter()
        try:
            resp = await client.post(url, json=payload, timeout=60.0)
            elapsed = (time.perf_counter() - t0) * 1000
            ok = resp.status_code == 200
            tier = ""
            if ok:
                try:
                    tier = resp.json().get("filterTier", "")
                except Exception:
                    pass
            results.append({
                "idx": idx, "ok": ok, "ms": elapsed,
                "status": resp.status_code, "tier": tier,
            })
            tag = "OK " if ok else f"{resp.status_code}"
            print(f"  [{idx:>3}] {tag} {elapsed:7.0f}ms  tier={tier}")
        except Exception as e:
            elapsed = (time.perf_counter() - t0) * 1000
            results.append({
                "idx": idx, "ok": False, "ms": elapsed,
                "status": -1, "tier": str(e)[:40],
            })
            print(f"  [{idx:>3}] ERR {elapsed:7.0f}ms  {str(e)[:60]}")


async def run_loadtest(host: str, port: int, concurrency: int, repeat: int,
                       shuffle: bool, report: bool):
    url = f"http://{host}:{port}/ai/moderate"

    # 构造请求列表（按 repeat 放大）
    cases = []
    for r in range(repeat):
        for i, (content_list, cat, _) in enumerate(DATASET):
            cases.append({
                "reportId": r * 10000 + i + 1,
                "reportedUserId": 1000 + (i % 50),
                "contentType": "comment",
                "contentList": content_list,
                "reportCategory": cat,
            })

    if shuffle:
        random.shuffle(cases)

    total = len(cases)
    print(f"\n开始压测: {total} 个请求, 并发={concurrency}")
    print(f"目标: {url}")
    print(f"数据集基数: {len(DATASET)}, 重复: {repeat}x")
    print("-" * 60)

    sem = asyncio.Semaphore(concurrency)
    results: list = []
    t_start = time.perf_counter()

    async with httpx.AsyncClient() as client:
        tasks = [
            _send_one(client, url, payload, i, sem, results)
            for i, payload in enumerate(cases, 1)
        ]
        await asyncio.gather(*tasks)

    elapsed_total = time.perf_counter() - t_start

    # ── 汇总 ──
    ok_count = sum(1 for r in results if r["ok"])
    fail_count = total - ok_count
    latencies = sorted(r["ms"] for r in results if r["ok"])
    tier_dist = Counter(r["tier"] for r in results if r["ok"])

    print("\n" + "=" * 60)
    print("  压测汇总")
    print("=" * 60)
    print(f"  总请求    : {total}")
    print(f"  成功      : {ok_count}")
    print(f"  失败      : {fail_count}")
    print(f"  总耗时    : {elapsed_total:.1f}s")
    print(f"  吞吐      : {total / elapsed_total:.1f} req/s" if elapsed_total > 0 else "")
    if latencies:
        p50 = latencies[len(latencies) // 2]
        p95 = latencies[int(len(latencies) * 0.95)]
        p99 = latencies[int(len(latencies) * 0.99)] if len(latencies) > 1 else latencies[-1]
        print(f"  延迟 P50  : {p50:.0f}ms")
        print(f"  延迟 P95  : {p95:.0f}ms")
        print(f"  延迟 P99  : {p99:.0f}ms")
    print(f"\n  返回 Tier 分布(从响应体):")
    for tier in ["T1-blacklist", "T1-whitelist", "T2-weighted", "T3-llm"]:
        c = tier_dist.get(tier, 0)
        pct = c / ok_count * 100 if ok_count else 0
        bar = "#" * int(pct / 100 * 24)
        print(f"    {tier:<16} {c:>4} ({pct:5.1f}%) {bar}")
    print("=" * 60)

    if fail_count > 0:
        print(f"\n  [warn] {fail_count} 个失败，请检查服务是否正常运行")

    # ── 自动出指标报告 ──
    if report:
        print("\n[自动] 运行离线聚合脚本 cascade_metrics.py ...")
        import subprocess
        try:
            subprocess.run([sys.executable, "loadtest/cascade_metrics.py"],
                           check=False)
        except Exception as e:
            print(f"[warn] 调用聚合脚本失败: {e}")
            print("       请手动运行: python loadtest/cascade_metrics.py")


def main():
    ap = argparse.ArgumentParser(description="审核级联真实流量压测")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--concurrency", "-c", type=int, default=10,
                    help="并发数(默认10)")
    ap.add_argument("--repeat", "-r", type=int, default=1,
                    help="数据集重复次数(默认1，即120条)")
    ap.add_argument("--shuffle", action="store_true", help="打乱请求顺序")
    ap.add_argument("--report", action="store_true", help="跑完自动出指标报告")
    args = ap.parse_args()

    asyncio.run(run_loadtest(
        args.host, args.port, args.concurrency,
        args.repeat, args.shuffle, args.report,
    ))


if __name__ == "__main__":
    main()
