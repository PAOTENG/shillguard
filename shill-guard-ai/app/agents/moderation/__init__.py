"""合规审核 Agent（Moderation Agent）—— 总体说明文档。

============================================================================
一、Agent 定位
============================================================================
ShillGuard 平台的"用户举报内容审核"Agent，负责对用户举报的帖子/评论做内容审核：
判定是否违规、给出违规类型与异常分、生成可申诉复核的封号证据报告、决定处罚动作。

它对应 ShillGuard MCP 工具中的 `moderate_content`（内容审核）能力。

与 chat / detect 的分工：
  - chat      ：面向终端用户的对话问答（前台）
  - moderation：用户举报 → 单条/单批内容审核 → 出证据 + 处罚动作（被动、单次、有完整图）
  - detect    ：系统主动扫描 → 批量逐条级联 → 按违规条数定禁言 → 出证据（主动、批量）

============================================================================
二、核心架构认知
============================================================================
moderation 是三条链路共存的 agent：

  ┌─ 链路1：举报审核（POST /ai/moderate，异步任务）── 本 agent 主体 ────────┐
  │  8 节点 LangGraph：pre_filter → classify → retrieve → crag_filter →     │
  │                     judge → evidence → citation_verify → action → END  │
  │  含 T1/T2 级联前置过滤（目标 90%+ 免 LLM）+ T3 完整 LLM 管线 + 短路优化   │
  └────────────────────────────────────────────────────────────────────────┘

  ┌─ 链路2：批量打分（POST /ai/detect-users）── 业务属 detect，物理在本目录 ─┐
  │  detect_router.py：逐用户逐条级联 T1/T2/T3，按违规条数定禁言动作         │
  │  注：这条链路属于 detect agent（见 app/agents/detect/__init__.py），     │
  │      因复用 moderation 的级联 pre_filter_node 而放在本目录。            │
  └────────────────────────────────────────────────────────────────────────┘

  ┌─ 链路3：流式打分（POST /ai/detect-users-stream）── 链路2 的 SSE 版 ──────┐
  │  detect_stream_router.py：复用 _process_user，SSE 实时推送日志+分数       │
  └────────────────────────────────────────────────────────────────────────┘

============================================================================
三、文件清单与职责
============================================================================
本 moderation/ 目录共 12 个源文件 + api_moderation/ 子包 4 文件 + 本 __init__.py：

  举报审核链路（链路1，主体）：
    graph.py            LangGraph 8 节点状态机 + 条件路由 + 短路优化
    router.py           FastAPI 异步任务接口（POST /ai/moderate + GET 轮询）
    prompts.py          4 个 prompt 模板（SYSTEM/CLASSIFY/JUDGE/EVIDENCE）+ 举报分类映射
    schemas.py          Java DTO 对齐的 Pydantic 契约模型
    cascade.py          T1/T2 级联前置过滤（pre_filter_node，黑名单/白名单/API/加权）
    citation_verifier.py 法律引用溯源校验（citation_verify_node，防幻觉）
    api_evidence.py     T2 API 命中后的模板证据报告（不调 LLM）
    api_label_map.py    厂商 label → 内部违规类型/法条 映射
    api_moderation/     商业文本审核 API 子包（Adapter 模式）
      __init__.py         工厂 + 批量聚合（check_text_api / check_text_api_batch）
      base.py             统一返回结构 ModerationApiResult（dataclass）
      aliyun.py           阿里云内容安全客户端（主力）
      yidun.py            网易易盾客户端（保留供回滚）

  批量打分链路（链路2/3，业务属 detect，物理在本目录）：
    detect_router.py        POST /ai/detect-users 批量级联打分
    detect_stream_router.py POST /ai/detect-users-stream SSE 流式打分
    detect_prompts.py       打分专用 prompt（DETECT_SCORE_PROMPT）

============================================================================
四、总体流程（一次 /ai/moderate 举报审核的完整链路）
============================================================================
流程编号 ① ~ ⑬，每步标注所在文件 / 函数，以及"下一步"去向。

  ① HTTP 提交（异步任务）
     文件：router.py :: moderate()
     做什么：接收 ModerateRequest（举报ID/被举报用户/内容列表/举报分类），
             生成 taskId，注册 BackgroundTasks，立即返回 taskId（不阻塞）。
     下一步 → ②（后台跑图）

  ② 后台执行审核图
     文件：router.py :: _run_moderate_task()
     做什么：构造 initial_state（content_list + report_category），
             graph.ainvoke 驱动 8 节点图，跑完写指标 JSONL，包装 ModerateResult。
     下一步 → ③（图入口 pre_filter）

  ③ 节点1 级联前置过滤
     文件：cascade.py :: pre_filter_node()
     做什么：T1 黑名单关键词命中→clear_violation（含模板证据）；
             T2 商业 API/软加权判定→clear_violation/clear_normal/灰区；
             T1 白名单启发式→clear_normal；
             都没下定论→ambiguous 退回 T3 LLM。
     下一步 → ④（条件路由 route_after_pre_filter）

  ④ 条件路由 route_after_pre_filter
     文件：graph.py :: route_after_pre_filter()
     做什么：clear_violation→跳 classify/retrieve/judge 直奔 evidence；
             clear_normal→跳全部 LLM 直奔 action；ambiguous→走 classify。
     下一步 → ⑤ 或 ⑨ 或 ⑫

  ⑤ 节点2 内容分类（T3 LLM 第一跳）
     文件：graph.py :: classify_node()
     做什么：LLM 判内容属于 13 种 type 哪种（normal/spam/fraud/...），输出 type+reason。
     下一步 → ⑥（条件路由 route_after_classify）

  ⑥ 条件路由 route_after_classify
     文件：graph.py :: route_after_classify()
     做什么：normal→跳 retrieve/judge 直奔 action；违规类型→走 retrieve。
     下一步 → ⑦ 或 ⑫

  ⑦ 节点3 三路 RAG 检索
     文件：graph.py :: retrieve_node()
     做什么：Q1 原文语义 + Q2 类型模板 + Q3 Step-Back 本体约束，三路并行混合检索
             （向量+BM25+RRF+rerank），dedup_and_merge 投票合并，存原始 chunk。
     下一步 → ⑧（CRAG 过滤）

  ⑧ 节点4 CRAG 质量过滤
     文件：graph.py :: crag_filter_node()
     做什么：对检索 chunk 用小模型打分三档（Correct/Ambiguous/Incorrect），
             丢低质量、保留高相关，更新 rag_context。
     下一步 → ⑨（judge）

  ⑨ 节点5 违规判定（T3 LLM 第二跳）
     文件：graph.py :: judge_node()
     做什么：LLM 结合内容+rag_context+分类，输出 anomaly_score + violated_rules/laws + judgment。
     下一步 → ⑩（条件路由 route_after_judge）

  ⑩ 条件路由 route_after_judge
     文件：graph.py :: route_after_judge()
     做什么：score ≥ 0.6→生成证据；score < 0.6→跳证据直奔 action。
     下一步 → ⑪ 或 ⑫

  ⑪ 节点6 证据生成（T3 LLM 第三跳，或级联已预填则跳过）
     文件：graph.py :: evidence_node()
     做什么：若级联 T1/T2 已写 evidence_detail→短路返回 {} 跳过 LLM；
             否则 LLM 生成五章节 Markdown 证据报告（含反幻觉引用约束）。
     下一步 → ⑫（citation_verify）

  ⑫ 节点7 引用溯源校验
     文件：citation_verifier.py :: citation_verify_node()
     做什么：校验 evidence_detail 里《xxx》法律引用是否在 rag_context 有支撑，
             修补幻觉引用（正文替换为[待核实]+末尾警告），输出 hallucinated_laws。
     下一步 → ⑬（action）

  ⑬ 节点8 处罚决策
     文件：graph.py :: action_node()
     做什么：按 anomaly_score 三档定 action：≥0.8→auto_mute；≥0.6→manual_review；其余→none。
     下一步 → END（图结束，router 包装结果返回）

  轮询取结果
     文件：router.py :: moderate_result()
     做什么：Java 每 2s 轮询 GET /ai/moderate/result/{taskId}，status=done/error 后停止。

============================================================================
五、核心优化与设计优点
============================================================================
1. T1/T2 级联前置过滤（目标 90%+ 免 LLM）
   T1 黑名单关键词 <1ms 0 LLM；T2 商业 API ~50ms 0 LLM；只有灰区进 T3 LLM。
   绝大多数明确违规/正常内容在 T1/T2 判完，整体免 LLM 比例高，成本与延迟陡降。

2. 四级短路优化（条件路由）
   - pre_filter clear_violation → 跳 classify/retrieve/judge 直奔 evidence
   - pre_filter clear_normal → 跳全部 LLM 直奔 action
   - classify normal → 跳 retrieve/judge 直奔 action
   - judge score < 0.6 → 跳 evidence 直奔 action
   每一级都能提前结束，避免无谓 LLM 调用。

3. 三路并行 RAG（Q1 原文 + Q2 类型模板 + Q3 Step-Back 本体约束）
   Q1 绕开分类错误保底、Q2 精准、Q3 本体约束防 HyDE 漂移；dedup_and_merge 投票合并。
   与 detect 同源，但 moderation 的 Q2 用 _TYPE_QUERY_MAP 模板表（detect 用级联给的具体法条）。

4. CRAG 检索质量过滤（借鉴 CRAG 评估器，无网络搜索退化）
   小模型三档打分过滤低质量 chunk，提升 rag_context 信噪比，源头压低 evidence 幻觉。
   注：仅用 CRAG 的"评估打分过滤"思想，未实现原版 CRAG 的"网络搜索退化"。

5. 引用溯源防幻觉（citation_verify_node）
   证据报告里《xxx》法律引用逐一校验 rag_context 支撑，幻觉引用修补为[待核实]+警告。
   与 EVIDENCE_PROMPT 的反幻觉约束双保险，保证法条可溯源（合规可申诉）。

6. 确定性模板证据（T1/T2 命中不调 LLM）
   T1 黑名单命中用 BLACKLIST 预设法条出模板证据；T2 API 命中用 api_label_map 映射法条出模板证据。
   法条预先人工核对，零幻觉，末尾标"非AI生成"提升申诉可信度。

7. 商业 API Adapter 模式（api_moderation 子包）
   cascade 只依赖 ModerationApiResult，不关心底层是阿里云/易盾/百度。
   新增厂商只需实现 check_text_xxx() 返回 ModerationApiResult。批量调用就重不就轻（取最高分）。

8. 异步任务模式（BackgroundTasks + 轮询）
   审核含 1~3 次 LLM 调用（1~3s+），POST 立即返回 taskId，后台跑图，Java 轮询取结果，
   避免 HTTP 长连接阻塞，适配 Java 调用方。

9. 就轻不就重（与 detect 相反）
   moderation 是单次举报审核，边缘内容倾向较低 score，避免误判误封；
   detect 是主动扫描高危用户，就重不就轻，宁抓不漏。两套策略因场景而异。

10. 全链路降级 + fail-open
    T2 API 失败→fail-open 继续级联；级联关闭→全部退回 T3 LLM（零回归）；
    RAG/CRAG/rerank 失败各自降级；单用户失败不影响其他。外部依赖抖动不阻断审核。

11. 级联指标可观测
    router 把每次请求的 tier_verdict/filter_tier/score/action 写 JSONL，
    供离线聚合统计免 LLM 比例、各层命中率，量化级联效果。

============================================================================
六、与 chat / detect 对比
============================================================================
| 维度 | chat | moderation | detect |
|------|------|-----------|--------|
| 触发 | 用户对话 | 用户举报（被动单次） | 系统/管理员主动扫描（批量） |
| 粒度 | 单轮对话 | 单次举报内容（可多条） | 批量用户 × 逐条内容 |
| 图 | 5节点+循环+并行+checkpointer | 8节点+条件路由+短路+无checkpointer | 4节点线性+无循环+无checkpointer |
| 记忆 | 三层记忆+双轨存储 | 无（一次性任务） | 无（一次性任务） |
| 输出 | 流式 SSE 回答 | 异步任务+轮询 JSON 结果 | 批量 JSON 结果 |
| RAG | Adaptive RAG 路由 | 三路检索+CRAG（Q2 模板表） | 三路检索+CRAG（Q2 用级联具体法条） |
| 级联 | 无 | T1/T2 级联前置（本 agent 核心） | 复用 moderation 级联 |
| 策略 | — | 就轻不就重 | 就重不就轻 |
| 证据 | — | 五章节报告+引用溯源 | 五章节报告+引用溯源（复用） |

============================================================================
七、对外路由挂载（由 app/main.py 直接导入）
============================================================================
  from app.agents.moderation.router import router as moderation_router → POST /ai/moderate + GET 轮询
  from app.agents.moderation.detect_router import router as detect_users_router → POST /ai/detect-users
  from app.agents.moderation.detect_stream_router import router as detect_stream_router → SSE 流式打分
本 __init__.py 仅作总体文档，不做 eager import，避免包级副作用与潜在循环导入。
"""

# 本 __init__.py 仅作总体文档，不做 eager import，避免包级副作用与潜在循环导入。
