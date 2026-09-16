# Windows + uvicorn + psycopg3 事件循环不兼容排障记录

> 日期：2026-07-07
> 范围：高并发压测准备阶段，FastAPI chat agent 在 Windows 上无法启动 / 一请求就 500
> 环境：Windows 10，Anaconda `D:\Environment\Anaconda\envs\agent`，Python 3.12，uvicorn 0.49.0，psycopg3，langgraph `AsyncPostgresSaver`

---

## 背景与目标

为 chat agent 做高并发压测拿基线数据。先用 Locust 打 10 并发，结果 100% 失败、30 秒 0 token；改用 curl 单请求，直接 `500 Internal Server Error`。目标是把 chat agent 跑通，才能进入真正的并发测试。

---

## 现象

### 现象 1：Locust 10 并发，100% 失败

```
POST  chat_stream  40  40  30000ms  30000ms  31000ms  ...  Average size=0
GET   health        9   0     10ms    560ms    560ms  ...  (正常)
```

- `chat_stream`：40 个请求全失败，中位 RT 正好 30000ms，**0 token**（Average size=0）
- `health`：10ms，FastAPI 进程本身活着

### 现象 2：curl 单请求，500

```powershell
curl -N -X POST http://localhost:8000/ai/chat -F "message=你好" -F "thread_id=single_test1"
# 返回：Internal Server Error
```

### 现象 3：FastAPI 终端 traceback

```
File "app/agents/chat/router.py", line 36, in chat
    graph = await build_graph()
File "app/agents/chat/graph.py", line 84, in build_graph
    await checkpointer.setup()
...
psycopg_pool.PoolTimeout: couldn't get a connection after 30.00 sec
error connecting in 'pool-1': Psycopg cannot use the 'ProactorEventLoop' to run in async mode.
Please use a compatible event loop, for instance by running
asyncio.run(..., loop_factory=asyncio.SelectorLoop(selectors.SelectSelector()))
```

关键信号：**`health` 正常但 `/ai/chat` 500** → 不是 FastAPI 框架问题，是 chat 路由依赖的某个组件炸了；traceback 指向 `checkpointer.setup()` → 数据库连接；最底层报错明确点出 **`ProactorEventLoop` 不兼容 psycopg3 异步**。

---

## 根因（两个独立 bug 叠加）

### Bug A（直接阻塞 500）：Windows 事件循环类型不对

**事件循环 / IO 多路复用背景**：
- asyncio 靠操作系统的 IO 多路复用机制"同时盯一堆 IO"。
- Windows 用 **IOCP（Proactor 模型）**：OS 帮你把数据读好再通知你（completion 模型）。
- Linux/Mac 用 **select/poll/epoll（Selector 模型）**：OS 只告诉你"准备好了"，你自己 read（readiness 模型）。
- 两种模型不兼容，库代码必须按其中一种写。

**asyncio 的两种事件循环类**：
| 类 | 机制 | 默认平台 |
|---|---|---|
| `SelectorEventLoop` | epoll/select | Linux/Mac |
| `ProactorEventLoop` | IOCP | **Windows** |

**psycopg3 异步**：底层用 socket + Selector 模型实现，只能在 `SelectorEventLoop` 上跑。它在 ProactorEventLoop 上**主动拒绝工作**（不是慢，是直接报错），于是 `AsyncConnectionPool` 30 秒拿不到连接 → `PoolTimeout` → 500。

**这就是 Locust 那 30 秒 0 token 的真因**：不是 LLM 慢、不是并发瓶颈，是数据库连接池卡死 30 秒超时。`health` 不连数据库所以正常。

### Bug B（即便修了 A 也会在并发下炸）：每请求重建 graph

`router.py` 第 36 行原代码：
```python
graph = await build_graph()     # 每个请求都重建！
```
而 `graph.py` 里已有缓存单例：
```python
_graph_instance = None
async def get_graph():
    global _graph_instance
    if _graph_instance is None:
        _graph_instance = await build_graph()
    return _graph_instance
```

`build_graph()` 每次都：新建 `AsyncPostgresSaver` → 跑 `checkpointer.setup()`（建表 SQL）→ `g.compile()`。10 并发 = 10 个请求同时建表、编译图，互相踩、浪费资源。**应该用 `get_graph()` 复用单例**。

