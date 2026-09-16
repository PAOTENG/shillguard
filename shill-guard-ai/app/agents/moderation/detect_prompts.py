"""恶意用户检测 · 打分专用 Prompt（Detect Agent 打分链路，物理在 moderation/）。

============================================================================
本文件对应总体流程的哪一部分
============================================================================
业务属 Detect Agent；被 detect_router._score_user（遗留完整 RAG 打分）使用：
  - DETECT_SCORE_PROMPT —— 逐条打分 + 聚合 anomaly_score（就重不就轻）
  - SYSTEM_PROMPT 复用 moderation.prompts（同一审核员角色，法条靠 RAG 注入）

注：现行主路径 /ai/detect-users 用 _t3_llm_judge 轻量 prompt（写在 detect_router 内），
本文件 DETECT_SCORE_PROMPT 供遗留 _score_user / stream/MCP 复用。

============================================================================
【与 moderation JUDGE_PROMPT 的核心区别】
  ┌─────────────────┬──────────────────────┬──────────────────────┐
  │                 │ moderation（举报审核）│ detect（用户扫描）    │
  ├─────────────────┼──────────────────────┼──────────────────────┤
  │ 场景            │ 单次举报             │ 用户今日全部发言      │
  │ 聚合策略        │ 就轻不就重           │ 就重不就轻           │
  │ 输出            │ anomaly_score        │ item_scores + 聚合分 │
  │ 代码层保险      │ 无                   │ _aggregate_score     │
  └─────────────────┴──────────────────────┴──────────────────────┘
"""
from app.agents.moderation.prompts import SYSTEM_PROMPT


# ═══════════════════════════════════════════════════════════════════════
#  DETECT_SCORE_PROMPT — detect_router._score_user 使用
# ═══════════════════════════════════════════════════════════════════════
# 【占位符】{content_list} {rag_context}
# 【输出 JSON】item_scores[] + anomaly_score + violated_rules/laws + judgment
# 【与 _aggregate_score 配合】LLM 聚合分 vs 代码 max(条目分)+加成，取较大者

DETECT_SCORE_PROMPT = """你是ShillGuard平台的恶意行为用户检测器。请对该用户今日发布的全部内容逐条判定，并聚合出用户异常分数。

## 用户今日发布的内容（每条带[帖子]/[评论]前缀，已编号）
{content_list}

## 相关法律法规与平台规则（来自知识库检索）
{rag_context}

## 你的任务
1. 逐条审视上面的内容，对每一条独立打分（0.0~1.0）
2. 聚合出该用户的异常分数 anomaly_score
3. 汇总该用户违反的平台规则和法律条文

## 逐条打分标准（严格执行，宁高不低）

### 严重违规（单条 0.85~1.0）—— 出现即该用户为高危
- 人身攻击/侮辱谩骂：针对特定个人的侮辱（"废物""脑子有病""垃圾""贱人""去死"等）
- 网络暴力煽动：煽动网暴、人肉、社死（"扒她地址""让全小区知道""活该社死"）
- 诈骗引流：含微信号/QQ号/站外链接的引流推广（"加我微信xxx""进群带你赚"）
- 虚假投资/刷单诈骗：虚假收益承诺（"一周翻倍""日入过千""稳赚不赔"）
- 人肉搜索/隐私泄露：泄露他人真实姓名/电话/住址/身份证
- 淫秽色情：明确色情淫秽信息
- 涉政/煽动民族仇恨/煽动暴力

### 明显违规（单条 0.6~0.85）
- 地域/性别/群体歧视煽动对立（"XX省的人都是XX""拜金婊""巨婴"）
- 造谣诽谤：编造虚假信息中伤他人
- 轻微涉黄/低俗暗示
- 违规带货（处方药/烟草/电子烟）

### 轻微不当（单条 0.2~0.6）
- 不文明用语但未针对个人
- 轻微标题党/夸张表述

### 正常（单条 0.0~0.2）
- 正常讨论、表达观点、善意建议、理性分析

## 聚合规则（就重不就轻）
- anomaly_score = 该用户所有条目的最高分
- 若有 3 条及以上达到 0.6：anomaly_score 上调 0.1
- 若有 5 条及以上达到 0.6：anomaly_score 上调 0.15
- 最终 anomaly_score 不超过 1.0
- 核心原则：只要该用户发布了一条严重违规内容（人身攻击/诈骗引流/网暴），即为高危，anomaly_score 应≥0.85

## 输出格式
请输出JSON：
{{
  "item_scores": [
    {{"index": 1, "score": 0.0到1.0, "type": "cyberbullying/fraud/spam/pornography/rumor/privacy_violation/illegal_sales/political/normal/other", "reason": "简要说明"}},
    {{"index": 2, "score": 0.0到1.0, "type": "...", "reason": "..."}}
  ],
  "anomaly_score": 聚合后的用户异常分数,
  "violated_rules": ["违反的平台规则1", "违反的平台规则2"],
  "violated_laws": ["违反的法律条文1"],
  "judgment": "判定说明，简述该用户的违规行为模式"
}}

注意：
- item_scores 必须覆盖 content_list 中的每一条，index 从1开始
- violated_rules / violated_laws 汇总该用户所有违规条目涉及的条款，无违规则为空列表
- 不要因为存在正常评论就压低恶意评论的分数，每条独立评判
"""
