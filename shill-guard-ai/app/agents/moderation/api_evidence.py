"""T2-api 拦截后的模板证据报告（不调 LLM）。

============================================================================
本文件对应总体流程的哪一部分
============================================================================
对应 __init__.py 总体流程编号 ③（被 cascade.py::pre_filter_node 在 T2 API block 时调用）：
  - api_templated_evidence() —— 用 API 命中结果 + api_label_map 预设法条拼 Markdown 证据

调用关系：
  - cascade.py T2 API risk_score ≥ block 阈值时调用，写入 state["evidence_detail"]；
  - 后续 evidence_node 见已有 evidence_detail 会短路跳过 LLM。

============================================================================
本部分流程与思路
============================================================================
与 cascade._templated_evidence（T1 黑名单模板）并列：
  T1 模板：引用 BLACKLIST 预设法条
  T2 API 模板：引用 map_api_label 映射的 rules/laws + API 命中词/标签
两者都不调 LLM，法条预先人工核对，零幻觉。

【触发条件】
  cascade pre_filter 中 api_result.risk_score >= cascade_api_block_threshold
"""

# ── 项目内：API 统一返回结构 ──
from app.agents.moderation.api_moderation.base import ModerationApiResult


def api_templated_evidence(
    content_list: list[str],
    api_result: ModerationApiResult,
    cfg: dict,
) -> str:
    """生成商业 API 路径的 Markdown 证据报告。

    【功能/流程定位】
      对应总体流程 ③ 的 T2 API 分支。被 pre_filter_node 在 API block 时调用。
      本函数结束后 → pre_filter 返回 clear_violation（含 evidence_detail），
      路由直奔 evidence_node（会因已有证据而短路跳过 LLM）。

    【思路/代码流程】
      1. 编号拼 content_list；从 cfg 取 rules/laws 列表。
      2. 命中说明用 hit_keywords 前 5 个，缺省用 label 中文名或 primary_label。
      3. 拼五章节 Markdown（概述/内容/命中说明/违反条款/说明），末尾标"未调用大模型"。
      参数：
        content_list —— 被审核原文列表
        api_result   —— 商业 API 标准化返回
        cfg          —— map_api_label() 得到的 content_type/rules/laws
      返回：Markdown 字符串，直接写入 state["evidence_detail"]。
    """
    content_text = "\n".join(f"{i+1}. {c}" for i, c in enumerate(content_list))  # 编号原文
    rules = "\n".join(f"- {r}" for r in cfg["violated_rules"])                   # 平台规则
    laws_list = cfg.get("violated_laws") or []                                   # 法律列表
    laws = "\n".join(f"- {l}" for l in laws_list) if laws_list else "- （适用平台规则处置）"
    hits = "、".join(api_result.hit_keywords[:5]) or api_result.primary_label_name or api_result.primary_label  # 命中说明

    return (
        f"### 一、违规概述\n"
        f"内容经「{api_result.provider}」文本审核 API 检测，"
        f"风险分 {api_result.risk_score:.2f}，主标签 `{api_result.primary_label}`，"
        f"判定为明确违规（{cfg['content_type']}）。\n\n"
        f"### 二、违规内容\n{content_text}\n\n"
        f"### 三、命中说明\n"
        f"API 命中：{hits}\n"
        f"子标签：{', '.join(api_result.sub_labels) or '无'}\n\n"
        f"### 四、违反条款\n**平台规则：**\n{rules}\n\n**法律法规：**\n{laws}\n\n"
        f"### 五、说明\n"
        f"本报告由商业文本审核 API + 平台预设法条模板生成，未调用大模型；"
        f"灰区内容仍走 LLM 复核链路。\n"
        f"（API 延迟 {api_result.latency_ms:.0f}ms）"
    )
