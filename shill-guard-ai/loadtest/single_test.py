"""单请求测量脚本：发一个 POST /ai/chat，消费 SSE 流，打印 TTFT / 总耗时 / token 数 / 完整回答。

用法：
    python loadtest/single_test.py
    python loadtest/single_test.py --message "网络暴力相关法律" --thread mytest
    python loadtest/single_test.py --host http://localhost:8000

输出示例：
    [TTFT]   3.21 秒  （首字返回时间）
    [TOTAL]  12.45 秒 （到 [DONE] 总耗时）
    [TOKENS] 86 个 delta 块
    [TPS]    6.9 tokens/秒
    [STATUS] 200
    [回答内容]
    你好！我是 ShillGuard 智能助手...
"""
import argparse
import json
import time

import requests


def run_once(host: str, message: str, thread_id: str, timeout: int = 120):
    files = {"message": (None, message), "thread_id": (None, thread_id)}

    t0 = time.perf_counter()
    ttft = None
    tokens = 0
    answer_parts = []
    status = None
    error = None
    done = False

    try:
        resp = requests.post(
            f"{host}/ai/chat",
            files=files,
            stream=True,
            timeout=(10, timeout),
        )
        status = resp.status_code
        if status != 200:
            error = resp.text[:500]
        else:
            for raw in resp.iter_lines(decode_unicode=True):
                if not raw:
                    continue
                if not raw.startswith("data:"):
                    continue
                payload = raw[5:].strip()
                if ttft is None:
                    ttft = time.perf_counter() - t0
                if payload == "[DONE]":
                    done = True
                    break
                try:
                    obj = json.loads(payload)
                    delta = obj.get("delta", "")
                    if delta:
                        tokens += 1
                        answer_parts.append(delta)
                except json.JSONDecodeError:
                    pass
    except requests.exceptions.Timeout as e:
        error = f"Timeout: {e}"
    except requests.exceptions.ConnectionError as e:
        error = f"ConnError: {e}"
    except Exception as e:
        error = f"{type(e).__name__}: {e}"
    finally:
        try:
            resp.close()
        except Exception:
            pass

    total = time.perf_counter() - t0
    answer = "".join(answer_parts)
    tps = (tokens / total) if (total > 0 and tokens > 0) else 0.0

    print("=" * 60)
    print(f"  请求: {message}")
    print(f"  thread_id: {thread_id}")
    print("-" * 60)
    print(f"  [STATUS]  {status}")
    print(f"  [TTFT]    {ttft*1000 if ttft else -1:.0f} 毫秒  ({ttft:.2f} 秒)" if ttft else "  [TTFT]    未收到任何数据")
    print(f"  [TOTAL]   {total*1000:.0f} 毫秒  ({total:.2f} 秒)")
    print(f"  [TOKENS]  {tokens} 个 delta 块")
    print(f"  [TPS]     {tps:.1f} tokens/秒")
    print(f"  [DONE]    {'是' if done else '否（流未正常结束）'}")
    if error:
        print(f"  [ERROR]   {error}")
    print("-" * 60)
    print("  [回答内容]")
    print(answer if answer else "(空)")
    print("=" * 60)

    return {
        "status": status,
        "ttft": ttft,
        "total": total,
        "tokens": tokens,
        "tps": tps,
        "done": done,
        "error": error,
        "answer": answer,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="http://localhost:8000")
    ap.add_argument("--message", default="你好，请简短介绍一下你自己")
    ap.add_argument("--thread", default=f"single_{int(time.time())}")
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--repeat", type=int, default=1, help="重复发几次，看稳定性")
    args = ap.parse_args()

    results = []
    for i in range(args.repeat):
        if args.repeat > 1:
            print(f"\n========== 第 {i+1}/{args.repeat} 次 ==========")
        r = run_once(args.host, args.message, args.thread, args.timeout)
        results.append(r)
        if args.repeat > 1 and i < args.repeat - 1:
            time.sleep(2)

    if args.repeat > 1:
        print("\n========== 汇总 ==========")
        ttfts = [r["ttft"] for r in results if r["ttft"]]
        totals = [r["total"] for r in results]
        ok = sum(1 for r in results if r["done"] and r["error"] is None)
        print(f"  成功: {ok}/{args.repeat}")
        if ttfts:
            print(f"  TTFT:  min={min(ttfts)*1000:.0f}ms  max={max(ttfts)*1000:.0f}ms  avg={sum(ttfts)/len(ttfts)*1000:.0f}ms")
        if totals:
            print(f"  TOTAL: min={min(totals)*1000:.0f}ms  max={max(totals)*1000:.0f}ms  avg={sum(totals)/len(totals)*1000:.0f}ms")


if __name__ == "__main__":
    main()
