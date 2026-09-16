"""Chat Agent 工具定义：联网搜索。

【LangChain Tool 机制】
  TavilySearch 是 langchain_tavily 包提供的 StructuredTool，
  通过 llm.bind_tools([tool]) 绑定后，LLM 可在回复中输出 tool_calls，
  ToolNode 自动执行并返回 ToolMessage。

【Tavily】
  专为 AI Agent 设计的搜索 API，返回结构化摘要而非原始 HTML。
  官方: https://tavily.com/
  LangChain 集成: https://python.langchain.com/docs/integrations/tools/tavily_search/
"""
from langchain_tavily import TavilySearch

from app.config import settings


def get_web_search_tool():
    """创建 Tavily 联网搜索工具实例（每次 chat_node 调用时新建，开销可忽略）。

    参数（【官方 TavilySearch】）:
        max_results: 每次搜索返回条数
        topic:       general=通用 | news=新闻
        tavily_api_key: API 密钥，从 settings 读取
    """
    return TavilySearch(
        max_results=3,
        topic="general",
        tavily_api_key=settings.tavily_api_key,
    )
