"""ShillGuard Chat Agent 压测脚本（Locust）。

目标接口：POST /ai/chat （multipart/form-data，SSE 流式返回）
测度指标：
  - TTFT  (Time To First Token)：从发请求到收到第一个 delta 的时间，agent 最关键指标
  - TOTAL  整个流式响应到 [DONE] 的总耗时
  - TOKENS 收到的 delta 块数（近似 token 数）
  - TPS    tokens / TOTAL，输出速率
  - ERR    非 200 / 连接异常 / 没收到 [DONE] 都算失败

运行方式（二选一）：
  # 1) 带 Web UI（推荐，浏览器开 http://localhost:8089 手动调并发数和加压速率）
  locust -f loadtest/locustfile.py --host=http://localhost:8000

  # 2) 无头模式（CI / 一次性出数据）
  locust -f loadtest/locustfile.py --host=http://localhost:8000 \
         --headless -u 100 -r 10 -t 60s \
         --csv=loadtest/result --only-summary

  参数说明：
    -u  / --users          并发用户数（同时模拟多少人）
    -r  / --spawn-rate     每秒新增多少用户（加压速率，防止瞬间打爆）
    -t  / --run-time       持续时间
    --csv                 导出 csv 结果文件前缀
"""
import json
import time
import uuid
import random

import requests
from locust import User, task, between, events


# ---------- 配置区 ----------
CHAT_PATH = "/ai/chat"
HEALTH_PATH = "/health"

# 真实用户提问池：长短混合，覆盖闲聊/法规/RAG/多轮，避免每次问一样导致缓存命中
MESSAGE_POOL = [
    "你好，今天天气怎么样？",
    "网络暴力相关的法律法规有哪些？",
    "帮我看一段评论是否违规：你这种人就该去死。",
    "平台对刷单引流的处罚规定是什么？",
    "解释一下什么是网络欺凌。",
    "我想举报一个用户，需要准备什么材料？",
    "诈骗类内容在法律里是怎么定义的？",
    "请总结一下未成年人保护法里和网络相关的条款。",
    "有人在评论区人身攻击我，我该怎么办？",
    "什么是RRF融合检索？",
]

# 单请求超时（秒）。LLM 可能慢，设 120s 给足空间；TTFT 单独设短一点能更早发现"卡死"
CONNECT_TIMEOUT = 10
READ_TIMEOUT = 120
TTFT_TIMEOUT = 30   # 超过这个还没首字，大概率卡住了，直接记为失败


@events.init_command_line_parser.add_listener
def _add_args(parser):
    # 自定义参数：每个用户问几轮就休息
    parser.add_argument(
        "--chat-rounds-per-user", type=int, default=999,
        help="每个虚拟用户在压测期间最多发多少条消息（默认不限）",
    )


