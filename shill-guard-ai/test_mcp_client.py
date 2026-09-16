"""MCP 客户端诊断 v3：超时+flush+异常捕获，定位 call_tool 是否卡住。"""
import asyncio
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

def log(msg):
    print(msg, flush=True)

async def main():
    server_params = StdioServerParameters(
        command="D:\\Environment\\Anaconda\\envs\\agent\\python.exe",
        args=["-m", "app.mcp.server"],
        env={"PYTHONPATH": "D:\\Projects\\shill-guard-ai"},
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            log("=== session 初始化完成 ===")

            tools = await session.list_tools()
            log(f"=== 注册工具数: {len(tools.tools)} ===")
            for t in tools.tools:
                log(f"  - {t.name}")

            log("\n=== 准备调用 rag_search_laws ===")
            try:
                result = await asyncio.wait_for(
                    session.call_tool("rag_search_laws", {"query": "网络暴力", "top_k": 3}),
                    timeout=120,
                )
                log("=== 调用返回 ===")
                log(f"isError={result.isError}, content数={len(result.content)}")
                for i, content in enumerate(result.content):
                    log(f"--- content[{i}] type={type(content).__name__} ---")
                    if hasattr(content, 'text'):
                        log(f"text: {content.text[:500]}")
                    else:
                        log(f"repr: {repr(content)[:500]}")
            except asyncio.TimeoutError:
                log("!!! 超时：call_tool 120 秒没返回，工具卡死了")
            except Exception as e:
                log(f"!!! 异常: {type(e).__name__}: {e}")

asyncio.run(main())