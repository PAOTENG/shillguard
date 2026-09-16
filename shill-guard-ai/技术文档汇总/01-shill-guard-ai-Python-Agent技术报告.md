# shill-guard-ai（Python Agent）技术报告

> 仓库：`D:\project\shill-guard-ai`  
> 范围：源码只读分析（`app/**/*.py` 为主）。不含改代码。  
> `app/` 下 **`.py` 文件数：72**。  
> 排除深度展开：`app/rag/sources` 法规 Markdown 语料 bulk、`data/` 运行时索引、`.venv`、`__pycache__`。

---

## 1. 项目定位与内容概览

本仓库是 ShillGuard 的 **AI 侧服务**：被 Java `shill-agent` 通过 HTTP 调用，同时可为 Cursor 暴露 MCP 工具，并为前端提供对话/续写/RAG 管理接口。

| 能力域 | 说明 |
|--------|------|
| Chat Agent | 多轮 SSE 对话、三层记忆、Adaptive RAG、Tavily 工具 |
| Moderation Agent | 举报内容审核（级联 + RAG + 证据 + 动作） |
| Detect | 恶意用户打分、SSE 流式、禁言证据生成 |
| Writer / ReAct | 帖子续写、ReAct 演示 |
| RAG | 父子分块、Chroma+ES 混合检索、RRF、远程 Rerank |
| MCP | `rag_search_laws` / `moderate_content` / `detect_user_score` / `generate_evidence` |
| Queue | RabbitMQ 审核异步 + Redis 任务状态 |

### 1.1 顶层目录

| 路径 | 用途 |
|------|------|
| `app/` | 全部业务源码 |
| `run.py` | Windows 下 SelectorEventLoop 启动 uvicorn（端口 8000） |
| `pyproject.toml` | 依赖声明 |
| `docs/` | 架构/流程/MQ/MCP 文档 |
| `scripts/` | 建索引、诊断、法规下载等工具脚本 |
| `eval/` / `loadtest/` / `tests/` | 评测与测试 |
| `data/` | Chroma、parents JSON、metrics 等运行时数据 |
| `.cursor/` | Cursor rules 与 MCP 配置 |

### 1.2 入口

| 入口 | 命令 / 行为 |
|------|-------------|
| HTTP | `python run.py` 或 `uvicorn app.main:app --port 8000` |
| MCP | `python -m app.mcp.server`（stdio） |
| 建索引 | `python -m app.rag.indexer` |
| ES 同步 | `python -m app.rag.sync_es_from_chroma` |

### 1.3 HTTP 路由一览（`app/main.py` 挂载）