---

## 排查走过的弯路

### 弯路 1：误判为"事件循环被同步 LLM 调用堵死"

最初根据"chat_stream 30 秒 0 token、health 正常"判断是 P0 改造要解决的"同步 `llm.invoke()` 阻塞事件循环"问题。让用户先做单请求 curl 区分"A 事件循环堵"还是"B LLM 慢"。

**转折**：curl 单请求直接 500——单请求都跑不起来，根本到不了"并发瓶颈"那一步。说明是**功能 bug**，不是并发问题。这是关键转折，避免了在错误方向上做 P0 改造。

### 弯路 2：在 main.py 顶部设 event_loop_policy

按经典 Windows + psycopg3 修复法，在 `main.py` 最顶部加：
```python
import sys, asyncio
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
```
重启 `uvicorn app.main:app` → **仍然报 ProactorEventLoop 错**。

**原因**：`uvicorn` CLI 启动顺序是「① uvicorn 自己建事件循环 → ② import main.py」。main.py 里的 policy 改动在第 ② 步才跑，但循环在第 ① 步已经建好（Proactor）。policy 只对"之后新建的循环"生效，对已存在的循环无效。

### 弯路 3：改用 run.py 启动器，policy 仍不生效

写 `run.py`，在 `import uvicorn` 之前设 policy，再调 `uvicorn.run(...)`：
```python
import sys, asyncio
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
import uvicorn
uvicorn.run("app.main:app", host="0.0.0.0", port=8000)
```
重启 → **仍然报 ProactorEventLoop 错**。

**真因**（查 uvicorn 源码 `D:\Environment\Anaconda\envs\agent\Lib\site-packages\uvicorn\loops\asyncio.py` 第 8-11 行）：
```python
def asyncio_loop_factory(use_subprocess: bool = False):
    if sys.platform == "win32" and not use_subprocess:
        return asyncio.ProactorEventLoop   # ← 硬编码！无视全局 policy
    return asyncio.SelectorEventLoop
```
**uvicorn 0.49 的"asyncio"循环模式在 Windows 上直接 `return asyncio.ProactorEventLoop`，完全无视全局 event_loop_policy**。无论 run.py 还是 main.py 里设 policy，uvicorn 都自己造一个 ProactorEventLoop。这是这个 bug 最反直觉、最坑的一点——经典修复法（设 policy）对 uvicorn 完全无效。

---

## 最终解决

### 解决 A：绕过 uvicorn 的 `server.run()`，自己建 SelectorEventLoop 跑 `server.serve()`

`run.py`：
```python
import asyncio
import sys
import uvicorn

def main():
    config = uvicorn.Config("app.main:app", host="0.0.0.0", port=8000, reload=False)
    server = uvicorn.Server(config)

    # 显式建循环：Windows 用 SelectorEventLoop（psycopg3 要求），其它平台默认
    if sys.platform == "win32":
        loop = asyncio.SelectorEventLoop()
    else:
        loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # 直接在已建好的 SelectorEventLoop 上跑 server.serve()，
    # 跳过 server.run() 内部的 asyncio.run(loop_factory=Proactor) 那一步
    loop.run_until_complete(server.serve())

if __name__ == "__main__":
    main()
```

**原理**：uvicorn 的 `Server.run()` 内部用 `asyncio.run(serve(), loop_factory=asyncio_loop_factory())`，而那个工厂在 Windows 硬编码返回 `ProactorEventLoop`。**直接调 `loop.run_until_complete(server.serve())` 就跳过了 `Server.run()`，避免它用硬编码工厂建循环**。`server.serve()` 协程跑起来时，`asyncio.get_running_loop()` 拿到的是我们自己建的 SelectorEventLoop，psycopg3 正常工作。

**三种启动方式对比**：

| 启动命令 | 谁决定循环类型 | 结果 |
|---|---|---|
| `uvicorn app.main:app` | uvicorn 工厂硬编码 Proactor | ❌ |
| `uvicorn.run(...)`（run.py 旧版） | uvicorn 工厂硬编码 Proactor | ❌ |
| `loop.run_until_complete(server.serve())`（run.py 新版） | **自己 `asyncio.SelectorEventLoop()`** | ✅ |

