# Chat Agent 完整流程与数据流向

> 本文档基于实际运行代码 + 真实数据库查询结果生成。  
> 查询时间：2026-07-12  
> 数据来源：PostgreSQL `shillguard` 库、ChromaDB `./data/chroma`、mem0 ChromaDB `./data/mem0_chroma`

---

## 一、核心问题澄清：PostgreSQL 存什么？向量存哪里？

| 存储系统 | 存的是什么 | 是否存向量 |
|---------|-----------|-----------|
| **PostgreSQL** | 对话历史（用户消息 + LLM 回答文本）、摘要文本、用户 ID 等 State 字段，序列化为二进制 | **否，完全没有向量** |
| **RAG ChromaDB** (`./data/chroma`) | 知识库文档切片（chunk）的**原文 + 向量**，共 14178 条 | **是** |
| **mem0 ChromaDB** (`./data/mem0_chroma`) | 从对话提取的用户记忆事实的**原文 + 向量** | **是** |
| **Elasticsearch** | 知识库文档切片的全文索引（BM25 关键词检索，无向量） | **否** |

**关键结论：PostgreSQL 里存的是对话消息（原文文本），不是向量。向量只存在 ChromaDB 里。**

---

## 二、整体架构图

```
┌─────────────────────────────────────────────────────────────────────┐
│                        前端 / Java 后端                              │
│  POST /ai/chat  { message, thread_id, user_id, [files] }           │
└───────────────────────────────┬─────────────────────────────────────┘
                                │ HTTP multipart/form-data
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   FastAPI router.py  /ai/chat                       │
│  1. 并发计数守卫（_CHAT_IN_FLIGHT < chat_max_concurrent=50）        │
│  2. 解析上传文件 → doc_text                                         │
│  3. 构造 inputs = {messages:[HumanMessage], doc_context, user_id}  │
│  4. 调用 graph.astream_events(inputs, config)                       │
│  5. 逐 token 发 SSE: data: {"delta": "..."}                         │
│  6. 结束后 asyncio.create_task(add_memories_background(...))        │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                 ┌──────────────▼──────────────────────┐
                 │   LangGraph StateGraph (graph.py)    │
                 │   checkpointer = AsyncPostgresSaver  │
                 │   thread_id → 从 PostgreSQL 恢复     │
                 │   state 上次的所有字段                │
                 └──────────────┬──────────────────────┘
                                │
        ┌───────────────────────┼───────────────────────────┐
        │                       │                           │
        ▼                       ▼                           ▼
  [节点1]               [节点2]                    [节点3]
  memory_node           rag_node                  chat_node
  （先跑）              （次跑）                  （最后跑）
        │                       │                           │
        └───────────────────────┴───────────────────────────┘
                                │
                   [条件分支] tools_condition
                    有 tool_call ──→ [节点4] tools → 回 chat
                    无 tool_call ──→ END（返回 SSE）
```

---

## 三、逐节点详细流程 + 数据写入

### 节点 0（前置）：LangGraph 从 PostgreSQL 恢复 State

```
thread_id = "user_xxx_session_yyy"
                │
                ▼
        AsyncPostgresSaver
        SELECT FROM checkpoints WHERE thread_id = ?
                │
                ▼
        反序列化 checkpoint_blobs 中的各 channel blob
        重建 ChatState：
          messages           = [旧 HumanMessage, 旧 AIMessage, ...]
          summary            = "上次生成的摘要文本..."
          long_term_memories = ""（每轮由 memory_node 重新填充）
          user_id            = "test_user_001"
          rag_context        = ""（每轮由 rag_node 重新填充）
          doc_context        = ""（由 router 填充）
                │
                ▼
        add_messages reducer 追加本轮新 HumanMessage
        state["messages"] 现在包含所有历史 + 本轮用户消息
```

**此时 PostgreSQL 的读操作：**

| 表 | 操作 | 读取内容 |
|----|------|---------|
| `checkpoints` | SELECT | `checkpoint_id`, `type`, `checkpoint`(JSONB 含 channel_versions) |
| `checkpoint_blobs` | SELECT | `channel`=messages/summary/user_id 等字段的序列化 blob |

---