| 方法 | 路径 | 模块 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/` | 本地测试页 `static/index.html` |
| POST | `/ai/chat` | 对话 SSE |
| GET | `/ai/history/{thread_id}`、`/ai/conversations` | 对话历史 |
| POST | `/ai/moderate`；GET `/ai/moderate/result/{taskId}` | 审核异步 |
| POST | `/ai/detect-users`、`/ai/detect-users-stream` | 恶意用户打分 |
| POST | `/ai/detect-evidence` | 禁言证据 |
| POST | `/ai/write`、`/ai/react` | 续写 / ReAct |
| `/ai/rag/*` | RAG 管理上传/列表/删/测题 | |
| `/ai/admin/*` | 级联实验开关 | |

---

## 2. `app/` 源码树

```
app/
├── main.py, config.py, llm.py, schemas.py, utils.py, admin_router.py
├── agents/
│   ├── chat/          对话
│   ├── moderation/    审核 + detect 打分
│   ├── detect/        证据生成
│   ├── writer/        续写
│   └── react/         ReAct 演示
├── rag/               检索/索引/分块/重排
├── mcp/               FastMCP
├── queue/             RabbitMQ + Redis task_store
├── observability/     LangSmith
└── tools/             Tavily
```

---

## 3. 逐文件：类 / 函数与功能

> 下列按目录列出。`__init__.py` 若仅文档/空包则注明。

### 3.1 根模块

#### `app/main.py`
| 符号 | 功能 |
|------|------|
| `lifespan(app)` | 启动/停止审核 RabbitMQ 消费者 |
| `health()` | `GET /health` → `{"status":"ok"}` |
| `index()` | 返回本地测试 HTML |

另：Windows 事件循环策略、HF 离线、MEM0/Chroma 遥测关闭、LangSmith setup；挂载全部 router。

#### `app/config.py`
| 符号 | 功能 |
|------|------|
| `Settings` | pydantic-settings：LLM/RAG/级联/MQ/PG/Redis/各 API Key |
| `settings` | 全局单例 |

要点字段：`cascade_*`、`rabbitmq_*`、`moderation_mq_*`、`pg_*`、`redis_*`、`rag_*`、`es_url`、`chat_max_concurrent`、`java_base_url` 等。

#### `app/llm.py`
| 符号 | 功能 |
|------|------|
| `get_llm()` | 主 ChatOpenAI（流式，带缓存） |
| `get_expander_llm()` | 轻量 LLM（Step-Back / CRAG / 路由） |

#### `app/schemas.py`
| 符号 | 功能 |
|------|------|
| `ChatRequest` | `/ai/react` 请求体 |
| `WriteRequest` | `/ai/write` 请求体 |
| `ChatChunk` | SSE delta 模型（路由中基本未用） |

#### `app/utils.py`
| 符号 | 功能 |
|------|------|
| `parse_json_from_llm(text)` | 从 LLM 自由文本抠 JSON |

#### `app/admin_router.py`
| 符号 | 功能 |
|------|------|
| `ExperimentRequest` / `ExperimentResponse` | 实验开关 DTO |
| `set_experiment` | 运行时切换 cascade + LangSmith 项目名 |
| `get_experiment_status` | 读当前实验状态 |

---

### 3.2 Chat — `app/agents/chat/`

#### `schemas.py`
| 符号 | 功能 |
|------|------|
| `WorkerContextResult` | Worker 结构化背景事实 |
| `.sanitize_fact` | 清洗 bullet / 截断 |
| `.to_processed_context` | 转为 Main LLM 可用字符串 |

#### `prompts.py`
| 符号 | 功能 |
|------|------|
| `SYSTEM_PROMPT` | 主对话角色规则 |
| `build_system_prompt(...)` | 拼 system：processed_context + doc_context + 北京时间 |

#### `output_sanitizer.py`
| 符号 | 功能 |
|------|------|
| `strip_leading_context_echo` | 旧版去回声（架构隔离后基本不用） |

#### `history_store.py`
| 符号 | 功能 |
|------|------|
| `ensure_table(pool)` | 建 `chat_messages` 表与索引 |
| `append_message(...)` | 追加一条 UI 消息 |
| `get_messages(...)` | 读整线程历史 |

#### `history_router.py`
| 符号 | 功能 |
|------|------|
| `get_history` | `GET /ai/history/{thread_id}` |
| `list_conversations` | `GET /ai/conversations` |

#### `memory.py`
| 符号 | 功能 |
|------|------|
| `_build_mem0_config` | mem0：LLM+embed+pgvector |
| `get_mem0` | 懒加载单例 |
| `search_memories` | 第三层语义记忆检索 |
| `add_memories_background` | 异步写入 + AMG 防护 |
| `format_user_said_history` | 抽用户说过的话给 Worker |
| `summarize_old_messages` | 第二层旧消息摘要 |

#### `graph.py`
| 符号 | 功能 |
|------|------|
| `_sanitize_window` | 修复截断的 tool-call 消息组 |
| `ChatState` | TypedDict 状态 |
| `get_pg_pool` | 异步 PG 连接池 |
| `memory_node` | mem0 检索 ∥ 可选摘要 |
| `_should_retrieve` | Adaptive RAG 是否检索 |
| `rag_node` | 条件混合检索 → `rag_context` |
| `context_processor_node` | Worker 隔离背景事实 |
| `chat_node` | Main LLM + bind_tools + 信号量 |
| `build_graph` / `get_graph` | 编译图 + Postgres checkpointer |

图拓扑概要：`memory ∥ rag → context_processor → chat ⇄ tools`。

#### `router.py`
| 符号 | 功能 |
|------|------|
| `chat(...)` | `POST /ai/chat` multipart SSE；并发限制；文档解析；双写历史；流后写 mem0 |

---

### 3.3 Detect 证据 — `app/agents/detect/`

#### `prompts.py`
常量：`SYSTEM_PROMPT` / `IDENTIFY_PROMPT` / `EVIDENCE_PROMPT`。

#### `schemas.py`
| 符号 | 功能 |
|------|------|
| `UserEvidenceInput` | 单用户输入 |
| `DetectEvidenceRequest` | 批请求 |
| `UserEvidenceResult` | Markdown 证据 |
| `DetectEvidenceResponse` | 批结果 |

#### `graph.py`
| 符号 | 功能 |
|------|------|
| `DetectEvidenceState` | 状态 |
| `_parse_json_from_llm` | JSON 抽取 |
| `retrieve_node` | 三路 RAG + CRAG |
| `identify_node` | 细标违规条目+法条 |
| `evidence_node` | 生成禁言证据 Markdown |
| `citation_verify_node` | 修补幻觉法条引用 |
| `build_graph` | 线性四节点 |

#### `router.py`
| 符号 | 功能 |
|------|------|
| `get_graph` | 懒加载图 |
| `detect_evidence` | `POST /ai/detect-evidence` |

---

### 3.4 Moderation — `app/agents/moderation/`

#### `prompts.py`
| 符号 | 功能 |
|------|------|
| `SYSTEM/CLASSIFY/JUDGE/EVIDENCE_PROMPT` | 审核提示词 |
| `REPORT_CATEGORY_MAP` / `get_report_category_desc` | 举报类目映射 |

#### `schemas.py`
`ModerateRequest/Result/Response/SubmitResponse/TaskResult` — 与 Java DTO 对齐。

#### `cascade.py`
| 符号 | 功能 |
|------|------|
| `BLACKLIST` | T1 关键词与预设法条分 |
| `_blacklist_hit` / `_weighted_score` / `_clearly_normal` | T1 启发式 |
| `_templated_evidence` | T1 模板证据 |
| `pre_filter_node` | 级联：clear_violation / clear_normal / ambiguous |

#### `citation_verifier.py`
| 符号 | 功能 |
|------|------|
| `_extract_law_names` / `_is_grounded` | 法名抽取与 grounding |
| `verify_and_patch_citations` / `citation_verify_node` | 校验修补 |

#### `api_evidence.py` / `api_label_map.py`
商业 API 命中后的模板证据；Aliyun/Yidun 标签 → 内部违规类型。

#### `api_moderation/`
| 文件 | 符号要点 |
|------|----------|
| `__init__.py` | `check_text_api` / `check_text_api_batch` |
| `base.py` | `ModerationApiResult` |
| `aliyun.py` | 客户端、风险分映射、解析、mock、`check_text_aliyun` |
| `yidun.py` | 签名、解析、mock、`check_text_yidun`（回滚保留） |

#### `graph.py`
| 符号 | 功能 |
|------|------|
| `ModerationState` | 全状态 |
| `classify_node` | 内容类型分类 |
| `retrieve_node` | Q1/Q2/Q3 并行检索 |
| `crag_filter_node` | CRAG 过滤 |
| `judge_node` | 打分+规则+法条 |
| `evidence_node` | LLM 证据（级联已填则跳过） |
| `action_node` | none / manual_review / auto_mute |
| `route_after_*` | 条件边 |
| `build_graph` | 约 8 节点含短路 |

阈值（配置）：异常分 ≥0.8 自动禁言，≥0.6 人工复核。

#### `router.py`
| 符号 | 功能 |
|------|------|
| `get_graph` | 懒加载 |
| `_append_metric_line` / `_log_cascade_metric` | 级联指标 JSONL |
| `_run_moderate_task` | 跑图写 task_store |
| `handle_moderate_job` | MQ Worker 入口 |
| `moderate` | `POST /ai/moderate` → taskId |
| `moderate_result` | `GET /ai/moderate/result/{taskId}` |

#### `detect_prompts.py` / `detect_router.py` / `detect_stream_router.py`
| 符号 | 功能 |
|------|------|
| `DETECT_SCORE_PROMPT` 等 | 旧版/MCP 全量打分提示 |
| `_t3_llm_judge` / `_cascade_single` / `_process_user` | 单内容级联+禁言策略 |
| `detect_users` | `POST /ai/detect-users` |
| `_score_user` | 旧全量 RAG 打分（MCP/流复用） |
| `_sse` / `_stream_detect` / `detect_users_stream` | SSE 流式检测 |

禁言策略摘要：违规条数 0→none，1→mute_3days，≥2→mute_7days（可提前结束）。

---

### 3.5 Writer / React

#### `app/agents/writer/`
| 文件 | 符号 | 功能 |
|------|------|------|
| `prompts.py` | `SYSTEM_PROMPT` | 续写约束 |
| `graph.py` | `WriteState`, `write_node`, `build_graph` | 单节点续写 |
| `router.py` | `write_post` | `POST /ai/write` SSE |

#### `app/agents/react/`
| 文件 | 符号 | 功能 |
|------|------|------|
| `tools.py` | `calculator`, `search_web` | 演示工具 |
| `graph.py` | `agent_node`, `should_continue`, `build_graph` | ReAct 环 |
| `router.py` | `react` | `POST /ai/react` SSE（含 tool 事件） |

---

### 3.6 RAG — `app/rag/`

| 文件 | 主要符号 | 功能 |
|------|----------|------|
| `retriever.py` | `_vector_search_async`, `_rrf_fusion`, `_expand_parents`, `retrieve` | 混合检索主 API |
| `es_client.py` | `ensure_index`, `es_index_chunks`, `es_search`, `es_delete_by_source`… | ES BM25（IK） |
| `indexer.py` | `build_index`, 分批 embed/purge 等 | CLI 建父子索引→Chroma+ES+JSON |
| `sync_es_from_chroma.py` | `sync_es_from_chroma` | 从 Chroma 重建 ES |
| `parent_child_splitter.py` | `ChildChunk/ParentChunk/SplitResult`, `split_parent_child`, `split_document` | 法规/平台文档父子切分 |
| `parent_store.py` | `load/get/save/upsert/delete_parents*` | `rag_parents.json` |
| `admin_router.py` | `upload_to_kb`, `list_documents`, `delete_document`, `generate_tests` | HTTP RAG 管理 |
| `query_expander.py` | `_generate_stepback_queries`, `expand_queries`, `dedup_and_merge` | 查询扩展与多路合并 |
| `law_taxonomy.py` | `TAXONOMY`, `get_search_terms` 等 | 内容类型→检索词本体 |
| `crag_filter.py` | `score_chunks`, `filter_chunks_by_score`, `crag_filter` | CRAG |
| `reranker.py` | `_get_reranker`, `rerank`, `rerank_api` | 本地 FlagEmbedding / SiliconFlow 远程 |
| `bm25_index.py` | `BM25Index`, `get_bm25_index` | 本地 BM25（遗留；生产用 ES） |
| `doc_parser.py` | `parse_document`, `parse_upload_file`, 各格式/OCR 私有函数 | 多格式转文本 |

生产检索链路概要：  
`expand → (vector ∥ ES BM25) → RRF → rerank_api → parent expand → (可选 CRAG)`。

---

### 3.7 MCP — `app/mcp/`

| 文件 | 符号 | 功能 |
|------|------|------|
| `__init__.py` | `mcp = FastMCP("ShillGuard")` | 单例（防双 import 0 tools） |
| `server.py` | `_print_to_stderr`, `mcp.run()` | stdio 入口；chdir/HF offline/禁本地 rerank |
| `tools_rag.py` | `rag_search_laws` | 包装 `retrieve` |
| `tools_moderation.py` | `moderate_content` | 同步跑审核图 |
| `tools_detect.py` | `detect_user_score`, `generate_evidence` | 打分 + 证据图 |

---

### 3.8 Queue / Observability / Tools

#### `app/queue/task_store.py`
| 符号 | 功能 |
|------|------|
| `TaskStore.set/get` | Redis（失败则内存）存审核任务状态 |
| `task_store` | 单例 |

#### `app/queue/moderation_mq.py`
| 符号 | 功能 |
|------|------|
| `_amqp_url` / `_ensure_topology` | AMQP 与拓扑声明 |
| `publish_moderate_job` | 持久化投递 |
| `start_moderation_consumer` / `_handle_message` | 消费循环 |
| `close_moderation_mq` | 关闭 |

拓扑：Exchange `shillguard.exchange`（Topic），RK `ai.moderate.request`，Queue `ai.moderate.queue`。

#### `app/observability/langsmith_setup.py`
| 符号 | 功能 |
|------|------|
| `setup_langsmith_tracing` | 读 `.env`，规范 LANGSMITH_/LANGCHAIN_ 变量 |

#### `app/tools/tools.py`
| 符号 | 功能 |
|------|------|
| `get_web_search_tool` | Tavily StructuredTool |

---

## 4. 关键业务流程（复查用）

### 4.1 审核
`pre_filter` →（短路 clear）或 `classify → retrieve → crag → judge → evidence → citation_verify → action`；异步 MQ + Redis。

### 4.2 对话
并发：`memory_node ∥ rag_node` → `context_processor` → `chat`⇄`tools`；UI 历史与 checkpointer 分离；mem0 流后异步写。

### 4.3 MCP vs HTTP
MCP 供 Cursor/外部客户端；Chat 主路径不调用自家 MCP，内部直接调函数/图。

---

## 5. 依赖（`pyproject.toml` 声明）

`fastapi`, `uvicorn[standard]`, `pydantic-settings`, `langgraph`, `langchain-openai`, `langchain-core`, `python-dotenv`, `chromadb`, `langchain-chroma`, PDF/DOCX/multipart, `httpx`, 阿里云 Green SDK, `mem0ai`, `tiktoken`, `agent-memory-guard`, `aio-pika`, `redis`；Python ≥3.11。

代码还用到但未全列在 toml：`mcp`, `elasticsearch`, `psycopg`/`psycopg_pool`, `langgraph.checkpoint.postgres`, `langchain_tavily`, `jieba`, `FlagEmbedding`（可选）等——环境需手动对齐。

---

## 6. 配置与运维注意

- 默认连 VM：`192.168.150.101`（PG/Redis/ES/MQ）。  
- Windows 启动务必用 `run.py`（SelectorEventLoop）。  
- MCP 子进程可设 `SHILLGUARD_DISABLE_RERANK=1`（配置/server 侧已有硬化）。  
- 指标文件：`data/cascade_metrics.jsonl`。  
- **复查点**：`config.py` 默认密钥、README 过时、本地 BM25 vs ES 双路径。

---

## 7. 复查检查清单

- [ ] 新增 Agent 是否挂到 `main.py`  
- [ ] 与 Java DTO 字段是否同步（moderate/detect/evidence）  
- [ ] MQ 拓扑名是否与 Java `RabbitMqConfig` 一致  
- [ ] RAG 索引变更后是否同步 Chroma+ES+parents  
- [ ] MCP 工具是否仍从同一 `mcp` 单例注册  

本报告为第一轮全量盘点；复查时可按文件路径对函数名做 diff 核对。
