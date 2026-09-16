"""阶梯加压：自动依次跑 10 / 50 / 100 / 300 / 500 / 1000 并发，每档 60s，结果汇总到 csv。

用法：
    python loadtest/staircase.py --host http://localhost:8000

为什么阶梯而不是直接打 1000：
  - 直接打 1000 会瞬间把瓶颈和雪崩混在一起，看不出"拐点在哪"
  - 阶梯加压能画出"并发数 vs QPS/RT/错误率"曲线，拐点 = 系统真实承载上限
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent

# (并发数, 每秒加压速率, 持续时间)
STAGES = [
    (10,   2,   "60s"),
    (50,   5,   "60s"),
    (100,  10,  "60s"),
    (300,  20,  "60s"),
    (500,  30,  "60s"),
    (1000, 50,  "60s"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="http://localhost:8000")
    ap.add_argument("--locust", default="locust")
    args = ap.parse_args()

    for users, rate, dur in STAGES:
        tag = f"u{users}"
        csv_prefix = HERE / f"stair_{tag}"
        print(f"\n========== 阶段: {users} 用户, +{rate}/s, 持续 {dur} ==========")
        cmd = [
            args.locust, "-f", str(HERE / "locustfile.py"),
            "--host", args.host,
            "--headless",
            "-u", str(users),
            "-r", str(rate),
            "-t", dur,
            "--csv", str(csv_prefix),
            "--only-summary",
        ]
        t0 = time.time()
        ret = subprocess.call(cmd)
        print(f"阶段 {tag} 结束, 耗时 {time.time()-t0:.0f}s, 返回码 {ret}")
        if ret != 0:
            print("该阶段失败，停止后续加压。")
            sys.exit(ret)
        # 档间休息 10s，让系统恢复、连接释放
        time.sleep(10)

    print("\n所有阶段完成。结果文件：")
    for p in HERE.glob("stair_u*_stats.csv"):
        print("  ", p.name)


if __name__ == "__main__":
    main()