### 节点 1：`memory_node` — 记忆检索 + LLM 摘要压缩

```
state["messages"] = [msg1, msg2, ..., msg_N_new]
                │
                ├── current_query = msg_N_new.content  （本轮用户问题）
                ├── history = [msg1, ..., msg_{N-1}]   （不含本轮新消息）
                │
                ├────────────────── 并发执行 ──────────────────────
                │                                                  │
                ▼ asyncio.create_task A                            ▼ asyncio.create_task B
        mem0.search(current_query,                    len(history) > 10 ?
                    user_id=user_id,                      │
                    limit=5)                              ├── 否 → 跳过，保留旧 summary
                │                                         └── 是 →
                ▼                                             to_summarize = history[:-6]
        查 mem0 ChromaDB:                                      （保留最近6条原文）
          1. 把 current_query 向量化                            │
             (阿里百炼 text-embedding-v3)                        ▼
          2. 在 shillguard_mem0 集合中                    LLM.ainvoke([
             向量相似度搜索 top-5                            SystemMessage(摘要Prompt),
          3. 返回记忆文本列表                               HumanMessage(旧消息文本)
                │                                         ])
                ▼                                              │
        long_term_memories =                                   ▼
          "- 用户叫小明\n                              new_summary = LLM 返回的摘要
           - 用户喜欢Python\n                         （≤200字，合并旧 summary）
           ..."
                │                                              │
                └──────────────────── 汇总 ───────────────────┘
                                       │
                                       ▼
                        return {
                            "long_term_memories": "- 用户叫小明\n...",
                            "summary": "用户小明，Python工程师，..."
                        }
```

**此步骤的数据库操作：**

| 数据库 | 集合/表 | 操作 | 内容 |
|--------|--------|------|------|
| **mem0 ChromaDB** (`./data/mem0_chroma`) | `shillguard_mem0` | **READ** 向量相似度查询 | 查询向量 ↔ 用户历史记忆向量比对，返回最相关的5条记忆文本 |
| **阿里百炼 API** | 远程 API | **调用** | 把 current_query 文本 → 向量（1536维），用于 mem0 检索 |
| **DeepSeek LLM API** | 远程 API | **调用**（条件触发） | messages > 10 时调用 LLM 生成摘要，约 200 字 |

> **没有写入操作**，写入发生在 SSE 结束后（见节点后置）

---

### 节点 2：`rag_node` — 混合检索 + 重排序

```
query = state["messages"][-1].content  （用户本轮问题）
                │
                ├─────────────────── 双路并行召回 ──────────────────────
                │                                                      │
                ▼ asyncio.gather A                                     ▼ asyncio.gather B
        向量检索（ChromaDB）                              BM25 检索（Elasticsearch）
          1. 阿里百炼 embed(query) → 1536维向量            query → ES 分词 → BM25 算分
          2. ChromaDB shillguard_kg 集合                  → top-20 chunk（关键词匹配）
             L2 距离搜索 top-20
          3. 过滤距离 > 0.6 的结果
          → top-20 chunk（语义匹配）
                │                                                      │
                └────────────────── RRF 融合 ──────────────────────────┘
                                       │
                              score(chunk) = Σ 1/(60 + rank + 1)
                              两路各自排名靠前的 chunk 得分更高
                                       │
                                       ▼
                              取融合后 top-5 候选
                                       │
                                       ▼
                         Cross-Encoder 精排（硅基流动 API）
                         POST https://api.siliconflow.cn/v1/rerank
                         模型: BAAI/bge-reranker-v2-m3
                         → 按语义相关性重新打分，取 top-5
                                       │
                                       ▼
                        rag_context = "chunk1文本\n\nchunk2文本\n..."
                        return {"rag_context": rag_context}
```

**此步骤的数据库操作：**

| 数据库 | 集合/索引 | 操作 | 内容 |
|--------|----------|------|------|
| **RAG ChromaDB** (`./data/chroma`) | `shillguard_kg`（14178条） | **READ** 向量相似度查询 | 返回最相关的知识库 chunk 文本，不含向量 |
| **Elasticsearch** | `shillguard_kg` 索引 | **READ** BM25 查询 | 返回关键词匹配的 chunk 文本 |
| **阿里百炼 API** | 远程 API | **调用** | query → 向量 |
| **硅基流动 API** | 远程 API | **调用** | cross-encoder 重排序 |

