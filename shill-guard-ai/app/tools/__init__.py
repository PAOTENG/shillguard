"""工具实现集合：LangGraph ToolNode 与 MCP server 共用。

当前已实现：
- tools.py : get_web_search_tool() — Tavily 联网搜索（chat Agent 用）

规划中（Java 侧对接，尚未落地）：
- violation_store.py : 查用户历史违规（调 Java shill-content）
- minio_image.py     : 从 MinIO 拉图片做 OCR/多模态审核
- audit_writer.py    : 把审核结果写回 Java 业务库

【LangChain 工具机制】
  每个工具写成纯函数 → @tool 装饰成 StructuredTool，
  再用 llm.bind_tools([tool]) 让 LLM 输出 tool_calls，
  ToolNode 自动执行并返回 ToolMessage。
  也可用 FastMCP 装饰成 MCP tool 暴露给 Cursor。
"""
from app.tools.tools import get_web_search_tool

__all__ = ["get_web_search_tool"]
