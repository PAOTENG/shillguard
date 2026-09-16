所有信息确认完毕，输出完整准确版：

---

### 1. 对话消息历史（UI 展示用）

| 项目 | 详情 |
|---|---|
| **存储服务** | PostgreSQL |
| **数据库** | `shillguard` |
| **表名** | `chat_messages` |
| **字段** | `id`(bigint)、`thread_id`(text)、`user_id`(text)、`role`(text)、`content`(text)、`created_at`(timestamptz) |
| **内容** | 每一条用户消息和 AI 回复的完整明文文本，append-only 永不删除，实测 2348 条 |
| **读写代码** | `app/agents/chat/history_store.py` |

---

### 2. LangGraph 消息列表（Agent 工作记忆）

| 项目 | 详情 |
|---|---|
| **存储服务** | PostgreSQL |
| **数据库** | `shillguard` |
| **表名** | `checkpoint_blobs` |
| **字段** | `channel='messages'`，值在 `blob`(bytea)，msgpack 序列化的 LangChain BaseMessage 列表 |
| **内容** | 当前会话的消息窗口（HumanMessage / AIMessage / ToolMessage），会被 RemoveMessage 裁剪压缩 |
| **读写代码** | LangGraph `AsyncPostgresSaver` 自动管理，触发点在 `app/agents/chat/graph.py` 的 `memory_node` |

---

### 3. LLM 摘要（Summary）

| 项目 | 详情 |
|---|---|
| **存储服务** | PostgreSQL |
| **数据库** | `shillguard` |
| **表名** | `checkpoint_writes` |
| **字段** | `channel='summary'`，值在 `blob`(bytea)，msgpack 序列化字符串，实测 125 条 |
| **内容** | 旧消息压缩后的 bullet 摘要文本（如"• 用户姓名：张三 • 用户询问助手底层模型"），每次压缩后增量合并更新 |
| **触发条件** | 历史消息数 > `max_messages_before_summary=8` 时触发 |
| **读写代码** | `app/agents/chat/memory.py` 的 `summarize_old_messages`，`graph.py` 的 `memory_node` |

---

### 4. mem0 用户长期记忆

| 项目 | 详情 |
|---|---|
| **存储服务** | PostgreSQL（pgvector 扩展） |
| **数据库** | `shillguard` |
| **表名** | `shillguard_mem0` |
| **字段** | `id`(uuid)、`vector`(pgvector，1024维)、`payload`(jsonb，含 `data`/`hash`/`user_id` 等) |
| **内容** | mem0 从对话中提炼的用户事实，**以英文存储**（mem0 内部默认行为），如 `"User's name is Li Si."`，实测 5 条 |
| **检索方式** | 向量语义检索 + BM25 混合（pgvector 支持） |
| **读写代码** | `app/agents/chat/memory.py` 的 `search_memories`（读）/ `add_memories_background`（写） |

---

### 5. mem0 实体关系图

| 项目 | 详情 |
|---|---|
| **存储服务** | PostgreSQL（pgvector 扩展） |
| **数据库** | `shillguard` |
| **表名** | `shillguard_mem0_entities` |
| **字段** | `id`(uuid)、`vector`(pgvector，1024维)、`payload`(jsonb) |
| **内容** | mem0 自动抽取的实体及关系（人名、事件等），实测 14 条，由 mem0 内部自动维护 |
| **读写代码** | mem0 库内部自动管理，`app/agents/chat/memory.py` 间接触发 |

---

### 6. RAG 知识库文档向量（语义检索路）

| 项目 | 详情 |
|---|---|
| **存储服务** | ChromaDB（本地磁盘） |
| **路径** | `./data/chroma`（Windows 本机，项目目录下） |
| **Collection** | `shillguard_kg` |
| **内容** | 平台规则/法律文档切片后的向量（text-embedding-v3，1024维），用于语义相似度检索 |
| **检索方式** | L2 距离，阈值过滤 `rag_distance_threshold=0.6` |
| **读写代码** | 读：`app/rag/retriever.py` 的 `_vector_search_async`；写：`indexer.py`（手动建库时运行） |

---

### 7. RAG 知识库文档倒排索引（BM25 关键词检索路）

| 项目 | 详情 |
|---|---|
| **存储服务** | Elasticsearch |
| **地址** | `192.168.150.101:9200` |
| **索引名** | `shillguard_kg` |
| **字段** | `content`(text，IK分词)、`source`(keyword)、`chunk_id`(keyword) |
| **内容** | 与 ChromaDB 相同的文档切片，以倒排索引形式存储，用于关键词精确匹配（如法条号） |
| **分词器** | 建索引用 `ik_max_word`，查询用 `ik_smart` |
| **读写代码** | 读：`app/rag/es_client.py` 的 `es_search`；写：`app/rag/es_client.py` 的 `es_index_chunks`，由 `indexer.py` 调用 |