> **没有写入操作**

---

### 节点 3：`chat_node` — LLM 推理（含滑动窗口）

```
all_messages = state["messages"]   # PostgreSQL 里的所有历史消息
window_messages = all_messages[-6:]  # 【滑动窗口】只取最近6条传给LLM
                                      # 全量历史仍在PostgreSQL，不删除

system_prompt = build_system_prompt(
    doc_context        = state["doc_context"],       # 用户上传文档（若有）
    rag_context        = state["rag_context"],        # 节点2检索结果
    summary            = state["summary"],            # 节点1生成的历史摘要
    long_term_memories = state["long_term_memories"], # 节点1的mem0检索结果
)
# system_prompt 结构：
#   角色定义
#   + 当前北京时间
#   + ## 关于这位用户的长期记忆（mem0结果）
#   + ## 历史对话摘要（summary）
#   + ## 参考知识库（RAG结果）
#   + ## 用户上传的文档（若有）

msgs_to_llm = [SystemMessage(system_prompt)] + window_messages
# 注意：LLM 只看 1(system) + 6(window) = 7条消息
# PostgreSQL 里可能有上百条，但LLM看不到，靠 summary 了解旧内容

result = await llm_with_tools.ainvoke(msgs_to_llm)
# llm = DeepSeek / 百炼（OpenAI 兼容 API）
# llm_with_tools = llm.bind_tools([web_search_tool])
# 若 LLM 决定联网搜索，result 包含 tool_calls

return {"messages": [result]}  # AIMessage 追加到 state["messages"]
```

**此步骤的数据库操作：**

| 数据库 | 操作 | 内容 |
|--------|------|------|
| **DeepSeek/百炼 LLM API** | **调用** | 发送 7 条消息，接收流式 token |
| PostgreSQL | **无直接操作** | LangGraph 在节点结束后才写入 |

---

### 节点 4（条件）：`tools` — 联网搜索工具

```
若 chat_node 的 AIMessage 包含 tool_calls:
    tool = TavilySearchTool
    result = tavily_api_key 调用 Tavily 搜索 API
    → 搜索结果作为 ToolMessage 追加到 messages
    → 回到 chat_node 再次调用 LLM（看到搜索结果后给出最终答案）

若无 tool_calls：
    直接 END
```

---

### 节点后置：LangGraph 自动写入 PostgreSQL Checkpoint

```
每个节点执行完后，LangGraph 自动：
    1. 把更新后的 state 字段序列化（msgpack 二进制）
    2. 写入 PostgreSQL checkpoint_blobs
       每个 channel (字段) 单独一行

写入的字段（channel）：
  messages           → 所有历史消息（HumanMessage + AIMessage 的 Python 对象列表）
  summary            → LLM 生成的压缩摘要文本
  long_term_memories → 本轮 mem0 检索结果（每轮刷新）
  user_id            → 用户 ID 字符串
  rag_context        → 本轮 RAG 检索结果（每轮刷新）
  doc_context        → 用户上传文档文本
```

---

### SSE 结束后：异步写入 mem0

```
router.py 的 event_stream() finally 块：
    full_response = "".join(streamed_tokens)   # 拼接完整的 LLM 回答
    asyncio.create_task(
        add_memories_background(
            user_message    = "用户本轮问题",
            assistant_message = full_response,
            user_id         = "test_user_001"
        )
    )
    # create_task = 不阻塞 SSE 响应，后台异步执行

add_memories_background 内部：
    1. 构造对话对: [{"role":"user","content":"..."}, {"role":"assistant","content":"..."}]
    2. mem0.add(conversation, user_id=user_id)
       → mem0 内部调用 LLM 从对话中提取关键事实
         "用户叫小明" / "用户喜欢Python" / "项目叫ShillGuard"
       → 把提取的事实向量化（阿里百炼 embedding）
       → 写入 mem0 ChromaDB shillguard_mem0 集合
```

**此步骤的数据库操作：**

