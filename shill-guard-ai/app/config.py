"""全局配置：从 .env 文件和环境变量自动读取。

【官方 pydantic-settings 机制】
  - 继承 BaseSettings，字段名 llm_api_key 自动映射环境变量 LLM_API_KEY（不区分大小写）
  - SettingsConfigDict(env_file=".env") 指定配置文件路径
  - extra="ignore" 忽略 .env 中未在类里声明的多余字段

【使用方式】
  from app.config import settings
  settings.llm_model  # 直接访问，无需每次实例化

官方文档: https://docs.pydantic.dev/latest/concepts/pydantic_settings/
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """所有可配置项。默认值供本地开发；生产环境在 .env 中覆盖。"""

    # ── LLM（主模型，用于审核/检测/对话）──
    llm_api_key: str = ""                    # .env: LLM_API_KEY
    llm_model: str = "deepseek-v4-flash"     # .env: LLM_MODEL
    llm_base_url: str | None = None          # .env: LLM_BASE_URL；None=OpenAI 官方地址

    # ── 对话记忆（chat agent）──
    max_messages_before_summary: int = 8     # 历史消息超过此数触发 LLM 摘要压缩（= keep + 2，节奏更紧凑）
    keep_recent_messages: int = 6            # 压缩后保留最近 N 条原文（建议偶数，每轮=2条）
    mem0_chroma_path: str = "./data/mem0_chroma"  # 已废弃：mem0 向量后端已迁移至 pgvector，此字段保留仅供旧数据引用
    mem0_search_limit: int = 8               # 每次问答从 mem0 检索的记忆条数上限（长对话时覆盖更多相关事实）
    mem0_enabled: bool = True                # False=禁用 mem0（测试/离线环境）

    # ── Java 微服务地址 ──
    java_base_url: str = "http://127.0.0.1:18080"

    # ── RAG 存储路径 ──
    chroma_dir: str = "./data/chroma"        # ChromaDB 向量库持久化目录
    rag_parent_store_path: str = "./data/rag_parents.json"  # parent-child 的 parent 回填映射
    memory_db_path: str = "./data/memory.db" # 旧版 SQLite 记忆（已被 PostgreSQL 替代）

    # ── RAG 检索参数 ──
    rag_recall_k: int = 20                   # 向量/BM25 每路召回数
    rag_rerank_top_k: int = 5                # rerank 后最终保留数
    rag_distance_threshold: float = 0.6      # 向量距离过滤阈值（L2，越小越相似）
    rag_min_relevance_score: float = 0.3     # reranker 分数低于此值的 chunk 丢弃，避免无关内容浪费 token

    # ── Elasticsearch（BM25 关键词检索）──
    es_url: str = "http://127.0.0.1:9201"

    # ── Step-Back 查询扩展专用模型（与主 LLM 分开，可用更便宜的 flash 模型）──
    expander_model: str = "deepseek-v4-flash"
    expander_api_key: str = ""               # 留空时 llm.py 回退到 llm_api_key
    expander_base_url: str = ""              # 留空时回退到 llm_base_url

    # ── LangSmith 可观测（tracing）──
    langchain_project: str = "shillguard-cascade-ON"  # 对应 LANGCHAIN_PROJECT 环境变量

    # ── 审核级联（cascade.py）──
    cascade_enabled: bool = True             # False=全部退回 LLM，零回归测试用
    cascade_normal_max_length: int = 15      # 白名单：文本长度上限（字）
    cascade_weighted_high_threshold: float = 0.55  # T2 加权≥此值 → clear_violation
    cascade_weighted_low_threshold: float = 0.2    # T2 加权<此值（且满足白名单其他条件）→ clear_normal

    # ── T2 商业 API 文本审核（aliyun | yidun 可选）──
    cascade_api_enabled: bool = False        # 默认关，避免没密钥启动报错
    cascade_api_provider: str = "aliyun"     # aliyun | yidun | baidu（预留）
    cascade_api_timeout_ms: int = 800          # 超时 fail-open 退回 LLM
    cascade_api_block_threshold: float = 0.85  # API 风险分≥此值 → clear_violation
    cascade_api_pass_threshold: float = 0.15   # API 风险分≤此值 → clear_normal（第一期建议设0关闭）
    cascade_api_gray_low: float = 0.40         # 灰区下界（在此区间内继续走后续级联）
    cascade_api_gray_high: float = 0.70        # 灰区上界
    cascade_api_mock: bool = False             # True=不调真 API，走本地 mock（评测用）

    # ── 阿里云内容安全（T2-api 主力）──
    aliyun_access_key_id: str = ""            # RAM AccessKey ID（非百炼 sk-xxx）
    aliyun_access_key_secret: str = ""        # RAM AccessKey Secret
    aliyun_green_region: str = "cn-shanghai"
    aliyun_green_endpoint: str = "green-cip.cn-shanghai.aliyuncs.com"
    aliyun_green_service: str = "comment_detection_pro"  # 公聊评论检测_专业版

    # ── 网易易盾（已弃用，保留供回滚）──
    yidun_secret_id: str = ""
    yidun_secret_key: str = ""
    yidun_business_id: str = ""
    yidun_api_url: str = "http://as.dun.163.com/v5/text/check"
    yidun_api_version: str = "v5.3"

    # ── 申诉审核（预留，待实现 appeal agent）──
    appeal_time_limit_days: int = 15
    appeal_uphold_threshold: float = 0.6       # 复核分≥此值 → 维持原判
    appeal_overturn_threshold: float = 0.3   # 复核分<此值 → 撤销（误判）
    appeal_mitigate_base_days: int = 3         # 0.3~0.6 减刑区间的基础禁言天数

    # ── Reranker ──
    reranker_model: str = "BAAI/bge-reranker-v2-m3"  # 本地 reranker 模型名（已改用 API）
    chat_max_concurrent: int = 50              # chat 接口最大并发，超过返回 429
    siliconflow_api_key: str = ""  # 硅基流动 rerank API 密钥（生产请改 .env）
    siliconflow_rerank_url: str = "https://api.siliconflow.cn/v1/rerank"

    bm25_index_path: str = "./data/bm25_index.json"  # BM25 索引持久化（备用）

    # ── 联网搜索（chat agent 工具）──
    tavily_api_key: str = "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"  # Tavily 搜索 API 密钥（生产请改 .env）

    # ── PostgreSQL（LangGraph checkpointer，chat 多轮记忆）──
    pg_host: str = "127.0.0.1"
    pg_port: int = 5432
    pg_dbname: str = "shillguard"
    pg_user: str = "postgres"
    pg_password: str = "shillguard123"

    # ── Redis（任务状态；MQ 开启时供 Java 轮询跨进程读结果）──
    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_password: str = "shillguard123"
    redis_db: int = 0

    # ── RabbitMQ（审核异步：替换 BackgroundTasks，对齐 Java shillguard.exchange）──
    moderation_queue_enabled: bool = True          # False=回退 FastAPI BackgroundTasks
    moderation_queue_strict: bool = False          # True=入队失败直接 503（默认降级 BackgroundTasks）
    rabbitmq_host: str = "127.0.0.1"
    rabbitmq_port: int = 5672
    rabbitmq_username: str = "admin"
    rabbitmq_password: str = "shillguard123"
    rabbitmq_vhost: str = "/"
    rabbitmq_exchange: str = "shillguard.exchange"
    moderation_mq_queue: str = "ai.moderate.queue"
    moderation_mq_routing_key: str = "ai.moderate.request"
    moderation_mq_prefetch: int = 2                # 同时处理的灰区审核数
    moderation_task_key_prefix: str = "moderation:task:"
    moderation_task_ttl_seconds: int = 3600        # 结果保留 1 小时

    # ── Embedding（阿里百炼，与 LLM 账号分开）──
    embed_api_key: str = ""  # 生产请改 .env
    embed_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    embedding_model: str = "text-embedding-v3"

    # ── 审核处罚阈值（action_node 使用）──
    moderation_auto_mute_threshold: float = 0.8     # ≥0.8 → auto_mute
    moderation_manual_review_threshold: float = 0.6  # ≥0.6 → manual_review / 生成证据
    moderation_mute_days_default: int = 30           # 默认禁言天数（Java 侧使用）
    moderation_severe_mute_days: int = 9999          # 严重违规永久禁言标记

    # pydantic-settings 元配置
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # .env 里多写的变量不报错
    )


# 模块级单例：整个进程共享一份配置
settings = Settings()