### 解决 B：router 用 `get_graph()` 复用单例

`app/agents/chat/router.py`：
```python
# 原：from app.agents.chat.graph import build_graph
# 改：
from app.agents.chat.graph import get_graph
# 原：graph = await build_graph()
# 改：
graph = await get_graph()
```

### 验证

`python run.py` 启动 → 无 ProactorEventLoop 报错 → `curl` 单请求 → 3~10 秒内流式吐字 → chat agent 跑通，可进入并发压测。

---

## 涉及文件

| 文件 | 改动 |
|---|---|
| `run.py`（新建） | 启动器：显式建 SelectorEventLoop 跑 `server.serve()`，绕过 uvicorn 硬编码 Proactor 工厂 |
| `app/main.py` | 顶部加 `set_event_loop_policy(WindowsSelectorEventLoopPolicy)`（防御性，覆盖 `python -m app.main` 启动路径；uvicorn 路径下被 run.py 覆盖） |
| `app/agents/chat/router.py` | `build_graph()` → `get_graph()`，复用 graph 单例，避免每请求重建 |

---

## 关键认知 / 方法论

1. **"单请求 500"和"并发慢"是完全不同的两类问题**：单请求就跑不通 = 功能 bug，先修功能再谈并发。Locust 的"30 秒 0 token"看似并发问题，本质是功能 bug 在并发下的表现。**先用 curl 单请求验证功能，再上 Locust**，能避免大量误判。

2. **`/health` 正常 + 业务接口 500 的组合 = 业务接口依赖的某个组件炸了**，不是 FastAPI 框架问题。`/health` 是最好的"框架是否健康"探针。

3. **uvicorn 在 Windows 上硬编码 ProactorEventLoop，无视全局 policy**——这是最反直觉的点。经典 psycopg3+Windows 修复法（设 `WindowsSelectorEventLoopPolicy`）对 uvicorn 启动方式无效。必须查 uvicorn 源码（`loops/asyncio.py`）才能发现它有自己的循环工厂。

4. **当"标准修复法"不生效时，去查库的源码**：`D:\Environment\Anaconda\envs\agent\Lib\site-packages\uvicorn\loops\asyncio.py` 一共 12 行，一眼就看到 `return asyncio.ProactorEventLoop`。第三方库装在 site-packages 里，直接读源码是最快的定位手段，比上网搜更准。

5. **绕过库的默认行为 vs 改库源码**：不要改 site-packages 里的库源码（升级会丢、不可复现）。用"自己建循环 + `run_until_complete(server.serve())`"从外部绕过 `Server.run()` 的硬编码工厂，是干净持久的解法。

6. **traceback 的最底层报错往往就是根因**：`Psycopg cannot use the 'ProactorEventLoop'` 这句话已经把答案写脸上了，上层 `PoolTimeout` 是它的后果。读 traceback 要从下往上看。

---

## 遗留 / 注意事项

- **`run.py` 不支持 `--reload` 热重载**：reload 会 spawn 子进程，子进程仍走 uvicorn 默认 Proactor 工厂，又会报错。开发改代码需手动 `Ctrl+C` 重启。压测时本就不该开 reload，无影响。
- **部署到 Linux 不需要 run.py 这套**：Linux 默认就是 SelectorEventLoop，`uvicorn app.main:app` 直接能用。`run.py` 里的 `if sys.platform == "win32"` 分支会自动走 `asyncio.new_event_loop()`，跨平台安全。
- **`main.py` 顶部的 policy 设置在 uvicorn 路径下其实是冗余的**（被 uvicorn 工厂覆盖），保留是为了覆盖 `python -m app.main` 启动路径和未来非 uvicorn 的 async 代码，幂等无害。
- **后续若要 `--workers N` 多进程部署**：每个 worker 是独立进程、独立事件循环，需确保每个 worker 都用 SelectorEventLoop。生产建议在 Linux 部署（无此问题），或用 gunicorn + uvicorn worker 并在 worker 启动钩子里设 policy。