| 数据库 | 集合 | 操作 | 内容 |
|--------|------|------|------|
| **DeepSeek LLM API** | 远程 API | **调用** | 从对话中提取结构化记忆事实 |
| **阿里百炼 API** | 远程 API | **调用** | 把提取的记忆事实向量化 |
| **mem0 ChromaDB** (`./data/mem0_chroma`) | `shillguard_mem0` | **WRITE** | 写入记忆文本 + 1536 维向量 + user_id 元数据 |

---

## 四、完整数据流向总图

```
用户发送消息："你好，我叫小明"
│
│ POST /ai/chat  {message, thread_id="session_001", user_id="user_123"}
▼
┌─────────────────────────────────────────────────────────────┐
│  router.py                                                  │
│  解析文件 → doc_text                                         │
│  构造 inputs = {messages:[HumanMsg("你好，我叫小明")],       │
│                 doc_context="", user_id="user_123"}         │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│  LangGraph 恢复 State                                        │
│  READ ←── PostgreSQL checkpoints + checkpoint_blobs         │
│  (thread_id="session_001" 对应的历史 messages, summary 等)  │
│  add_messages：追加 HumanMsg("你好，我叫小明")               │
└──────────────────────────────┬──────────────────────────────┘
                               │
               ┌───────────────┼───────────────┐
               │               │               │
               ▼               ▼               ▼
    ┌──────────────────┐ ┌──────────────┐ ┌─────────────────┐
    │  memory_node     │ │  rag_node    │ │  chat_node      │
    │                  │ │  （顺序执行）│ │  （顺序执行）   │
    │ READ←mem0 Chroma │ │READ←Chroma  │ │ CALL←DeepSeek   │
    │ "小明叫什么名字" │ │ shillguard  │ │ 7条消息         │
    │ 向量检索记忆      │ │ _kg集合     │ │ (system+6条滑窗)│
    │                  │ │ 14178条向量 │ │                  │
    │ [条件]摘要压缩    │ │             │ │ 返回 AIMessage  │
    │ CALL←DeepSeek    │ │READ←ES      │ │                  │
    │ 生成200字摘要     │ │ BM25检索    │ │                  │
    │                  │ │             │ │                  │
    │ 写回 state:      │ │ CALL←硅基   │ │ 写回 state:     │
    │  summary         │ │ 流动rerank  │ │  messages追加   │
    │  long_term_mem   │ │             │ │  AIMessage      │
    └──────────────────┘ │ 写回 state: │ └─────────────────┘
                         │  rag_context│
                         └──────────────┘
                               │
                               ▼
    ┌─────────────────────────────────────────────────────┐
    │  LangGraph 自动 Checkpoint                           │
    │  WRITE ──→ PostgreSQL checkpoint_blobs              │
    │                                                     │
    │  channel=messages      │ 序列化所有消息（HumanMsg + │
    │                        │ AIMsg 对象，msgpack 二进制）│
    │  channel=summary       │ 摘要文本                   │
    │  channel=long_term_mem │ mem0 检索结果              │
    │  channel=rag_context   │ RAG 检索片段               │
    │  channel=user_id       │ "user_123"                 │
    │  channel=doc_context   │ 文档文本（若有）            │
    └─────────────────────────────────────────────────────┘
                               │
                               ▼
              SSE 流式推送 token 给前端
              data: {"delta": "你好"} × N次
              data: [DONE]
                               │
                               ▼
    ┌─────────────────────────────────────────────────────┐
    │  SSE 结束后（finally + asyncio.create_task）         │
    │  CALL←DeepSeek：从对话提取记忆事实                   │
    │    "用户叫小明"                                      │
    │  CALL←阿里百炼：把事实向量化 → 1536维向量            │
    │  WRITE ──→ mem0 ChromaDB shillguard_mem0            │
    │    document: "用户叫小明"                            │
    │    vector:   [0.02, -0.15, 0.33, ...] (1536维)      │
    │    metadata: {user_id: "user_123"}                  │
    └─────────────────────────────────────────────────────┘
```

---

## 五、各数据库真实表结构（基于 2026-07-12 实测）

### PostgreSQL (`shillguard` 库)

