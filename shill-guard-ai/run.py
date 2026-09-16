"""FastAPI 启动脚本：强制用 SelectorEventLoop 跑 uvicorn，兼容 psycopg3 异步。

为什么不能直接用 `uvicorn app.main:app` 或 `uvicorn.run()`：
  uvicorn 0.49 的 loops/asyncio.py 在 Windows 上硬编码返回 asyncio.ProactorEventLoop，
  完全无视全局 event_loop_policy。而 psycopg3 异步只兼容 SelectorEventLoop。
  所以必须绕过 uvicorn 的 server.run()（它内部用那个硬编码工厂），
  自己显式建一个 SelectorEventLoop，把 server.serve() 协程跑在上面。

用法：
    python run.py
"""
import asyncio
import sys

import uvicorn


def main():
    config = uvicorn.Config(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        # 不开 reload：reload 会 spawn 子进程，子进程仍走 uvicorn 默认 Proactor 工厂
        reload=False,
    )
    server = uvicorn.Server(config)

    # 显式建循环：Windows 上用 SelectorEventLoop（psycopg3 要求），其它平台用默认
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
