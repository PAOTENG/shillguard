"""RAG 检索类 MCP Tools。

【MCP 是什么】
  Model Context Protocol：Anthropic 发起的开放协议，让 AI 客户端（如 Cursor）
  标准化调用外部工具。FastMCP 是 Python 实现。
  官方: https://modelcontextprotocol.io/

【@mcp.tool() 装饰器】
  FastMCP 官方写法，把 Python 函数注册为 MCP tool，AI 客户端可发现并调用。
  工具函数的 docstring 会作为 tool description 传给 LLM。
"""
from app.mcp import mcp
from app.rag.retriever import retrieve as rag_retrieve


@mcp.tool()
async def rag_search_laws(query: str, top_k: int = 5) -> str:
    """检索【法律法规与平台规则】知识库，返回与查询最相关的条款原文片段。

    适用场景（凡是涉及法律法规、平台规则的问题都应调用本工具）：
      - 查询某类违法行为/社会现象相关的法律条款，例如：网络暴力、电信诈骗、造谣传谣、
        隐私侵犯、人身攻击、煽动情绪、违禁商品等
      - 了解平台对某类违规行为的治理规定和处置措施
      - 审核具体内容时需要引用法规条款作为违规判定依据
      - 用户申诉、禁言处置时需要调取相关条款

    本工具检索的是项目本地沉淀的法规知识库（含国家法律法规 + 平台自建治理规定），
    返回条款原文，引用准确、可溯源。涉及法律法规的问题请优先调用本工具检索，
    而不是凭模型记忆回答，以保证条款内容准确。

    注意：平台自建治理规定是私有数据，网络搜索无法获取，必须用本工具检索。

    参数:
        query: 检索 query 字符串
        top_k: 返回条数，默认 5
    """
    # retrieve 是 async 函数，必须 await（与 FastAPI 路由层用法一致）
    chunks = await rag_retrieve(query, top_k=top_k)
    return "\n---\n".join(chunks) if chunks else "未检索到相关条款"