#### 表 `checkpoints`（5686 条）
| 列名 | 类型 | 说明 |
|------|------|------|
| `thread_id` | TEXT NOT NULL | 会话 ID（如 "session_001"） |
| `checkpoint_ns` | TEXT NOT NULL | 命名空间（通常为空字符串 ""） |
| `checkpoint_id` | TEXT NOT NULL | 本次 checkpoint UUID |
| `parent_checkpoint_id` | TEXT | 上一次 checkpoint UUID |
| `type` | TEXT | checkpoint 类型 |
| `checkpoint` | JSONB | 元数据：含 `channel_versions`（各字段版本号）、`ts`（时间戳）；**不含实际 state 值** |
| `metadata` | JSONB | LangGraph 内部元数据（source、step、writes 等） |

**示例行 `checkpoint` 字段内容：**
```json
{
  "v": 4,
  "id": "1f176992-9663-68e9-bfff-6d2b244a489f",
  "ts": "2026-07-03T04:39:22.182925+00:00",
  "versions_seen": {"__input__": {}},
  "channel_values": {},
  "channel_versions": {
    "__start__": "00000000000000000000000000000001.0.908..."
  },
  "updated_channels": ["__start__"]
}
```

#### 表 `checkpoint_blobs`（4329 条）
| 列名 | 类型 | 说明 |
|------|------|------|
| `thread_id` | TEXT NOT NULL | 对应 checkpoints.thread_id |
| `checkpoint_ns` | TEXT NOT NULL | 命名空间 |
| `channel` | TEXT NOT NULL | **State 字段名**（如 "messages"、"summary"、"user_id"） |
| `version` | TEXT NOT NULL | 该字段的版本号 |
| `type` | TEXT NOT NULL | 序列化格式（如 "msgpack"） |
| `blob` | BYTEA | **实际 State 值**，msgpack 二进制序列化。messages 字段里含所有 HumanMessage + AIMessage 对象 |

**每轮对话后 channel 列的取值：**
- `messages` - 所有历史消息的 Python 对象列表（含原文）
- `summary` - LLM 生成的摘要字符串
- `long_term_memories` - mem0 检索结果字符串
- `rag_context` - 本轮 RAG 检索片段
- `user_id` - 用户 ID 字符串
- `doc_context` - 上传文档文本
- `__start__`, `__end__` 等 LangGraph 内部控制 channel

#### 表 `checkpoint_writes`（9277 条）
| 列名 | 类型 | 说明 |
|------|------|------|
| `thread_id` | TEXT | 会话 ID |
| `checkpoint_id` | TEXT | 所属 checkpoint |
| `task_id` | TEXT | 节点任务 ID |
| `idx` | INT | 写入顺序 |
| `channel` | TEXT | 写入的 State 字段名 |
| `blob` | BYTEA | 节点输出的序列化值 |
| `task_path` | TEXT | 节点路径 |

> LangGraph 先把节点输出写入 `checkpoint_writes`，确认无误后合并到 `checkpoint_blobs`，保证原子性。

#### 表 `checkpoint_migrations`（10 条）
| 列名 | 类型 | 说明 |
|------|------|------|
| `v` | INT | 迁移版本号（0~9） |

> LangGraph 自动管理 schema 升级，无需手动干预。

---

### RAG ChromaDB (`./data/chroma`)

**集合：`shillguard_kg`（14178 条文档）**

| 字段 | 内容 | 说明 |
|------|------|------|
| `id` | `品牌核心规范_0` | 文件名 + chunk 序号组成 |
| `document` | `# 品牌核心规范 v2.0\n...` | chunk 原文（通常 300-500 字） |
| `embedding` | `[0.02, -0.15, ...]` | 1536 维浮点向量（阿里百炼 text-embedding-v3） |
| `metadata` | `{"source": "品牌核心规范.docx"}` | 来源文件名 |

**什么时候写入？** 离线一次性通过 `indexer.py` 把知识库文档切片 → 向量化 → 写入 ChromaDB。运行时只读不写。

---

### mem0 ChromaDB (`./data/mem0_chroma`)

**集合：`shillguard_mem0`**

| 字段 | 内容 | 说明 |
|------|------|------|
| `id` | UUID | mem0 自动生成 |
| `document` | `"用户叫小明"` | mem0 从对话中提取的结构化记忆事实 |
| `embedding` | `[0.03, -0.12, ...]` | 1536 维浮点向量（阿里百炼 text-embedding-v3） |
| `metadata` | `{"user_id": "user_123", "created_at": "..."}` | 用户 ID + 时间戳 |

