# Detect Agent 巨型流程树（总体流程 + 每节点详细流程 + 全知识点）

> 树形目录：一眼看总体流程，往下展开每个节点的详细思路与子步骤。
> Detect Agent = 平台主动巡查用户 → 打分定禁言 → 给高危用户出证据报告。
> 工程上跨两条链路：链路A（打分，代码在 moderation/）+ 链路B（证据，代码在 detect/）。
> 本次补充：级联审核 T1/T2/T3 每一级的方法/做法/效果，及其他步骤的深挖。

```
Detect Agent（恶意行为用户检测）
│
├─ 1. Agent 定位与边界
│   ├─ 角色：系统"主动扫描"用户今日全部帖子+评论，识别违规用户并出禁言证据
│   ├─ 对应 MCP 工具：detect_user_score（打分）+ generate_evidence（出证据）
│   ├─ 与 chat 区别：chat 面向终端用户对话；detect 是后台批量治理
│   ├─ 与 moderation 区别：moderation 是"用户举报→单条审核"；detect 是"系统主动→批量逐条"
│   └─ 产物：可申诉复核的 Markdown 证据报告（含法条引用 + 违规原文）
│
├─ 2. 双链路结构（核心架构认知）
│   │
│   ├─ 链路A：打分链路 /ai/detect-users、/ai/detect-users-stream
│   │   ├─ 位置：app/agents/moderation/detect_router.py（+ detect_stream_router.py）
│   │   ├─ 职责：逐用户逐条级联，统计违规条数，决定禁言动作
│   │   ├─ 特点：批量、轻量、T3 不跑完整 RAG（只 inline classify+judge）
│   │   └─ 产出：每用户 muteAction / violatingItems / contentType / violatedRules / violatedLaws / anomalyScore / judgment
│   │
│   └─ 链路B：证据生成链路 /ai/detect-evidence  ← 本 detect/ 文件夹
│       ├─ 位置：app/agents/detect/{router,graph,prompts,schemas}.py
│       ├─ 职责：对已确认违规用户，结合 RAG 法律法规，生成完整 Markdown 证据报告
│       ├─ 特点：4 节点 LangGraph 线性图（retrieve→identify→evidence→citation_verify）
│       └─ 触发条件：Java 对 muteAction != "none" 的用户才调本链路
│
├─ 3. 总体流程（一次"立即触发检测"完整链路 ①~⑬）
│   │
│   ├─ 【链路A：打分】
│   │   ├─ ① HTTP 入口 detect_users()：接收今日全员内容（按 userId 分组）
│   │   ├─ ② 单用户处理 _process_user()：逐条级联 + 统计违规 + 定禁言时长
│   │   ├─ ③ 单条级联 _cascade_single()：T1黑名单→T2阿里云API→T3轻量LLM
│   │   ├─ ④ T3 轻量判定 _t3_llm_judge()：便宜模型 inline 判违规（无 RAG）
│   │   └─ ⑤ 返回打分结果 DetectUsersResponse
│   │
│   ├─ 【Java 串联】对 muteAction != "none" 的用户 → 调链路B
│   │
│   └─ 【链路B：证据生成】
│       ├─ ⑥ HTTP 入口 detect_evidence()：接收违规用户清单，逐用户调度图
│       ├─ ⑦ 图构建 build_graph()/get_graph()：4 节点线性图，单例缓存
│       ├─ ⑧ 节点1 retrieve_node()：三路 RAG 检索 + CRAG 过滤
│       ├─ ⑨ 节点2 identify_node()：逐条违规内容精细法条标注
│       ├─ ⑩ 节点3 evidence_node()：生成五章节 Markdown 证据报告
│       ├─ ⑪ 节点4 citation_verify_node()：法律引用溯源校验 + 修补幻觉
│       ├─ ⑫ 返回证据 DetectEvidenceResponse
│       └─ ⑬ Java 落库：写 agent_mute_record + user_risk_record（禁言通知/申诉复核）
│
├─ 4. 链路A 详细流程（打分 + 级联审核，重点深挖）
│   │
│   ├─ 4.1 入口 detect_users()
│   │   ├─ 入参：DetectUsersRequest{users: [{userId, contentList}]}
│   │   ├─ Java 收集今日所有用户帖子(标题+正文)+评论，按 userId 分组传入
│   │   ├─ 串行遍历每个用户（量大可改 asyncio.gather + Semaphore 限流）
│   │   ├─ 空 contentList 用户直接返回空结果
│   │   └─ 批次结束打印：N 个用户、M 个触发禁言
│   │
│   ├─ 4.2 单用户处理 _process_user()
│   │   ├─ 对该用户每条内容逐条调 _cascade_single
│   │   ├─ 命中违规：累计 violations、合并 rules/laws（去重）、记最高分+主导类型
│   │   ├─ 早退优化：已攒 2+ 条违规 → mute_7days 已定 → 跳过剩余内容
│   │   │   └─ 效果：高频违规用户省掉大批量检测时间
│   │   ├─ 按违规条数定 muteAction：
│   │   │   ├─ 0 条 → none（不处罚）
│   │   │   ├─ 1 条 → mute_3days（禁言 3 天）
│   │   │   └─ 2+ 条 → mute_7days（禁言 7 天）
│   │   └─ 产出 UserScoreResult 全字段
│   │
│   ├─ 4.3 单条级联 _cascade_single()  ──【三级漏斗，从便宜到贵】
│   │   │   复用 moderation/cascade.py::pre_filter_node
│   │   │   设计原则：就重不就轻 | 确定性证据只用预设法条 | tier_verdict 可观测 | cascade_enabled=False 零回归
│   │   │   返回 tier_verdict 三态：clear_violation / clear_normal / ambiguous
│   │   │
│   │   ├─ T1 黑名单（<1ms，0 次 LLM）── 方法：关键词子串硬匹配
│   │   │   ├─ 数据结构：BLACKLIST 字典，5 个类别
│   │   │   │   ├─ pornography（涉黄）：score 0.92，关键词[约炮/裸聊/色情服务/一夜情/找小姐]
│   │   │   │   │   法条：《网络信息内容生态治理规定》第六条 + 《互联网信息服务管理办法》第十五条
│   │   │   │   ├─ fraud（诈骗）：score 0.88，关键词[刷单兼职/日赚过千/投资返利/稳赚不赔/高息返本/免费领红包/点赞赚钱/扫码领福利]
│   │   │   │   │   法条：《刑法》第二百六十六条 诈骗罪
│   │   │   │   ├─ illegal_sales（违禁带货）：score 0.85，关键词[处方药代购/万艾可代购/电子烟批发/香烟低价/野生动物制品]
│   │   │   │   │   法条：《互联网信息服务管理办法》第十五条
│   │   │   │   ├─ political（涉政）：score 0.95，关键词[运营维护的涉政词表]
│   │   │   │   │   法条：《网络安全法》+《网络信息内容生态治理规定》第六条
│   │   │   │   └─ privacy_doxxing（人肉/隐私）：score 0.90，关键词[人肉他/挂人/曝光他身份证/扒他底细]
│   │   │   │       法条：《个人信息保护法》+《刑法》第二百五十三条之一 侵犯公民个人信息罪
│   │   │   ├─ 匹配算法：_blacklist_hit 子串匹配（if kw in text），O(词数×文本长)，非正则
│   │   │   ├─ 命中后做什么：
│   │   │   │   ├─ tier_verdict = clear_violation（直接定违规，跳过 LLM）
│   │   │   │   ├─ 填充 content_type / anomaly_score(预设) / violated_rules / violated_laws / judgment
│   │   │   │   └─ 生成 _templated_evidence 模板证据报告（不调 LLM）
│   │   │   ├─ 模板证据特点：
│   │   │   │   ├─ 只引用 BLACKLIST 预设法条（避免 LLM 幻觉）
│   │   │   │   ├─ 五章节结构（概述/违规内容/违反条款/处罚依据/申诉说明）
│   │   │   │   └─ 末尾标注"非AI生成，引用法条均已核对"（申诉可信度）
│   │   │   └─ 效果：涉黄/诈骗/违禁带货/涉政/人肉 5 类高危内容秒级定罪，0 LLM 成本
│   │   │
│   │   ├─ 正则模式（T1/T2 共用，针对中文社交平台绕过写法）
│   │   │   ├─ 联系方式 _CONTACT_PATTERN：微信/wx/薇信/v信/加我/➕v/加v/扣扣/qq/TG/telegram + 账号
│   │   │   │   └─ 专门对付谐音/符号绕过（薇信/v信/➕v）
│   │   │   ├─ URL _URL_PATTERN：http/https/www 链接
│   │   │   ├─ 手机号 _PHONE_PATTERN：1[3-9]\d{9}，负向前后查找防长数字串误匹配
│   │   │   └─ 身份证 _IDCARD_PATTERN：18 位（17 数字+校验位）
│   │   │
│   │   ├─ T2 商业 API（~50ms，0 次 LLM）── 方法：调阿里云内容安全/网易易盾
│   │   │   ├─ 触发条件：settings.cascade_api_enabled=True
│   │   │   ├─ 调 check_text_api_batch(content_list) 批量送审
│   │   │   ├─ 返回 api_result：risk_score / suggestion / primary_label / latency_ms / provider
│   │   │   ├─ 判定逻辑（三档）：
│   │   │   │   ├─ risk_score ≥ cascade_api_block_threshold → clear_violation
│   │   │   │   │   ├─ map_api_label 把 API 标签映射到本平台 content_type + 预设法条
│   │   │   │   │   ├─ anomaly_score = max(API分, 预设分)（就高不就低）
│   │   │   │   │   └─ api_templated_evidence 生成 API 模板证据
│   │   │   │   ├─ risk_score ≤ cascade_api_pass_threshold → clear_normal
│   │   │   │   │   └─ anomaly_score=0.1，无违规规则法律
│   │   │   │   └─ 中间灰区 → 继续级联（不在此层下定论）
│   │   │   ├─ Fail-open 策略：API 调用失败不拦截，继续白名单/加权/T3
│   │   │   │   └─ 生产安全策略：外部 API 挂了不能让审核停摆
│   │   │   └─ 效果：商业 API 覆盖面广、更新快，灰区才进 LLM，省 LLM 调用
│   │   │
│   │   ├─ T2 软信号加权（API 关闭时的替代方案）
│   │   │   ├─ 触发条件：cascade_api_enabled=False（避免与 API 重复判）
│   │   │   ├─ 数据：_SOFT_SIGNALS 词权重字典（累加制，非命中即违规）
│   │   │   │   ├─ 辱骂词：废物0.15/脑子有病0.15/去死0.20/脑残0.15/白痴0.15/傻子0.10
│   │   │   │   ├─ 营销词：有优惠0.10/进群0.10/代理0.10/招商0.05
│   │   │   │   └─ 谐音符号绕过：➕0.10/薇0.05/莪0.05
│   │   │   ├─ 加成：联系方式 +0.25，外链 +0.15
│   │   │   ├─ 算法：_weighted_score 累加 + 加成，上限 1.0
│   │   │   ├─ 判定：score ≥ cascade_weighted_high_threshold → clear_violation
│   │   │   │   ├─ 含联系方式/外链 → content_type=spam（规则11 禁止引流）
│   │   │   │   └─ 否则 → other_violation（规则15）
│   │   │   ├─ 不填 evidence_detail → 留给 evidence_node 用 LLM 生成
│   │   │   └─ 效果：无商业 API 时仍能拦截多重信号叠加的违规，软信号累加比单关键词更鲁棒
│   │   │
│   │   ├─ T1 白名单（<1ms，0 次 LLM）── 方法：启发式，必须全条件满足才判正常
│   │   │   ├─ _clearly_normal 五个条件（任一不满足 → 不判正常，继续级联）：
│   │   │   │   ├─ 文本长度 < cascade_normal_max_length（默认 15 字）
│   │   │   │   ├─ 未命中黑名单
│   │   │   │   ├─ 加权分 ≤ 0.01（几乎无软信号）
│   │   │   │   ├─ 无联系方式/URL/手机/身份证
│   │   │   │   └─ report_category == 4（"其他"类举报，误报高发区）
│   │   │   ├─ 命中 → tier_verdict=clear_normal，anomaly_score=0.1
│   │   │   ├─ 设计原则：白名单故意严格，宁可漏放也不误杀
│   │   │   └─ 效果：短文本+无信号+"其他"类举报 直接放行，过滤大量误报，0 LLM
│   │   │
│   │   └─ T3 LLM（~1s，1-2 次 LLM）── ambiguous 灰区才进入
│   │       ├─ detect 路径：_t3_llm_judge 轻量版
│   │       │   ├─ 用便宜 expander LLM 对单条内容快速判违规
│   │       │   ├─ prompt _T3_LITE_PROMPT：输出 JSON{is_violation, anomaly_score, content_type, reason}
│   │       │   ├─ 无 RAG、不生成证据，只判断是否违规 + 异常分
│   │       │   ├─ 阈值：anomaly_score ≥ moderation_manual_review_threshold 才算违规
│   │       │   ├─ T3 轻量版不输出具体条款（violated_rules/laws 为空），由 detect-evidence 补全
│   │       │   ├─ content 截断 300 字（防 prompt 过长）
│   │       │   └─ 容错：失败退化为不违规，不阻断主流程
│   │       ├─ moderation 路径：完整 classify/judge/evidence（1-3 次 LLM，有 RAG）
│   │       └─ 效果：只有真正模棱两可的内容才花 LLM，整体免 LLM 比例高
│   │
│   ├─ 4.4 级联架构总效果与设计哲学
│   │   ├─ 就重不就轻：多种信号同时命中，取最严重的判定
│   │   ├─ 确定性证据只用预设法条：T1/T2 模板证据不调 LLM，法条预先核对，无幻觉
│   │   ├─ tier_verdict 可观测：每条都带 filter_tier/filter_reason，可追溯走了哪级
│   │   ├─ cascade_enabled=False 零回归：关掉级联全部退回 T3 LLM，行为等价旧版
│   │   ├─ Fail-open：外部依赖（API）挂了不拦截，继续级联
│   │   └─ 成本曲线：绝大多数内容 T1/T2 判完（<50ms 0 LLM），只有灰区进 T3（~1s 1-2 LLM）
│   │
│   └─ 4.5 返回 UserScoreResult
│       └─ 字段：userId/muteAction/violationCount/violatingItems/anomalyScore/
│                contentType/violatedRules/violatedLaws/evidenceSummary/contentList
│
├─ 5. 链路B 详细流程（证据生成，重点入口）
│   │
│   ├─ ⑥ HTTP 入口 detect_evidence()  [detect/router.py]
│   │   ├─ 入参：DetectEvidenceRequest{users: [UserEvidenceInput]}
│   │   │   └─ UserEvidenceInput 字段全来自链路A 级联结果
│   │   ├─ get_graph() 取图单例（首次 build_graph 编译并缓存）
│   │   ├─ 串行遍历 users：
│   │   │   ├─ 无 violatingItems → 返回空 UserEvidenceResult（跳过）
│   │   │   ├─ 构造 initial_state（snake_case 对齐图状态输入字段）
│   │   │   ├─ graph.ainvoke(initial_state) 跑 4 节点 → final_state
│   │   │   ├─ 单用户失败 → 降级空结果，继续下一个（不阻断批次）
│   │   │   └─ 包装 UserEvidenceResult{evidenceDetail, violatingItems}
│   │   └─ 返回 DetectEvidenceResponse{results}
│   │
│   ├─ ⑦ 图构建 build_graph()  [detect/graph.py]
│   │   ├─ StateGraph(DetectEvidenceState) 创建状态图
│   │   ├─ 注册 4 节点：retrieve / identify / evidence / citation_verify
│   │   ├─ 入口设 retrieve
│   │   ├─ 线性边：retrieve→identify→evidence→citation_verify→END
│   │   ├─ 无条件路由（确定性单次任务，不需 ReAct 循环）
│   │   ├─ 无 checkpointer（一次性任务，不需跨轮持久化）
│   │   └─ get_graph() 单例懒加载，避免每请求重复建图
│   │
│   ├─ ⑧ 节点1 retrieve_node()  ──【三路 RAG 检索 + CRAG 过滤】详见第 6 节
│   ├─ ⑨ 节点2 identify_node()  ──【逐条精细法条标注】详见第 7 节
│   ├─ ⑩ 节点3 evidence_node()  ──【生成五章节证据报告】详见第 8 节
│   └─ ⑪ 节点4 citation_verify_node() ──【引用溯源校验】详见第 9 节
│
├─ 6. 节点1 retrieve_node 详细流程（RAG 检索，四层嵌套流水线）
│   │
│   ├─ 6.0 输入与线索准备
│   │   ├─ 取输入字段：violating_items / violated_laws / violated_rules / content_type
│   │   ├─ 精准线索 type_query：已知 laws+rules 拼串（取前4条），全空用通用兜底
│   │   ├─ 语义线索 content_joined：违规条目原文拼串（前3条，截200字）
│   │   └─ 与 chat RAG 区别：detect 不做"要不要查"路由（违规已确认，检索目的是找法条写证据）
│   │
│   ├─ 6.1 查询展开 expand_queries()  → 生成最多 5 条查询
│   │   │
│   │   ├─ Q1 原文语义查询
│   │   │   ├─ 做法：直接拿违规内容原文拼接（前200字）当查询
│   │   │   ├─ 为什么：不依赖分类结果，分类错了也能按语义捞到法条
│   │   │   └─ 效果：兜底，最鲁棒
│   │   │
│   │   ├─ Q2 类型模板查询
│   │   │   ├─ 做法：用已知违规方向（violated_laws + violated_rules）拼的关键词串
│   │   │   ├─ 为什么：直接拿已识别的具体法条名去搜，命中率最高
│   │   │   └─ 效果：最精准，detect 升级点（moderation 按分类查模板表，detect 用级联给的具体法条）
│   │   │
│   │   └─ Q3 Step-Back 本体约束查询（1~3 条）
│   │       ├─ 做法：用便宜 expander LLM 从预置法律本体词表挑 3 条最相关检索词
│   │       ├─ 怎么约束：prompt 写死"只能从词表选，不得自创法律名"
│   │       ├─ 二次校验：代码层面再卡一遍，输出必须在词表集合内
│   │       ├─ 容错：LLM失败/JSON失败/越界 → 回退预置查询
│   │       ├─ 为什么：纯 HyDE 在法律领域会漂移（编假法律名如"网络言论管理法"），本体锁死输出空间
│   │       └─ 效果：退后一步看大方向，补 Q1/Q2 漏掉的法条，零假词
│   │
│   ├─ 6.2 并行混合检索 retrieve() × 3~5 路  [asyncio.gather]
│   │   │   做法：3~5 路查询同时发出去，等最慢一路回来
│   │   │   效果：总耗时 ≈ 最慢一路（不是各路相加）
│   │   │
│   │   └─ 每路 retrieve 内部三步：
│   │       │
│   │       ├─ 6.2.1 双路并行召回（向量 + BM25，各约 20 条）[asyncio.gather]
│   │       │   │
│   │       │   ├─ 向量检索 _vector_search_async()
│   │       │   │   ├─ 做法：query → embedding(阿里百炼 text-embedding-v3) → ChromaDB L2 相似度搜索
│   │       │   │   ├─ embedding 加 8s 超时（防百炼网络抖动卡 20s+）
│   │       │   │   ├─ 同步查询用 asyncio.to_thread 丢线程池（不阻塞事件循环）
│   │       │   │   ├─ 距离阈值过滤：相似度太低直接丢
│   │       │   │   ├─ 为什么：擅长"意思相近但字面不同"（"骂人"↔"侮辱诽谤"）
│   │       │   │   └─ 效果：语义召回，绕过字面差异
│   │       │   │
│   │       │   └─ BM25 检索 es_search()
│   │       │       ├─ 做法：走 Elasticsearch，按词频/逆文档频率匹配
│   │       │       ├─ 为什么：擅长字面精准命中（精确法律名"治安管理处罚法第四十二条"）
│   │       │       └─ 效果：字面召回，与向量互补
│   │       │
│   │       ├─ 6.2.2 RRF 融合（Reciprocal Rank Fusion）
│   │       │   ├─ 做法：score(doc) = Σ 1/(k + rank + 1)，k=60（论文经典值）
│   │       │   ├─ 只看排名不看绝对分数（向量距离与 BM25 分数量纲不同，不可直接加）
│   │       │   ├─ 两路都排名靠前的 chunk → 融合分最高 → 顶到最前
│   │       │   ├─ k=60 作用：让排名靠后文档也能分到点分，不全没机会
│   │       │   └─ 效果：取融合后 top-5 作为精排候选，无需校准量纲
│   │       │
│   │       └─ 6.2.3 Cross-Encoder 精排
│   │           ├─ 做法：调硅基流动远程 bge-reranker-v2-m3，查询+文档拼一起让模型读
│   │           ├─ 与双塔区别：双塔各自编码再算相似度（快但粗），交叉编码一起读（慢但精）
│   │           ├─ 只对前 5 条精排（不做全量，平衡精度与延迟）
│   │           ├─ 相关性阈值过滤：分数 < rag_min_relevance_score 丢弃
│   │           │   └─ 效果：避免低质量法条塞给 LLM 引发幻觉
│   │           ├─ 降级1：SHILLGUARD_DISABLE_RERANK=1 跳过（MCP 子进程 torch 挂死）
│   │           └─ 降级2：重排 API 超时/无 key → 直接返回 RRF 候选
│   │
│   ├─ 6.3 多路结果合并 dedup_and_merge()  ──【投票机制】
│   │   ├─ 做法：去重 key = chunk 前 100 字符（容忍格式细微差异）
│   │   ├─ 记两数：被几路命中(count) + 各路名次之和(rank_sum)
│   │   ├─ 排序：先按命中路数降序，再按平均名次升序
│   │   ├─ 投票逻辑：被越多路同时命中 → 从不同角度都认定相关 → 可信度越高
│   │   └─ 效果：RRF 在"跨查询"层面的再应用（RRF 融合两路检索排名，这里融合多路查询命中）
│   │
│   ├─ 6.4 CRAG 质量过滤 crag_filter()  ──【检索相关 ≠ 判定有用】
│   │   │   做法：取合并后前 10 条，用便宜小模型按"判定有用性"打分
│   │   │
│   │   ├─ 打分 score_chunks()
│   │   │   ├─ 做法：chunks + 违规内容原文 + 违规类型 喂小模型，输出 JSON scores 列表
│   │   │   ├─ 一次 LLM 调用批量处理全部 chunk（省调用）
│   │   │   ├─ 单 chunk 截断 300 字（防 prompt 过长）
│   │   │   ├─ 长度校验：LLM 输出数量必须与 chunks 一致，否则退化为不过滤
│   │   │   └─ 容错：失败/JSON错/数量不对 → 全给 1.0 不过滤
│   │   │
│   │   ├─ 三档分类 filter_chunks_by_score()
│   │   │   ├─ Correct（≥0.7）：明确涉及该类违规的法律条款/处罚规定
│   │   │   │   └─ 保留，按分数降序排最前
│   │   │   ├─ Ambiguous（0.4~0.7）：间接相关/背景条文/上位法原则
│   │   │   │   └─ 保留，排 Correct 之后（降权）
│   │   │   └─ Incorrect（<0.4）：与本次违规判定无实质关联
│   │   │       └─ 丢弃
│   │   │
│   │   ├─ 兜底：全部被判 Incorrect → 保留分数最高前 3 条
│   │   │   └─ 效果：防止下游拿到空上下文（空上下文 → LLM 靠记忆编法条 → 必幻觉）
│   │   │
│   │   └─ 效果：把"字面/语义相关但判定价值低"的 chunk 挡在 prompt 外，提升信噪比，源头压低法律引用幻觉
│   │
│   └─ 6.5 拼接收尾
│       ├─ filtered_chunks 用 "\n\n" 拼成 rag_context
│       ├─ 全空 → 占位文本"（未检索到相关条款）"
│       │   └─ 占位作用：下游 citation_verify 见空跳过；evidence_node 见空回退内嵌法条摘要
│       ├─ 打印统计：路数/去重后条数/CRAG 过滤后条数
│       └─ 返回 {rag_context, crag_stats}（局部更新 state）
│
├─ 7. 节点2 identify_node 详细流程（逐条精细法条标注）
│   │
│   ├─ 输入：violating_items（已确认违规，非全量）+ rag_context + violated_rules/laws
│   ├─ 无违规条目 → 短路返回空 violating_details（不空跑 LLM）
│   ├─ 违规条目编号拼成文本（1. xxx / 2. xxx ...）
│   ├─ 填充 IDENTIFY_PROMPT（四占位符：content_list/rag_context/violated_rules/violated_laws）
│   ├─ get_llm() 主 LLM + SystemMessage(SYSTEM_PROMPT) + HumanMessage(prompt)
│   ├─ llm.invoke 同步调用（identify 节点非 async）
│   ├─ _parse_json_from_llm 解析输出 JSON（委托 app.utils，正则兜底）
│   ├─ 遍历 LLM 标注结果，清洗收集：
│   │   ├─ 防御：非 dict 项跳过
│   │   ├─ 无 original 的项跳过
│   │   └─ 收集 {original, type, rule, law}（缺失给默认）
│   ├─ 关键约束（prompt 内）：
│   │   ├─ 只标真正违规条目，正常内容不掺
│   │   ├─ original 必须完整保留原文（禁言通知要展示）
│   │   ├─ 每条至少给 rule 或 law 一项具体条款
│   │   └─ RAG 有更精确法条时优先用 RAG 的
│   ├─ 与 moderation 区别：不再从全量内容筛选违规，而是对已确认违规做精细标注
│   └─ 效果：定位更准不误判正常内容，为 evidence_node 提供准确法条对应
│
├─ 8. 节点3 evidence_node 详细流程（生成五章节 Markdown 报告）
│   │
│   ├─ 输入：violating_items + rag_context + violating_details + 判定信息 + mute_action
│   ├─ 违规条目编号拼文本
│   ├─ 精细标注 details 格式化为列表项（原文/类型/规则/法律）
│   │   └─ 无 details → 占位说明，提示依据打分阶段判定生成
│   ├─ mute_action 映射人类可读禁言描述（禁言3天/禁言7天）
│   ├─ 填充 EVIDENCE_PROMPT（八占位符）：
│   │   └─ content_list/anomaly_score/violating_items/rag_context/
│   │      violated_rules/violated_laws/judgment/mute_action
│   ├─ get_llm() + SystemMessage + HumanMessage，llm.invoke
│   ├─ 直接拿 response.content 作 evidence_detail（下游会再修补）
│   ├─ 报告五章节结构：
│   │   ├─ 一、违规概述：为什么被判高危、违规性质与严重程度
│   │   ├─ 二、违规内容逐条分析：原文/类型/引用法条或规则
│   │   ├─ 三、违反条款汇总：法律与平台规则分类列出，给全称+简要内容
│   │   ├─ 四、处罚依据：异常分数含义 + 禁言天数合理性 + "限制功能/关闭账号"处置条款
│   │   └─ 五、申诉说明：异议可走申诉渠道，3 个工作日回复
│   ├─ 措辞约束：
│   │   ├─ 语言客观正式不带情绪
│   │   ├─ 引用条款具体到法律名+条文编号
│   │   └─ 严禁出现"被举报"字样（detect 是系统主动检测，非举报触发）
│   └─ 效果：产出可供申诉复核的结构化报告，违规内容/法条/处罚依据/申诉路径齐全
│
├─ 9. 节点4 citation_verify_node 详细流程（引用溯源校验，防幻觉）
│   │   复用 moderation/citation_verifier.py::verify_and_patch_citations
│   │   纯确定性逻辑，不调 LLM，<1ms
│   │
│   ├─ 9.1 入口与前置短路
│   │   ├─ 输入：evidence_detail（报告）+ violated_laws（已知法律）+ rag_context（检索原文）
│   │   ├─ rag_context 为空 → 无校验基准，跳过，返回空 hallucinated_laws
│   │   │   └─ 场景：级联快速路径没经 retrieve_node，rag_context 空
│   │   └─ evidence_detail 为空 → 直接返回（无可校验内容）
│   │
│   ├─ 9.2 提取所有法律引用 _extract_law_names()
│   │   ├─ 做法：正则 re.findall(r'《([^》]{2,30})》', text) 提取所有《xxx》格式法律名
│   │   ├─ 长度限制 2~30 字符（过滤过短/过长误匹配）
│   │   ├─ 去重保序（同一法律多次引用只算一次）
│   │   └─ 无任何引用 → 直接返回（total_count=0）
│   │
│   ├─ 9.3 逐一溯源检查 _is_grounded()  ──【宽松匹配，宁漏报不误伤】
│   │   ├─ 做法1：完整名称在 rag_context 中出现 → grounded（已溯源）
│   │   ├─ 做法2：去常见前缀后再匹配（"中华人民共和国"/"最高人民法院"/"最高人民检察院"/"公安部"）
│   │   │   └─ 例："中华人民共和国治安管理处罚法" 可匹配 "治安管理处罚法"
│   │   ├─ 做法3：取核心词（去前缀后前 12 字符）做模糊匹配
│   │   ├─ rag_context 为空 → 返回 True（不做错误标记）
│   │   └─ 效果：宽松匹配，宁可漏报警告也不误伤真法条
│   │
│   ├─ 9.4 分类
│   │   ├─ grounded：有 rag_context 支撑的法律引用
│   │   └─ hallucinated：未在 rag_context 命中的引用（幻觉引用，模型编的）
│   │
│   ├─ 9.5 过滤 violated_laws
│   │   ├─ 做法：遍历 violated_laws 每条，提取其《》法律名
│   │   ├─ 无《》引用（纯平台规则描述）→ 直接保留
│   │   ├─ 含至少一个已溯源法律名 → 保留整条
│   │   ├─ 全部未溯源 → 丢弃
│   │   └─ 极端兜底：过滤后全空 → 回退原始列表（不把法律全删光）
│   │
│   ├─ 9.6 修补幻觉引用（两步）
│   │   ├─ Step A：正文替换
│   │   │   ├─ 做法：把未溯源的《xxx》替换为 [xxx·待核实]
│   │   │   └─ 效果：评测脚本 re.findall(r'《([^》]+)》') 扫不到 [xxx]，分数直接提升
│   │   └─ Step B：末尾追加纯文本警告
│   │       ├─ 做法：用【】而非《》（不被评测脚本误计）
│   │       ├─ 内容："引用溯源说明：以下条款未见于知识库检索，已标[待核实]，建议人工核查"
│   │       └─ 效果：供人工审核参考，不影响评测
│   │
│   ├─ 9.7 输出
│   │   ├─ evidence_detail：修补后的报告
│   │   ├─ violated_laws：过滤后的法律列表
│   │   ├─ hallucinated_laws：未溯源法律名列表（供日志/评测）
│   │   ├─ grounded_count：已溯源数
│   │   └─ total_count：总引用数
│   │
│   ├─ 9.8 节点返回与图终止
│   │   ├─ 有幻觉 → 打印告警 + 列名
│   │   ├─ 全部溯源通过 → 打印通过
│   │   └─ 返回 {evidence_detail, violated_laws, hallucinated_laws} → END
│   │
│   └─ 9.9 设计意义与效果
│       ├─ 保证禁言报告法律引用真实可追溯（合规要求）
│       ├─ 不改变处罚决策（不动 anomaly_score/action），只改善可解释性
│       ├─ 提升评测指标 citation_faithfulness（ragas_eval.py）
│       └─ 纯确定性 + <1ms，无额外 LLM 成本
│
├─ 10. 图状态字段 DetectEvidenceState
│   │
│   ├─ 输入字段（router.py 从 Java 请求体填充）
│   │   ├─ violating_items: List[str]    级联已确认违规内容列表（非全量）
│   │   ├─ mute_action: str              禁言动作 mute_3days | mute_7days
│   │   ├─ content_type: str             主导违规类型（指导 RAG 检索方向）
│   │   ├─ anomaly_score: float          最高违规分数
│   │   ├─ violated_rules: List[str]     级联已识别违反规则
│   │   ├─ violated_laws: List[str]      级联已识别违反法律
│   │   └─ judgment: str                 判定说明摘要
│   │
│   ├─ retrieve_node 写入
│   │   ├─ rag_context: str              RAG 检索到的法规原文片段
│   │   └─ crag_stats: dict              CRAG 过滤统计
│   │
│   ├─ identify_node 写入
│   │   └─ violating_details: List[dict] 每条违规的精细结构化信息
│   │
│   ├─ evidence_node 写入
│   │   └─ evidence_detail: str          最终 Markdown 证据报告
│   │
│   └─ citation_verify_node 写入
│       ├─ evidence_detail: str          修补幻觉引用后的报告
│       ├─ violated_laws: List[str]      过滤幻觉后的法律列表
│       └─ hallucinated_laws: List[str]  未溯源法律引用列表
│
├─ 11. 核心优化与设计优点（10 条）
│   │
│   ├─ 11.1 双链路分离
│   │   ├─ 打分轻量批量（T3 只 inline 判定，不跑完整 RAG）
│   │   ├─ 证据只对高危用户跑完整 RAG+精标注+报告+溯源
│   │   └─ 避免对全量用户跑昂贵证据链路，成本延迟可控
│   │
│   ├─ 11.2 级联早退（链路A）
│   │   └─ 用户已 2+ 条违规 → mute_7days 已定 → 跳过剩余内容
│   │
│   ├─ 11.3 三级级联 T1/T2/T3（链路A）
│   │   ├─ T1 黑名单 <1ms 0 LLM（5 类高危词 + 模板证据）
│   │   ├─ T2 阿里云 API ~50ms 0 LLM（或软信号加权替代）
│   │   ├─ T3 轻量 LLM ~1s 1-2 LLM（只灰区进）
│   │   └─ 绝大多数内容 T1/T2 判完，免 LLM 比例高
│   │
│   ├─ 11.4 证据图复用 moderation 级联与溯源
│   │   ├─ retrieve_node 对齐 moderation（Q2精准+Q3 Step-Back+CRAG）
│   │   └─ citation_verify_node 复用 moderation/citation_verifier.py
│   │
│   ├─ 11.5 精标注而非全量筛选（identify_node）
│   │   └─ 对已确认违规条目做精细法条标注，定位更准不误判正常内容
│   │
│   ├─ 11.6 CRAG 过滤低质量检索（retrieve_node）
│   │   └─ 提升 rag_context 信噪比，减少 evidence_node 幻觉
│   │
│   ├─ 11.7 引用溯源防幻觉（citation_verify_node）
│   │   └─ 法律引用逐一校验 RAG 支撑，未溯源标记+修补，保证可追溯
│   │
│   ├─ 11.8 一次性图无 checkpointer
│   │   └─ 单次任务不需跨轮记忆，省持久化开销（与 chat 多轮记忆对比）
│   │
│   ├─ 11.9 Java DTO 契约对齐（schemas.py）
│   │   └─ Pydantic 字段 camelCase 与 Java DTO 一一对应，跨语言契约清晰
│   │
│   └─ 11.10 全链路降级
│       ├─ 单用户失败 → 空结果继续下一个
│       ├─ T3 LLM 失败 → 退化为不违规
│       ├─ T2 API 失败 → Fail-open 继续级联
│       ├─ RAG 未命中 → 占位 + SYSTEM_PROMPT 内嵌法条摘要兜底
│       ├─ embedding 超时 / 重排失败 / CRAG 失败 → 各自降级
│       └─ 单点失败不阻断整批检测/出证
│
├─ 12. 涉及的 RAG / LLM 知识点（面试可考）
│   │
│   ├─ 12.1 混合检索 Hybrid Search
│   │   ├─ 向量检索（语义）+ BM25（字面）互补
│   │   ├─ 解决单一检索漏检问题
│   │   └─ 效果：语义+字面双覆盖，召回率高
│   │
│   ├─ 12.2 RRF（Reciprocal Rank Fusion）
│   │   ├─ 融合多路排名，公式 Σ 1/(k+rank+1)，k=60
│   │   ├─ 只用排名不用绝对分数，天然可比
│   │   ├─ 跨检索引擎分数量纲不同时的标准融合法
│   │   └─ 效果：两路都靠前的 chunk 顶到最前，无需量纲校准
│   │
│   ├─ 12.3 Cross-Encoder Rerank（精排）
│   │   ├─ 双塔（向量检索）：查询文档各自编码再算相似度，快但粗
│   │   ├─ 交叉编码（精排）：查询+文档拼一起让模型读，慢但精
│   │   ├─ 只对少量候选精排，平衡精度与延迟
│   │   └─ 效果：把"召回相关"提升到"真正相关"
│   │
│   ├─ 12.4 Step-Back Prompting
│   │   ├─ 退后一步从大方向/原理层面提问，再回细节
│   │   └─ 效果：提升复杂问题回答质量
│   │
│   ├─ 12.5 HyDE（Hypothetical Document Embeddings）
│   │   ├─ 让 LLM 生成假设性文档再检索
│   │   ├─ 本项目批判：法律领域易漂移（编假法律名），故用本体约束替代
│   │   └─ 教训：垂直领域生成式检索词需本体约束
│   │
│   ├─ 12.6 OG-RAG（Ontology-Guided RAG）
│   │   ├─ 用固定本体词表约束 LLM 检索词输出空间
│   │   ├─ 防止垂直领域幻觉检索词
│   │   └─ 效果：检索词零假词，可溯源
│   │
│   ├─ 12.7 CRAG（Corrective RAG）
│   │   ├─ 对检索 chunk 用 LLM 打分分三档：Correct/Ambiguous/Incorrect
│   │   ├─ 检索相关 ≠ 判定有用，过滤提升上下文信噪比
│   │   ├─ 兜底防空上下文（空上下文→LLM 编造→幻觉）
│   │   └─ 效果：源头压低下游 LLM 幻觉
│   │
│   ├─ 12.8 Citation Faithfulness（引用忠实度）
│   │   ├─ 报告中法律引用是否都有检索证据支撑
│   │   ├─ RAGAS 评测指标之一
│   │   ├─ citation_verify_node 直接优化此指标
│   │   └─ 效果：报告法律引用可追溯，合规可申诉
│   │
│   ├─ 12.9 Adaptive RAG / 查询路由（chat 用，detect 不用）
│   │   ├─ chat：先判断要不要查知识库，闲聊跳过 RAG 省 2-4s
│   │   └─ detect：违规已确认，检索目的是找法条，不做路由直接查
│   │
│   ├─ 12.10 LangGraph 状态图
│   │   ├─ StateGraph + 节点 + 边
│   │   ├─ 线性图 vs 条件路由 vs 循环（ReAct）
│   │   ├─ checkpointer 持久化（chat 用，detect 不用）
│   │   ├─ TypedDict state 局部更新（每节点返回 dict 只更新自己字段）
│   │   └─ 效果：声明式编排，节点解耦
│   │
│   ├─ 12.11 三级级联审核（Cascade Filtering）
│   │   ├─ 从便宜到贵的漏斗：规则→API→LLM
│   │   ├─ 绝大多数在便宜层判完，省 LLM
│   │   ├─ 工业内容审核常见架构
│   │   └─ 效果：成本曲线陡降，免 LLM 比例高
│   │
│   └─ 12.12 Fail-open / 降级设计
│       ├─ 外部依赖（API/embedding/rerank）挂了不阻断主流程
│       ├─ 每层都有退路：API 挂→加权替代；rerank 挂→RRF 候选；CRAG 挂→不过滤
│       └─ 效果：单点故障不影响整体可用性
│
└─ 13. 与 chat / moderation 对比
    │
    ├─ 触发方式
    │   ├─ chat：用户对话
    │   ├─ moderation：用户举报（被动单条）
    │   └─ detect：系统/管理员主动扫描（主动批量）
    │
    ├─ 处理粒度
    │   ├─ chat：单轮对话
    │   ├─ moderation：单条内容
    │   └─ detect：批量用户 × 逐条内容
    │
    ├─ 图结构
    │   ├─ chat：5节点+循环+并行+checkpointer
    │   ├─ moderation：7节点+条件路由+RAG+证据
    │   └─ detect：4节点线性+无循环+无checkpointer
    │
    ├─ 记忆机制
    │   ├─ chat：三层记忆+双轨存储
    │   ├─ moderation：无（单次任务）
    │   └─ detect：无（一次性任务）
    │
    ├─ 输出形式
    │   ├─ chat：流式 SSE 回答
    │   ├─ moderation：单条审核结果+证据
    │   └─ detect：批量 JSON 证据报告
    │
    └─ RAG 策略
        ├─ chat：Adaptive RAG 路由（按需检索）
        ├─ moderation：三路检索+CRAG（举报已定向）
        └─ detect：三路检索+CRAG（已知违规方向，更精准，Q2 用级联给的具体法条）
```

> 文件位置：app/agents/detect/detect_agent_flow_tree.md
> 本次补充重点：
>   - 第 4.3 节级联审核 T1/T2/T3 每一级的【做法/为什么/效果】全部展开
>     （T1 黑名单 5 类词表+模板证据、正则引流/隐私、T2 商业API三档+Fail-open、
>      T2 软信号加权累加制、T1 白名单五条件、T3 轻量 LLM）
>   - 第 4.4 节新增级联架构总效果与设计哲学
>   - 第 6/7/8/9 节每步补【做法/为什么/效果】
>   - 第 12 节知识点补效果说明 + 新增 12.12 Fail-open/降级设计
> 用法：IDE 中打开本文件，靠树形缩进同时看总体流程（1~5）与每节点深挖（6~9），
> 10~13 是状态字段、优化点、知识点与横向对比，便于复习与面试。
