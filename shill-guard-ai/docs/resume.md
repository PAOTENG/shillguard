# 【姓名】

📱 1xx-xxxx-xxxx　｜　✉️ xxx@xxx.com　｜　🔗 github.com/【你的GitHub】　｜　📍 【城市】

**求职意向**：AI Agent 开发工程师 · 大模型应用工程师

---

## 技术栈

**Agent / LLM 工程**
LangGraph（StateGraph、并行节点、Human-in-the-Loop）｜LangChain（AgentExecutor、Tool Calling、Memory）
Prompt Engineering / Context Engineering｜多 Agent 协作（意图路由、子 Agent 编排）｜MCP 工具调用协议

**RAG / 向量检索**
混合检索（向量 + BM25 / Elasticsearch）｜Reranker 重排序
ChromaDB / pgvector / Elasticsearch（索引构建、混合检索）｜向量化存储（text-embedding-v3）

**后端工程**
Python（asyncio、Pydantic、FastAPI、SSE 流式输出）｜Java（Spring Boot、MyBatis、MySQL）
Redis（分布式缓存）｜PostgreSQL / pgvector｜Docker

---

## 项目经历

### 项目一：ShillGuard · UGC 内容治理 AI 助手（Python · LangGraph · RAG）

> 基于 LangGraph + RAG + mem0 的 UGC 社区内容治理 AI 助手，面向短视频平台内容审核与用户咨询场景，支持违规内容智能研判、国家法规与平台规则语义检索、多轮对话及实时流式输出。

**个人工作：**

- 设计 LangGraph 四节点 Agent 架构（memory + rag **并行** → context_processor → chat），实现 Worker LLM 上下文隔离策略（Isolate），消除多轮对话"回声污染"，跨会话用户信息准确回忆率从约 **40% 提升至 90%**，总请求延迟从约 7.2s 降至 **3.8s（↓47%）**

- 构建向量（ChromaDB）+ BM25（Elasticsearch）+ Reranker API 三阶段混合检索链，实现 **Adaptive RAG Query Routing**（LLM yes/no 路由判断），无关查询跳过全流程节省 **2~4s**，相关查询 Top-5 召回率提升约 **20%**

- 实现三层记忆架构：滑动窗口（最近 8 条）+ LLM 摘要压缩（HumanMessage 边界对齐）+ mem0 长期跨会话记忆；将 mem0 向量后端从 ChromaDB 迁移至 **pgvector**，消除 spaCy 依赖和 BM25 不支持警告

- 对全链路 6 个外部调用统一添加 `asyncio.wait_for` 超时保护，P99 等待时间从 **22s 降至 5s** 以内；禁用 PostHog / LangSmith 后台遥测，消除 3~5s 网络噪声

- 接入 **MCP Server** 四类工具（法规 RAG 检索、内容审核打分、恶意用户检测、禁言证据生成），实现内容治理全链路工具调用闭环

- 实现 FastAPI + **SSE 流式 token 推送**，前端实时渲染 Markdown + 代码高亮；构建**双轨存储**（PostgreSQL `chat_messages` + LangGraph checkpoint），解耦 UI 历史与 LLM 工作记忆，彻底解决页面刷新后历史消失问题

**项目难点：**

- **Thinking 模型兼容性**：DeepSeek-R1 等 thinking 模型不支持 `tool_choice` / `function_calling`（报 400 错误）。方案：移除 `with_structured_output`，改用 Prompt-based JSON Schema 注入 + 手动解析 + 降级兜底，结构化提炼成功率稳定在 **~95%**

- **LangGraph 工具消息原子性**：滑动窗口截断后 `AIMessage(tool_calls)` 与对应 `ToolMessage` 被分割，导致 `BadRequestError`。方案：重写 `_sanitize_window`，将工具调用消息组视为**原子单元**，仅当 `tool_call_id` 全部匹配时整组保留，彻底消除孤儿消息错误

---

### 项目二：【项目名称】（Python · 【技术栈关键词】）

> 【一句话项目描述：面向什么场景、解决什么核心问题、支持哪些核心功能】

**个人工作：**

- 【技术决策 + 量化结果，例如：设计了XX架构/实现了XX功能，将A指标从X提升至Y】
- 【技术决策 + 量化结果】
- 【技术决策 + 量化结果】
- 【技术决策 + 量化结果】

**项目难点：**

- **【难点名称】**：【遇到什么问题（根因）→ 用什么方案解决 → 效果是多少】
- **【难点名称】**：【遇到什么问题 → 解决方案 → 效果】

---

## 教育背景

**【院校名称】**　　｜　【专业】　｜　本科 / 硕士　｜　20xx 年 x 月 — 20xx 年 x 月

- 主修课程：数据结构、计算机网络、数据库原理、操作系统、算法设计
- GPA：xx / 4.0（如有排名可写：专业前 xx%）

---

## 其他信息

- **GitHub**：github.com/【你的ID】（含 ShillGuard 项目完整代码及架构文档）
- **技术博客**：【如有可填写】
- **奖项 / 证书**：【如有可填写，例如：国家奖学金 / 蓝桥杯 xx 奖 / 阿里云 ACP 认证】
