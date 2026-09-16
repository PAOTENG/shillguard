"""LangSmith / LangChain tracing 初始化（可观测性）。

【LangSmith 是什么】
  LangChain 官方的可观测平台，自动记录 LLM 调用链、token 用量、延迟。
  官方: https://docs.smith.langchain.com/

【启用方式（.env 任选一种命名）】
  LANGSMITH_TRACING=true
  LANGSMITH_API_KEY=lsv2_...
  LANGSMITH_PROJECT=shill-guard-ai

  或旧版命名：LANGCHAIN_TRACING_V2 / LANGCHAIN_API_KEY / LANGCHAIN_PROJECT

【调用时机】
  本函数为可选工具。当前 eval/run_eval.py、loadtest 脚本均未显式调用它——
  LangChain/LangGraph 会自动读取 LANGCHAIN_* 环境变量并上报 trace，
  只要在 .env 中配好 LANGSMITH_TRACING=true / LANGSMITH_API_KEY 即可生效。
  如需在脚本里统一加载 .env 并兼容两套命名，可手动调用 setup_langsmith_tracing()。
"""
import os

from dotenv import load_dotenv


def setup_langsmith_tracing() -> dict[str, str]:
    """加载 .env 并统一映射 LangSmith 环境变量。

    【项目自定义】兼容 LANGSMITH_* 和 LANGCHAIN_* 两套命名，
    最终写入 os.environ 供 LangChain 自动 tracing 读取。

    返回当前生效配置摘要（不含 api_key 明文）。
    """
    load_dotenv()

    tracing = os.getenv("LANGSMITH_TRACING", os.getenv("LANGCHAIN_TRACING_V2", ""))
    tracing_enabled = tracing.lower() in ("true", "1", "yes")
    if tracing_enabled:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
    else:
        # 显式关闭：防止 LangChain 因检测到 API key 而自动尝试连接
        # api.smith.langchain.com，国内 SSL 超时会打印大量错误日志。
        os.environ["LANGCHAIN_TRACING_V2"] = "false"

    api_key = os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY")
    if api_key:
        os.environ["LANGCHAIN_API_KEY"] = api_key
        os.environ["LANGSMITH_API_KEY"] = api_key

    project = (
        os.getenv("LANGCHAIN_PROJECT")
        or os.getenv("LANGSMITH_PROJECT")
        or "shill-guard-ai"
    )
    os.environ["LANGCHAIN_PROJECT"] = project

    return {
        "tracing_v2": os.environ.get("LANGCHAIN_TRACING_V2", "false"),
        "project": project,
        "api_key_set": bool(api_key),
    }
