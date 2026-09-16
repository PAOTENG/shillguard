# ShillGuard AI 架构说明

> 面向「读代码学 Agent 开发」的架构文档。与代码内注释互补。

## 1. 系统定位

```
Java Spring Cloud (shill-ai)  ──HTTP──▶  Python FastAPI (shill-guard-ai)
                                              │
                    ┌─────────────────────────┼─────────────────────────┐
                    ▼                         ▼                         ▼
              LangGraph Agents            RAG 子系统                  MCP Server
           (chat/writer/moderation)    (Chroma+ES+rerank)         (Cursor 工具)
```

Python 侧负责 **AI 推理**；业务落库、用户管理、定时任务在 Java 侧。

---

## 2. Agent 一览

| Agent | 路径 | 触发 | 图结构 | 记忆 |
|-------|------|------|--------|------|
| **moderation** | `app/agents/moderation/` | `POST /ai/moderate` | 7 节点 + 条件路由 | 无 |
| **detect 打分** | `detect_router.py` | `POST /ai/detect-users` | 无图，单函数 | 无 |
| **detect 证据** | `app/agents/detect/` | `POST /ai/detect-evidence` | 3 节点线性 | 无 |
| **chat** | `app/agents/chat/` | `POST /ai/chat` SSE | RAG→Chat→Tools 循环 | PostgreSQL |
| **writer** | `app/agents/writer/` | `POST /ai/write` SSE | 单节点 | 无 |
| **react** | `app/agents/react/` | `POST /ai/react` SSE | ReAct 循环 | 无 |

### 2.1 Moderation 审核图（核心）

```
pre_filter(级联)
  ├─ clear_violation → evidence → citation_verify → action → END
  ├─ clear_normal    → action → END
  └─ ambiguous       → classify → retrieve → judge → [score≥0.6] → evidence → ...
```

**级联 T1/T2 目标**：90%+ 请求不调 LLM，降低成本和延迟。

### 2.2 Chat 对话图

```
rag → chat ──有 tool_calls?──→ tools → chat (循环)
              └──无──→ END
```

`thread_id` + `AsyncPostgresSaver` 实现多轮记忆。

---

## 3. 共享基础设施

| 模块 | 文件 | 作用 |
|------|------|------|
| LLM 工厂 | `app/llm.py` | `get_llm()` / `get_expander_llm()`，OpenAI 兼容 API |
| 配置 | `app/config.py` | pydantic-settings 读 `.env` |
| RAG 检索 | `app/rag/retriever.py` | 向量(Chroma) + BM25(ES) + RRF + rerank |
| 查询扩展 | `app/rag/query_expander.py` | 三路并行 query（Q1/Q2/Q3） |
| 法律本体 | `app/rag/law_taxonomy.py` | Step-Back LLM 输出约束 |
| 引用溯源 | `citation_verifier.py` | 防 evidence 法条幻觉 |

---

## 4. RAG Pipeline

```
query
  ├─ Q1 原文语义
  ├─ Q2 类型模板 (_TYPE_QUERY_MAP)
  └─ Q3 Step-Back (law_taxonomy 约束)
       │
       ▼ 每路 retrieve()
  Chroma 向量(top-20) + Elasticsearch BM25(top-20)
       │
       ▼ RRF 融合
  top-5 候选
       │
       ▼ 硅基流动 bge-reranker API
  top-5 最终 → 注入 LLM prompt
```

**建索引**：`python -m app.rag.indexer`（双写 Chroma + ES）

---

## 5. MCP 工具（给 Cursor 用）

| Tool | 底层 |
|------|------|
| `rag_search_laws` | `retrieve()` |
| `moderate_content` | `moderation/graph.ainvoke()` |
| `detect_user_score` | `detect_router._score_user()` |
| `generate_evidence` | `detect/graph.ainvoke()` |

启动：MCP 配置指向 `app/mcp/server.py`

---

## 6. 评测体系

```
eval/run_eval.py          ← CI 总入口（fast / full）
├── Phase-1 无 LLM
│   ├── cascade_eval.py   ← 级联层准确率 + LLM 减少率
│   └── citation_check.py ← 法条引用幻觉检测
└── Phase-2 含 LLM
    ├── rag_eval.py       ← recall@k
    └── moderation_eval.py← 全链路 action 准确率

loadtest/ragas_eval.py    ← HTTP 全链路 + RAGAS 指标（需起服务）
loadtest/ci_gate.py       ← 读 ragas 报告做 CI 门控
```

**Golden Set**：`loadtest/golden_set.json`（110 条）+ `eval/golden_set.py`（分类用例）

---

## 7. 技术栈与版本

| 组件 | 版本 | 文档 |
|------|------|------|
| FastAPI | ≥0.115 | https://fastapi.tiangolo.com/ |
| LangGraph | ≥0.2.50 | https://langchain-ai.github.io/langgraph/ |
| LangChain | ≥0.3 | https://python.langchain.com/ |
| ChromaDB | ≥0.5 | https://docs.trychroma.com/ |
| Elasticsearch | 8.x + IK 分词 | 本地 BM25 |
| PostgreSQL | psycopg3 | LangGraph checkpoint |
| FastMCP | mcp.server.fastmcp | MCP 协议 |

**LLM 提供商**（OpenAI 兼容 `base_url`）：
- DeepSeek — 主 LLM（classify/judge/evidence）
- 阿里百炼 — Embedding（text-embedding-v3）
- 硅基流动 — Rerank API（bge-reranker-v2-m3）

---

## 8. 新建 Agent 标准步骤

```
1. schemas.py     — Pydantic 请求/响应（对齐 Java DTO）
2. prompts.py     — SYSTEM + 各节点 prompt
3. graph.py       — TypedDict State + 节点 + build_graph()
4. router.py      — FastAPI + ainvoke
5. main.py        — include_router
6. (可选) mcp/tools_xxx.py
```

**最小模板**：复制 `app/agents/writer/graph.py`

---

## 9. 关键配置项（.env）

```env
LLM_API_KEY / LLM_BASE_URL / LLM_MODEL
EMBED_API_KEY / EMBED_BASE_URL
CASCADE_ENABLED / CASCADE_API_ENABLED
PG_HOST / PG_PORT / PG_DBNAME
ES_URL
SILICONFLOW_API_KEY
```

---

## 10. 启动命令

```cmd
cd d:\Projects\shill-guard-ai
python -m uvicorn app.main:app --reload --port 8000
```

验证：`curl http://localhost:8000/health`