**什么时候写入？** 每轮对话的 SSE 结束后，`add_memories_background` 异步写入。不阻塞响应。

---

### Elasticsearch

**索引：`shillguard_kg`（与 ChromaDB 同源文档）**

- 存储 chunk 原文 + BM25 词频统计
- 不存向量
- 用于关键词精确匹配，与向量检索形成互补

---

## 六、三层记忆触发时机详解

```
第 1 轮对话（全新会话）
  PostgreSQL: 无历史，从空 state 开始
  mem0: 无记忆，search 返回空
  summary: 无，跳过摘要
  chat_node: LLM 看 1(system) + 1(本轮问) = 2 条消息

第 2~10 轮对话
  PostgreSQL: 每轮追加 2 条消息（HumanMsg + AIMsg）
  mem0: 每轮结束后异步提取记忆
  summary: history.length < 10，不触发摘要
  chat_node: LLM 看 1(system) + min(历史, 6) 条消息

第 11 轮对话  ← 【摘要首次触发】
  history = [msg1~msg20]，length=20 > 10
  to_summarize = history[:-6] = msg1~msg14（14条旧消息）
  → 调 DeepSeek 生成摘要 "用户小明，Python工程师，..."
  summary 写入 PostgreSQL checkpoint_blobs channel=summary
  chat_node: LLM 看 system(含摘要) + 最近6条 = 7条消息
             摘要替代了旧的14条原文 → 节省大量 token

第 12 轮起
  每轮都会检查是否需要更新摘要（新 history 超过阈值则更新）
  mem0 已有记忆，search 返回用户历史偏好
  LLM 每轮看的消息数稳定在 7 条左右（不随对话增长而增长）
```

---

## 七、各 API 调用汇总

| 步骤 | API 提供商 | 模型/端点 | 用途 |
|------|-----------|----------|------|
| memory_node：mem0 检索 | 阿里百炼 | `text-embedding-v3` | query → 向量，用于 mem0 检索 |
| memory_node：摘要压缩（条件） | DeepSeek | `deepseek-v4-flash` | 旧消息 → 摘要文本 |
| rag_node：向量检索 | 阿里百炼 | `text-embedding-v3` | query → 向量，用于 ChromaDB 检索 |
| rag_node：BM25 检索 | Elasticsearch | - | query → 关键词搜索 |
| rag_node：精排 | 硅基流动 | `bge-reranker-v2-m3` | 候选 chunk 重排序 |
| chat_node：生成回答 | DeepSeek | `deepseek-v4-flash` | 主要 LLM 推理，流式输出 |
| tools（条件）：联网搜索 | Tavily | Search API | 实时搜索补充信息 |
| 后置：提取记忆 | DeepSeek | `deepseek-v4-flash` | 对话 → 结构化记忆事实 |
| 后置：记忆向量化 | 阿里百炼 | `text-embedding-v3` | 记忆文本 → 向量，存 mem0 |

---

## 八、常见误解纠正

| 误解 | 实际情况 |
|------|---------|
| "PostgreSQL 存了向量" | **错误**。PostgreSQL 只存 LangGraph State，即消息原文、摘要文本等，序列化为 msgpack 二进制（BYTEA 列）。向量只在 ChromaDB 中 |
| "PostgreSQL 存了 LLM 的向量输出" | **错误**。LLM 输出的是文本（AIMessage.content），以 Python 对象序列化后存在 `checkpoint_blobs.blob` |
| "摘要存在单独的表里" | **错误**。摘要文本存在 `checkpoint_blobs` 表中，`channel='summary'` 的行的 `blob` 字段里 |
| "mem0 用 PostgreSQL 存记忆" | **错误**。mem0 用 ChromaDB（`./data/mem0_chroma`），与 RAG 知识库的 ChromaDB 路径不同但格式相同 |
| "每次对话都发全量历史给 LLM" | **错误**。滑动窗口限制最多发 6 条给 LLM；全量历史保留在 PostgreSQL 和 summary 摘要中 |