class ChatUser(User):
    """模拟一个真实聊天用户：发消息 -> 收 SSE 流 -> 休息 -> 再发。

    每个用户用独立 thread_id，避免对话历史串台（这正是基线测试要暴露的问题之一）。
    """
    # 两次请求间思考 1~4 秒，模拟人打字
    wait_time = between(1, 4)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.thread_id = f"loadtest_{uuid.uuid4().hex[:12]}"
        self.round = 0
        # 用裸 requests（不走 locust.client）+ 手动 fire 事件，
        # 这样才能精确把"流式消费"的时间也算进统计，并分离 TTFT/TOTAL。
        self.session = requests.Session()

    def on_stop(self):
        try:
            self.session.close()
        except Exception:
            pass

    @task(10)
    def chat_stream(self):
        """主任务：POST /ai/chat，消费 SSE 流，记录 TTFT/TOTAL/TOKENS/TPS。"""
        self.round += 1
        _opts = getattr(self.environment, "parsed_options", None)
        rounds = getattr(_opts, "chat_rounds_per_user", 999) if _opts else 999
        if self.round > rounds:
            self.environment.runner.quit()
            return

        message = random.choice(MESSAGE_POOL)
        files = {"message": (None, message), "thread_id": (None, self.thread_id)}

        t_start = time.perf_counter()
        ttft = None
        tokens = 0
        error_msg = None
        done = False

        try:
            resp = self.session.post(
                f"{self.host}{CHAT_PATH}",
                files=files,
                stream=True,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
            if resp.status_code != 200:
                error_msg = f"HTTP {resp.status_code}: {resp.text[:200]}"
            else:
                # 逐行读 SSE。每行形如 "data: {...}\n\n"
                for raw in resp.iter_lines(decode_unicode=True):
                    if not raw:
                        continue
                    if not raw.startswith("data:"):
                        continue
                    payload = raw[5:].strip()
                    if ttft is None:
                        ttft = time.perf_counter() - t_start
                        if ttft > TTFT_TIMEOUT:
                            error_msg = f"TTFT_TIMEOUT>{TTFT_TIMEOUT}s"
                            break
                    if payload == "[DONE]":
                        done = True
                        break
                    try:
                        obj = json.loads(payload)
                        if obj.get("delta"):
                            tokens += 1
                    except json.JSONDecodeError:
                        # 协议异常不算致命，但记下来
                        pass
        except requests.exceptions.Timeout as e:
            error_msg = f"Timeout: {e}"
        except requests.exceptions.ConnectionError as e:
            error_msg = f"ConnError: {e}"
        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
        finally:
            try:
                resp.close()
            except Exception:
                pass

        total = time.perf_counter() - t_start
        tps = (tokens / total) if (total > 0 and tokens > 0) else 0.0

        # 成功条件：200 + 收到 [DONE] + 至少 1 个 token + 无 error_msg
        success = (error_msg is None) and done and (tokens > 0) and (ttft is not None)

        # 主指标：TOTAL（Locust 的 Aggregated 里会看到 chat_stream 的响应时间分布）
        events.request.fire(
            request_type="POST",
            name="chat_stream",
            response_time=total * 1000,        # ms
            response_length=tokens,
            exception=None if success else (Exception(error_msg or "no DONE/no token")),
            context={"thread_id": self.thread_id},
        )

        # 分指标：TTFT 单独记一条，方便看首字延迟分布
        if ttft is not None:
            events.request.fire(
                request_type="POST",
                name="chat_stream_TTFT",
                response_time=ttft * 1000,
                response_length=0,
                exception=None,
                context={},
            )

        # 自定义指标：token 速率（用 response_length 存 tps*1000，单位 ms 等价）
        if tps > 0:
            events.request.fire(
                request_type="POST",
                name="chat_stream_TPS",
                response_time=tps * 1000,   # 这里借用 response_time 字段存 tps*1000
                response_length=tokens,
                exception=None,
                context={},
            )

        # 本地调试输出（--headless 时控制台能看到每条请求）
        # Locust 2.44 里属性叫 parsed_options；web UI 模式下可能没有，用 getattr 兜底
        _opts = getattr(self.environment, "parsed_options", None)
        _headless = bool(getattr(_opts, "headless", False))
        if _headless:
            status = "OK " if success else "ERR"
            print(f"[{status}] ttft={(ttft*1000) if ttft else -1:.0f}ms "
                  f"total={total*1000:.0f}ms tokens={tokens} tps={tps:.1f} "
                  f"err={error_msg}")

    @task(1)
    def health(self):
        """轻量探活，作为对照组——同样的并发下 /health 应该几乎不降速，
        如果 /health 也慢了，说明是 FastAPI 事件循环本身被堵了（async 化不彻底的铁证）。
        """
        t0 = time.perf_counter()
        try:
            resp = self.session.get(f"{self.host}{HEALTH_PATH}", timeout=5)
            rt = (time.perf_counter() - t0) * 1000
            events.request.fire(
                request_type="GET",
                name="health",
                response_time=rt,
                response_length=len(resp.content),
                exception=None if resp.ok else Exception(f"HTTP {resp.status_code}"),
                context={},
            )
        except Exception as e:
            rt = (time.perf_counter() - t0) * 1000
            events.request.fire(
                request_type="GET",
                name="health",
                response_time=rt,
                response_length=0,
                exception=e,
                context={},
            )
