"""MCP server 单例：FastMCP 实例 + 工具注册入口。

【FastMCP】
  mcp.server.fastmcp 提供的轻量 MCP Server 框架。
  mcp = FastMCP("name") 创建实例；
  @mcp.tool() 装饰器注册 tool；
  mcp.run() 启动 stdio 服务。

  各 tools_*.py 通过 from app.mcp import mcp 共享同一实例，
  import 时 @mcp.tool() 副作用完成注册。

安装: pip install mcp  （或 fastmcp，视版本而定）
"""
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("ShillGuard")
