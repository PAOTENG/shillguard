# ShillGuard Chat Agent 压测

针对 `POST /ai/chat`（SSE 流式）的 Locust 压测脚本，用来拿"高并发改造前"的基线数据。

## 安装

在你的 agent 环境里装 Locust：

```powershell
conda activate agent
pip install locust -i https://pypi.tuna.tsinghua.edu.cn/simple
```

## 启动被测服务

确保 FastAPI 已起在 `http://localhost:8000`：

```powershell
conda activate agent
cd d:\Projects\shill-guard-ai
uvicorn app.main:app --host 0.0.0.0 --port 8000
```
> 压测时不要用 `--reload`，reload 会拖慢且不稳定。

## 运行方式

### 方式 A：Web UI（推荐第一次用，直观）

```powershell
cd d:\Projects\shill-guard-ai
locust -f loadtest/locustfile.py --host=http://localhost:8000
```
浏览器打开 `http://localhost:8089`：
- Number of users：并发用户数（先填 10）
- Ramp up：每秒新增用户数（填 2）
- 点击 Start swarming

### 方式 B：无头 + 阶梯加压（一键出全量数据）

```powershell
python loadtest/staircase.py --host http://localhost:8000
```
自动依次跑 10 / 50 / 100 / 300 / 500 / 1000 并发，每档 60s，结果落到 `loadtest/stair_u*_stats.csv`。

### 方式 C：单档无头（精确控制）

```powershell
locust -f loadtest/locustfile.py --host=http://localhost:8000 `
       --headless -u 100 -r 10 -t 60s `
       --csv=loadtest/result --only-summary
```

## 指标含义

Locust 统计表里会出现这几个 name：

| name | 含义 | 看什么 |
|---|---|---|
| `chat_stream` | 完整流式请求 | **Total RT** 的 p95/p99，越大越慢 |
| `chat_stream_TTFT` | 首字返回时间 | agent 最关键指标，目标 p95 < 500ms |
| `chat_stream_TPS` | token 输出速率 | 数值越大输出越快（注意单位是借用 response_time，看平均值即可） |
| `health` | 探活对照 | 如果它也变慢 → 事件循环被堵死了（async 不彻底的铁证） |

关键列：
- **Average / Median**：平均 / 中位 RT
- **90% / 95% / 99%**：分位 RT（**只看分位，不看平均**）
- **Fails**：失败次数
- **RPS**：每秒请求数

## 怎么判断"瓶颈在哪"

观察这两条曲线/对比：

1. **/health 的 RT 随并发上升而飙升** → FastAPI 事件循环被同步调用堵住了 → P0 改造（全 async）能解决
2. **chat_stream TTFT 飙升但 /health 不变** → LLM API 侧限流/排队 → 加 Semaphore + 重试 + 限流
3. **错误率随并发突增（429/Timeout）** → LLM API 配额打爆 → 必须限流
4. **Fails 里大量 "no DONE/no token"** → 流被中途掐断，连接耗尽 → 多 worker + 连接池
5. **RPS 到一定值后不再涨** → 到拐点了，这就是当前系统的承载上限

## 跑完保存

每档的 csv 保留下来（`stair_u10_stats.csv` ... `stair_u1000_stats.csv`），改造后用同样脚本再跑一遍，前后对比就是简历里的"提升 X 倍"数据来源。
