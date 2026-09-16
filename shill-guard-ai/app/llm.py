"""统一 LLM 工厂：换模型/换厂商只改这里。

【设计模式】工厂 + 单例（@lru_cache 保证进程内只创建一次 ChatOpenAI 实例）

【为什么用 langchain_openai.ChatOpenAI 调 DeepSeek/百炼？】
DeepSeek、阿里百炼、硅基流动等都提供 OpenAI 兼容 REST API（/v1/chat/completions），
LangChain 官方 ChatOpenAI 只需改 base_url + api_key 即可对接，无需换类。
官方文档: https://python.langchain.com/docs/integrations/chat/openai/
"""
from functools import lru_cache  # 【官方 Python】无参函数结果缓存，等价于进程内单例

from langchain_openai import ChatOpenAI  # 【官方 LangChain】OpenAI 兼容 Chat 模型封装
from app.config import settings


@lru_cache
def get_llm() -> ChatOpenAI:
    """主 LLM（用于 moderation 的 classify/judge/evidence 节点、detect 打分等）。

    返回 ChatOpenAI 实例，调用方式：
      - 同步: llm.invoke([SystemMessage(...), HumanMessage(...)]) -> AIMessage
      - 异步: await llm.ainvoke(msgs) -> AIMessage
      - 流式: llm.stream(msgs) / llm.astream(msgs) 逐 token 产出
    """
    return ChatOpenAI(
        model=settings.llm_model,           # 模型名，如 deepseek-v4-flash
        api_key=settings.llm_api_key,       # API 密钥，从 .env 的 LLM_API_KEY 读取
        base_url=settings.llm_base_url or None,  # None=OpenAI 官方地址；填 URL 则走兼容端点
        streaming=True,                     # 允许 stream/astream；不影响 invoke 同步调用
    )


@lru_cache
def get_expander_llm() -> ChatOpenAI:
    """Step-Back 查询扩展专用 LLM（轻量/便宜，与主 LLM 独立配置）。

    【项目自定义】RAG 三路检索的 Q3 查询扩展用此模型，与主审核 LLM 分开：
      - 可用更便宜的 flash 模型，降低成本
      - 扩展失败不影响主流程（query_expander 有回退逻辑）

    在 .env 中配置（字段名自动映射，pydantic-settings 规则：llm_api_key -> LLM_API_KEY）：
        EXPANDER_MODEL=deepseek-v4-flash
        EXPANDER_API_KEY=sk-xxx      # 留空则复用 LLM_API_KEY
        EXPANDER_BASE_URL=https://...  # 留空则复用 LLM_BASE_URL
    """
    api_key = settings.expander_api_key or settings.llm_api_key
    base_url = settings.expander_base_url or settings.llm_base_url or None
    return ChatOpenAI(
        model=settings.expander_model,
        api_key=api_key,
        base_url=base_url,
        streaming=False,    # 扩展查询只需完整 JSON，不需要 SSE 流式
        temperature=0.0,    # 【官方参数】0=确定性输出，避免每次扩展词不同导致检索不稳定
    )
