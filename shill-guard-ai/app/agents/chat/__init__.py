"""对话问答 Agent（Chat Agent）—— 总体说明文档。

============================================================================
一、Agent 定位
============================================================================
ShillGuard 平台的通用对话 Agent，承担"用户 ↔ 平台"的多轮自然语言交互：
  - 通用知识问答（闲聊、常识、编程通识等）
  - 平台专属知识问答（平台规则、内容审核条款、相关法律法规）——通过 RAG 检索
  - 联网搜索（web_search 工具）
  - 用户上传文档（pdf/docx/txt）解读
  - 跨会话长期记忆（记住用户的姓名、职业、偏好等个人事实）

它对应 ShillGuard MCP 工具中的 `rag_search_laws`（法律/规则检索）能力，
也是 moderation / detect 之外面向终端用户的"前台 Agent"。

============================================================================
二、文件清单与职责
============================================================================
本 Agent 共 8 个源文件 + 本 __init__.py，分工如下：

  router.py            HTTP 入口（POST /ai/chat）+ SSE 流式输出 + 并发控制
  graph.py             LangGraph 状态机（5 节点图）+ PostgreSQL 持久化
  memory.py            三层记忆管理（滑动窗口 / LLM 摘要 / mem0 跨会话）
  prompts.py           Main LLM 的 system prompt 构建（架构隔离版）
  schemas.py           Worker LLM 结构化输出模型 WorkerContextResult
  history_store.py     双轨存储之 UI 历史表 chat_messages（append-only）
  history_router.py    历史读取接口（GET /ai/history、GET /ai/conversations）
  output_sanitizer.py  输出清洗工具（备用防御，防 bullet 复读）

============================================================================
三、总体流程（一次 /ai/chat 请求的完整链路）
============================================================================
流程编号 ① ~ ⑬，每一步标注所在文件 / 函数，以及"下一步"去向。

  ① HTTP 入口
     文件：router.py :: chat()
     做什么：接收 multipart/form-data（message + thread_id + user_id + files），
             并发计数 _CHAT_IN_FLIGHT 超阈值返回 429，解析上传文件→doc_context，
             构建 graph inputs，异步写入用户消息到 chat_messages 表，
             返回 StreamingResponse(event_stream)。
     下一步 → ② event_stream（SSE 生成器）

  ② SSE 流式生成
     文件：router.py :: event_stream()
     做什么：graph.astream_events(version="v2") 监听 on_chat_model_stream，
             只推 langgraph_node=="chat" 的 token（过滤 Worker LLM 的 JSON 输出），
             结束后 finally 块写助手回复到 chat_messages + 异步更新 mem0。
     下一步 → ③ 取到已编译的 graph 实例，触发图执行

  ③ 图构建与持久化
     文件：graph.py :: build_graph() / get_graph()
     做什么：构建 5 节点 StateGraph，挂载 AsyncPostgresSaver checkpointer，
             初始化 chat_messages 表（ensure_table），单例缓存编译后的图。
     下一步 → ④⑤（memory 与 rag 并行启动）

  ④ 节点1 记忆检索 + 摘要压缩
     文件：graph.py :: memory_node()
     做什么：并发执行两件事——
             (a) mem0 语义检索长期记忆 → long_term_memories（调 memory.py::search_memories）
             (b) 历史超阈值时把旧消息压缩为摘要 → summary，并用 RemoveMessage 删旧消息
                 （调 memory.py::summarize_old_messages）
     下一步 → ⑥ context_processor（与 ⑤ rag 同时进行，先到先等）

  ⑤ 节点2 Adaptive RAG 路由 + 检索
     文件：graph.py :: rag_node() + _should_retrieve()
     做什么：先用 Worker LLM 判断"是否需要查知识库"（yes/no），
             不需要→直接返回空 rag_context（跳过 embedding/BM25/rerank，省 2-4s）；
             需要→调 app/rag/retriever.py::retrieve() 混合检索
             （ES BM25 + pgvector 向量 + RRF 融合 + rerank 重排）→ rag_context。
     下一步 → ⑥ context_processor

  ⑥ 节点3 Context Processor（Worker LLM 提炼）
     文件：graph.py :: context_processor_node()
     做什么：读取 memories/summary/rag/user_said 全部原始背景，
             用 Worker LLM + prompt 内嵌 JSON 提炼为"单句 background_fact"，
             写入 processed_context（架构隔离：Main LLM 只看这一句，看不到原文）。
             无外部背景时跳过 Worker LLM 省 ~1.5s。
     下一步 → ⑦ chat_node

  ⑦ 节点4 Main LLM 推理
     文件：graph.py :: chat_node()
     做什么：build_system_prompt(processed_context, doc_context) 组装 system prompt，
             取最近 N 条滑动窗口消息并 _sanitize_window 清洗工具消息结构，
             llm.bind_tools([web_search]) 调用，信号量限流（_LLM_SEMAPHORE=2000）。
     下一步 → ⑧（若 LLM 输出 tool_calls 走 tools 节点）或 END（无 tool_calls）

  ⑧ 工具节点
     文件：graph.py :: tools（ToolNode([web_search])）
     做什么：执行 web_search 工具调用，返回 ToolMessage。
     下一步 → 回到 ⑦ chat_node 循环，直到无 tool_calls → END

  ⑨ 三层记忆之 Layer2/3（被 ④ 调用）
     文件：memory.py :: summarize_old_messages / search_memories / add_memories_background
     做什么：摘要压缩旧消息、检索 mem0、SSE 结束后异步写入 mem0（含 AMG 校验）。

  ⑩ Prompt 构建（被 ⑦ 调用）
     文件：prompts.py :: build_system_prompt()
     做什么：组装 SYSTEM_PROMPT + 北京时间 + processed_context + doc_context。

  ⑪ Worker 结构化输出（被 ⑥ 调用）
     文件：schemas.py :: WorkerContextResult
     做什么：Pydantic 模型 + field_validator 防御性清洗 + to_processed_context()。

  ⑫ 双轨存储 UI 历史表（被 ①②③ 调用）
     文件：history_store.py :: ensure_table / append_message / get_messages
     做什么：chat_messages 表的建表、append-only 写入、按 thread 读取。

  ⑬ 历史读取接口
     文件：history_router.py :: get_history / list_conversations
     做什么：GET /ai/history/{thread_id} 取单会话历史；
             GET /ai/conversations 取最近 N 个会话摘要（标题/最后消息/时间）。

============================================================================
四、核心优化与设计优点
============================================================================
1. memory / rag 并行执行
   两节点写不同 state 字段、互不依赖，LangGraph fan-in 让 context_processor
   等两者全完成。省时 ≈ max(mem0,rag) - min(mem0,rag)（约 600ms+）。

2. Adaptive RAG（查询路由 / 自适应检索）
   无关问题（闲聊/日期/数学/天气）在路由阶段直接返回空，跳过整条 RAG 链，
   省 ~2-4s。路由失败/超时保守降级为"执行检索"，不漏答知识库问题。
   扩展知识库领域只需改 _RAG_CORPUS_DESC 一个常量。

3. 架构隔离（Context Engineering - Isolate 策略）—— 防复读根本解法
   Worker LLM(context_processor) 消费原始背景，提炼单句 processed_context；
   Main LLM(chat_node) 物理上看不到 memories/summary/rag 原文，无法复读。
   用架构隔离替代事后 regex 清洗（output_sanitizer 仅作备用兜底）。

4. 三层记忆
   Layer1 滑动窗口（chat_node 取最近 N 条）+ Layer2 LLM 摘要（独立 summary 字段）
   + Layer3 mem0 跨会话（pgvector Hybrid Search）。符合 LangGraph 官方
   "summary key 与 messages 分离"最佳实践。

5. 双轨存储（工业标准）
   checkpointer(PostgresSaver) = LLM 工作记忆，可被摘要压缩；
   chat_messages 表 = UI 展示历史，append-only 永不删除。
   两者严格分离，UI 永远读 chat_messages，解决"摘要后 UI 历史断裂"反模式。

6. thinking 模型兼容
   Worker LLM 用 prompt 内嵌 JSON schema + 手动正则提取，不用
   with_structured_output / json_mode（DeepSeek-R1 等 thinking 模型两种都报 400）。
   RAG 路由用 yes/no 文本判断，兼容无 function_calling 的模型。

7. 全链路静默降级
   mem0 / AMG / 摘要 / RAG 路由 / Worker 提炼 任意环节失败都降级为空 / 保守检索，
   记忆与辅助流程失败不影响主对话可用性。

8. 并发与限流
   router 层 _CHAT_IN_FLIGHT 进程内计数 + chat_max_concurrent 防过载（超则 429）；
   chat_node 内 _LLM_SEMAPHORE(2000) 信号量限流 LLM 并发。

9. SSE 安全过滤
   只推 chat 节点的 on_chat_model_stream 事件，Worker LLM 的结构化 JSON
   不会泄漏给前端用户。

10. 工具消息结构清洗 _sanitize_window
    处理滑动窗口截断导致的孤立 ToolMessage / 不完整 tool_calls 组 / 悬空
    AIMessage(tool_calls)，防止 OpenAI 兼容 API 400 结构错误。
"""

# 对话 Agent 的对外路由对象由 app/main.py 直接从子模块导入挂载：
#   from app.agents.chat.router import router as chat_router        → POST /ai/chat
#   from app.agents.chat.history_router import router as history_router → 历史接口
# 本 __init__.py 仅作总体文档，不做 eager import，避免包级副作用与潜在循环导入。
