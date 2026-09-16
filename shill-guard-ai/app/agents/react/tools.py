"""ReAct Agent 工具定义。

【@tool 装饰器 — 官方 LangChain 写法】
  from langchain_core.tools import tool

  @tool 会自动：
    1. 把函数 docstring 作为 tool description（LLM 靠它决定是否调用）
    2. 把参数类型注解转为 JSON Schema（LLM 知道传什么参数）
    3. 包装为 StructuredTool，供 bind_tools / ToolNode 使用

  官方文档: https://python.langchain.com/docs/how_to/custom_tools/

【生产注意】
  calculator 里 eval() 仅演示用，生产应换 safe_eval 或 AST 解析。
  search_web 是占位；chat agent 用的是 app/tools/tools.py 的 TavilySearch。
"""
from langchain_core.tools import tool


@tool
def calculator(expression: str) -> str:
    """计算一个数学表达式并返回结果。例如 '12 * (3 + 4)'。
    当用户问数学计算时调用这个工具。

    参数:
        expression: 数学表达式字符串
    """
    try:
        # {"__builtins__": {}} 限制 eval 环境，禁止 import/os 等（仍非完全安全）
        return str(eval(expression, {"__builtins__": {}}, {}))
    except Exception as e:
        return f"计算失败: {e}"


@tool
def search_web(query: str) -> str:
    """在网上搜索关键词并返回结果摘要。
    当用户问到需要最新信息或外部知识时调用。

    参数:
        query: 搜索关键词
    """
    return f"（演示）已为你搜索：{query} —— 这是模拟的搜索结果。"
