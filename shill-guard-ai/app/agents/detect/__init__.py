"""恶意用户检测 Agent（Detect Agent）—— 总体说明文档。

============================================================================
一、Agent 定位
============================================================================
ShillGuard 平台的"恶意行为用户检测"Agent，负责平台**主动扫描**用户今日发布的
全部帖子与评论，识别违规用户并生成可用于禁言/申诉复核的结构化证据报告。

它对应 ShillGuard MCP 工具中的：
  - `detect_user_score`   —— 用户异常分打分（批量级联检测，决定禁言时长）
  - `generate_evidence`   —— 高危用户禁言证据生成（Markdown 报告 + 法条引用）

与 moderation / chat 的分工：
  - chat      ：面向终端用户的对话问答（前台）
  - moderation：用户举报 → 单条内容审核（被动、单条、有完整 7 节点图）
  - detect    ：系统主动扫描 → 批量逐条级联 → 按违规条数决定禁言 → 出证据报告（主动、批量）

============================================================================
二、双链路结构（Detect Agent 由两条链路组成）
============================================================================
Detect Agent 在工程上跨两个目录，分两条链路：

  ┌─ 链路A：打分链路（/ai/detect-users、/ai/detect-users-stream）────────────┐
  │  位置：app/agents/moderation/detect_router.py（+ detect_stream_router.py）│
  │  职责：对每个用户的每条内容逐条跑 T1/T2/T3 级联，统计违规条数，           │
  │        决定禁言动作（none / mute_3days / mute_7days）                      │
  │  特点：批量、轻量、无完整 RAG+证据（T3 只做 inline classify+judge）        │
  └──────────────────────────────────────────────────────────────────────────┘
                                  │ 对 muteAction != "none" 的用户
                                  ▼
  ┌─ 链路B：证据生成链路（/ai/detect-evidence）—— 本 detect/ 文件夹 ──────────┐
  │  位置：app/agents/detect/{router,graph,prompts,schemas}.py                │
  │  职责：对已确认违规的用户，结合 RAG 法律法规，生成完整 Markdown 证据报告    │
  │  特点：4 节点 LangGraph（retrieve→identify→evidence→citation_verify）     │
  └──────────────────────────────────────────────────────────────────────────┘

> 注：链路A 的代码物理上放在 moderation/ 下（复用了 moderation 的级联 pre_filter_node），
>    但业务上属于 detect agent。本 __init__ 同时描述两条链路，注释任务聚焦本 detect/ 文件夹。

============================================================================
三、文件清单与职责
============================================================================
本 detect/ 文件夹共 4 个源文件 + 本 __init__.py，分工如下（证据生成链路）：

  router.py     HTTP 入口（POST /ai/detect-evidence）+ 逐用户调度 graph.ainvoke
  graph.py      LangGraph 状态机（4 节点线性图：retrieve→identify→evidence→citation_verify）
  prompts.py    三个 prompt 模板（SYSTEM_PROMPT / IDENTIFY_PROMPT / EVIDENCE_PROMPT）
  schemas.py    Java DTO 对齐的 Pydantic 契约模型（请求/响应/单用户结果）

链路A（打分，在 moderation/ 下，仅在此说明，不在本文件夹注释）：
  moderation/detect_router.py       POST /ai/detect-users（批量级联打分）
  moderation/detect_stream_router.py POST /ai/detect-users-stream（SSE 流式打分）

============================================================================
四、总体流程（一次"立即触发检测"的完整链路）
============================================================================
流程编号 ① ~ ⑬，每步标注所在文件 / 函数，以及"下一步"去向。

  ── 链路A：打分（moderation/detect_router.py）──

  ① HTTP 入口（批量打分）
     文件：moderation/detect_router.py :: detect_users()
     做什么：接收 DetectUsersRequest（Java 收集的今日所有用户帖子+评论，按 userId 分组），
             串行逐用户调 _process_user。
     下一步 → ②（逐用户处理）

  ② 单用户处理
     文件：moderation/detect_router.py :: _process_user()
     做什么：对该用户每条内容逐条调 _cascade_single 级联，统计违规条数，
             合并 rules/laws，记录最高分+主导类型；已有 2+ 条违规即早退（mute_7days 已定）。
             按违规条数决定 muteAction：0→none / 1→mute_3days / 2+→mute_7days。
     下一步 → ③（逐条级联）

  ③ 单条内容级联
     文件：moderation/detect_router.py :: _cascade_single()
     做什么：对单条内容跑 T1黑名单→T2阿里云API→T3轻量LLM 级联（复用 moderation/cascade.py::pre_filter_node）。
             clear_violation→直接违规；clear_normal→正常；ambiguous→走 T3 轻量判定。
     下一步 → ④（T3 轻量判定，仅 ambiguous 时）

  ④ T3 轻量 LLM 判定
     文件：moderation/detect_router.py :: _t3_llm_judge()
     做什么：用便宜 expander LLM 对单条内容快速判违规（无 RAG，只 is_violation+anomaly_score+content_type），
             分数 ≥ moderation_manual_review_threshold 才算违规。失败退化为不违规。
     下一步 → 回 ② 继续下一条；全部完成 → ⑤

  ⑤ 打分链路返回
     文件：moderation/detect_router.py :: detect_users() 收尾
     做什么：返回 DetectUsersResponse（每用户 muteAction/violationCount/violatingItems/
             anomalyScore/contentType/violatedRules/violatedLaws/evidenceSummary）。
     下一步 → Java 侧：对 muteAction != "none" 的用户调链路B ⑥

  ── 链路B：证据生成（本 detect/ 文件夹）──

  ⑥ HTTP 入口（证据生成）
     文件：detect/router.py :: detect_evidence()
     做什么：接收 DetectEvidenceRequest（Java 传来的违规用户列表，字段来自 ⑤ 的级联结果），
             串行逐用户构造 initial_state，调 graph.ainvoke 跑证据图，汇总 UserEvidenceResult。
             无 violatingItems 的用户直接跳过；单用户失败降级为空结果。
     下一步 → ⑦（图构建/取单例）

  ⑦ 图构建
     文件：detect/graph.py :: build_graph() / get_graph()
     做什么：构建 4 节点线性 StateGraph（retrieve→identify→evidence→citation_verify→END），
             无条件路由、无 checkpointer（一次性任务），单例缓存编译后的图。
     下一步 → ⑧（graph.ainvoke 驱动，进入节点1）

  ⑧ 节点1 RAG 检索
     文件：detect/graph.py :: retrieve_node()
     做什么：用 contentType + violated_laws/violated_rules 构造 query，三路并行检索
             （expand_queries → retrieve → dedup_and_merge）+ CRAG 过滤低质量 chunk → rag_context。
     下一步 → ⑨（identify_node）

  ⑨ 节点2 逐条精细标注
     文件：detect/graph.py :: identify_node()
     做什么：对级联已确认的 violating_items（非全量内容），结合 rag_context 用 LLM 逐条
             精细标注（original/type/rule/law），供 evidence_node 准确引用。
     下一步 → ⑩（evidence_node）

  ⑩ 节点3 生成证据报告
     文件：detect/graph.py :: evidence_node()
     做什么：LLM 综合 violating_items + violating_details + rag_context + rules/laws + judgment +
             mute_action，生成结构化 Markdown 证据报告（五章节：概述/逐条分析/条款汇总/处罚依据/申诉说明）。
     下一步 → ⑪（citation_verify_node）

  ⑪ 节点4 引用溯源校验
     文件：detect/graph.py :: citation_verify_node()
     做什么：复用 moderation/citation_verifier.py::verify_and_patch_citations，
             校验 evidence_detail 里的法律引用是否有 rag_context 支撑，修补幻觉引用，
             输出 hallucinated_laws（未溯源列表）。
     下一步 → END（图结束）

  ⑫ 证据链路返回
     文件：detect/router.py :: detect_evidence() 收尾
     做什么：把 final_state 的 evidence_detail + violating_items 包装成 UserEvidenceResult，
             返回 DetectEvidenceResponse。
     下一步 → Java 侧落库

  ⑬ Java 侧落库（不在 Python 代码内，仅说明）
     Java 把 evidenceDetail + violatingItems 写进 agent_mute_record 与 user_risk_record，
     用于禁言通知与申诉复核。

============================================================================
五、核心优化与设计优点
============================================================================
1. 双链路分离：打分（轻量批量）与证据（重 RAG+LLM）拆开
   打分要对全平台用户逐条跑，必须轻量（T3 只 inline 判定，不跑完整 RAG）；
   证据只对已确认违规的高危用户生成，可以重（4 节点完整 RAG+精标注+报告+溯源）。
   避免对全量用户跑昂贵证据链路，成本与延迟可控。

2. 级联早退（链路A）
   某用户已累积 2+ 条违规 → mute_7days 已确定 → 直接跳过其剩余内容，省批量检测时间。

3. 三级级联 T1/T2/T3（链路A）
   T1 黑名单(<1ms,0 LLM) → T2 阿里云API(~50ms,0 LLM) → T3 轻量LLM(~1s,1-2 LLM)。
   绝大多数内容在 T1/T2 就判定完，只有灰区才进 T3，整体免 LLM 比例高。

4. 证据图复用 moderation 的级联与溯源
   - retrieve_node 与 moderation 对齐：Q2 精准 + Q3 Step-Back 本体扩展 + CRAG 过滤
   - citation_verify_node 直接复用 moderation/citation_verifier.py，防法律引用幻觉

5. 精标注而非全量筛选（identify_node）
   violating_items 已由级联 T1/T2/T3 确认违规，identify_node 不再从全量内容筛选，
   而是对已确认违规条目结合 RAG 做精细法条标注，定位更准、不误判正常内容。

6. CRAG 过滤低质量检索（retrieve_node）
   三路检索去重后用 crag_filter 评估 chunk 质量，过滤掉与违规内容不相关的 chunk，
   提升 rag_context 信噪比，减少 evidence_node 幻觉。

7. 引用溯源防幻觉（citation_verify_node）
   证据报告里的法律引用逐一校验是否有 RAG 上下文支撑，未溯源的标记为 hallucinated_laws，
   并修补，保证禁言报告法律引用可追溯（合规要求）。

8. 一次性图、无 checkpointer
   证据生成是单次任务（不需要跨轮记忆），不挂 checkpointer，省持久化开销，
   与 chat agent（多轮、需 checkpointer）形成对比。

9. Java DTO 契约对齐（schemas.py）
   Pydantic 字段名 camelCase 与 Java DTO 一一对应（userId/muteAction/violatingItems...），
   跨语言接口契约清晰，Java 侧直接序列化落库。

10. 全链路降级
    单用户失败 → 降级为空结果继续下一个；T3 LLM 失败 → 退化为不违规；
    RAG 未命中 → "（未检索到相关条款）"占位 + SYSTEM_PROMPT 内嵌法条摘要兜底。
    单点失败不阻断整批检测/出证。

============================================================================
六、与 chat agent 的对比（帮助理解差异）
============================================================================
| 维度 | chat agent | detect agent |
|------|-----------|--------------|
| 触发 | 用户对话 | 系统/管理员主动扫描 |
| 粒度 | 单轮对话 | 批量用户 × 逐条内容 |
| 图   | 5节点+循环+并行+checkpointer | 4节点线性+无循环+无checkpointer |
| 记忆 | 三层记忆+双轨存储 | 无（一次性任务） |
| 输出 | 流式 SSE 回答 | 批量 JSON 证据报告 |
| RAG  | Adaptive RAG 路由 | 三路检索+CRAG（已知违规方向，更精准） |
"""

# Detect Agent 对外路由由 app/main.py 直接从子模块导入挂载：
#   from app.agents.detect.router import router as detect_evidence_router  → POST /ai/detect-evidence
# 打分链路路由在 moderation/ 下：
#   from app.agents.moderation.detect_router import router as detect_users_router → POST /ai/detect-users
#   from app.agents.moderation.detect_stream_router import router as detect_stream_router → SSE 流式打分
# 本 __init__.py 仅作总体文档，不做 eager import，避免包级副作用与潜在循环导入。
