"""审核级联前置过滤（Moderation Agent 举报审核链路的节点1）。

============================================================================
本文件对应总体流程的哪一部分
============================================================================
对应 __init__.py 总体流程编号 ③：
  ③ pre_filter_node() —— 节点1：T1/T2 级联前置过滤，输出 tier_verdict 三态
  辅助：_blacklist_hit / _weighted_score / _clearly_normal / _templated_evidence

调用关系（谁来调用本文件）：
  - graph.py 把 pre_filter_node 注册为入口节点；
  - detect_router.py::_cascade_single 也复用本节点做批量打分级联。
执行后：route_after_pre_filter 按 tier_verdict 分流到 evidence / action / classify。

============================================================================
本部分流程与思路
============================================================================
在 LLM 分类前用确定性规则/商业 API 清掉明确违规与明确正常，目标 90%+ 免 LLM：

  T1 黑名单 (<1ms, 0 LLM) → clear_violation + 模板证据
  T2 商业 API (~50ms, 0 LLM) → clear_violation / clear_normal / 灰区继续
  T2 软信号加权（API 关闭时）→ clear_violation（无模板证据，留给 evidence_node）
  T1 白名单 (<1ms, 0 LLM) → clear_normal
  都没下定论 → ambiguous，退回 T3 LLM 管线

设计原则：
  - 确定性证据只用预设法条（T1 模板 / T2 api_label_map），零幻觉。
  - T2 API Fail-open：调用失败不拦截，继续白名单/加权/T3。
  - cascade_enabled=False → 全部退回 ambiguous（零回归到纯 LLM）。
  - tier_verdict / filter_tier / filter_reason 可观测，供指标与短路路由。

============================================================================
【级联架构】（参考 Hi-Guard KDD2026 + TianPan 四级架构）
  T1-黑名单: 关键词硬匹配 (<1ms)     → clear_violation，模板证据，0 次 LLM
  T2-api:    商业 API (~50ms)         → clear_violation / clear_normal / 灰区
  T2-weighted: 软信号加权（API 关闭时）→ clear_violation
  T1-白名单: 启发式 (<1ms)            → clear_normal，0 次 LLM
  T3-LLM:    classify/judge/evidence (1~3s) → 灰区才进入

【在 LangGraph 中的位置】
  moderation/graph.py 的入口节点 pre_filter，输出 tier_verdict 供 route_after_pre_filter 路由。
"""

# ── 标准库与配置 ──
import re                                       # 正则：联系方式/URL/手机号/身份证检测
from app.config import settings                 # 级联开关、阈值、长度限制等


# ═══════════════════════════════════════════════════════════════
#  T1 黑名单：类别 → {content_type, score, violated_rules, violated_laws, keywords}
#  【项目自定义】真实部署建议从 data/blacklist.yaml 加载，便于运营热更新
# ═══════════════════════════════════════════════════════════════

BLACKLIST: dict[str, dict] = {
    "pornography": {
        "content_type": "pornography",
        "score": 0.92,  # 预设 anomaly_score，直接用于 action_node
        "violated_rules": ["规则9 禁止涉黄低俗内容"],
        "violated_laws": ["《网络信息内容生态治理规定》第六条",
                          "《互联网信息服务管理办法》第十五条"],
        "keywords": ["约炮", "裸聊", "色情服务", "一夜情", "找小姐"],
    },
    "fraud": {
        "content_type": "fraud",
        "score": 0.88,
        "violated_rules": ["规则11 禁止网络诈骗、虚假营销"],
        "violated_laws": ["《刑法》第二百六十六条 诈骗罪"],
        "keywords": ["刷单兼职", "日赚过千", "投资返利", "稳赚不赔",
                     "高息返本", "免费领红包", "点赞赚钱", "扫码领福利"],
    },
    "illegal_sales": {
        "content_type": "illegal_sales",
        "score": 0.85,
        "violated_rules": ["规则13 禁止违规带货：处方药、烟草、电子烟等"],
        "violated_laws": ["《互联网信息服务管理办法》第十五条"],
        "keywords": ["处方药代购", "万艾可代购", "电子烟批发", "香烟低价",
                     "野生动物制品"],
    },
    "political": {
        "content_type": "political",
        "score": 0.95,
        "violated_rules": ["规则10 危害国家安全"],
        "violated_laws": ["《网络安全法》", "《网络信息内容生态治理规定》第六条"],
        "keywords": ["占位涉政词1"],  # 由运营维护，生产环境替换为真实词表
    },
    "privacy_doxxing": {
        "content_type": "privacy_violation",
        "score": 0.90,
        "violated_rules": ["规则12 禁止人肉搜索、泄露他人隐私"],
        "violated_laws": ["《个人信息保护法》",
                          "《刑法》第二百五十三条之一 侵犯公民个人信息罪"],
        "keywords": ["人肉他", "挂人", "曝光他身份证", "扒他底细"],
    },
}


# ═══════════════════════════════════════════════════════════════
#  正则模式：引流/隐私检测（【项目自定义】针对中文社交平台绕过写法）
# ═══════════════════════════════════════════════════════════════

# 站外引流：微信/QQ/TG 等 + 可选分隔符 + 账号（含谐音绕过：薇信/v信/➕v）
_CONTACT_PATTERN = re.compile(
    r"(?:微信|wx|薇信|v信|加我|➕v|加v|扣扣|qq|TG|telegram)"
    r"[\s:：]?\s*(?:[a-zA-Z0-9_\-]{5,20}|[0-9]{5,12})",
    re.IGNORECASE,
)
_URL_PATTERN = re.compile(r"https?://[^\s，。]+|www\.[^\s，。]+", re.IGNORECASE)  # 外链
# (?<!\d)...(?!\d) 负向前后查找，避免长数字串误匹配手机号
_PHONE_PATTERN = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_IDCARD_PATTERN = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")  # 18 位身份证


# ═══════════════════════════════════════════════════════════════
#  T2 软信号词权重（【项目自定义】累加制，非命中即违规）
# ═══════════════════════════════════════════════════════════════

_SOFT_SIGNALS: dict[str, float] = {
    "废物": 0.15, "脑子有病": 0.15, "去死": 0.20, "脑残": 0.15,
    "白痴": 0.15, "傻子": 0.10,
    "有优惠": 0.10, "进群": 0.10, "代理": 0.10, "招商": 0.05,
    "➕": 0.10, "薇": 0.05, "莪": 0.05,  # 谐音/符号绕过
}


# ═══════════════════════════════════════════════════════════════
#  辅助函数
# ═══════════════════════════════════════════════════════════════

def _blacklist_hit(text: str) -> tuple[str, dict, str] | None:
    """T1 黑名单扫描：子串匹配（非正则，性能 O(词数×文本长)）。

    【功能/流程定位】
      被 pre_filter_node 调用，扫描全文是否含 BLACKLIST 关键词。
      本函数结束后 → 命中则 pre_filter 返回 clear_violation；未命中则继续 T2。

    【思路/代码流程】
      遍历 BLACKLIST 每个类别的 keywords，用 `if kw in text` 子串匹配。
      命中即返回 (类别名, 类别配置dict, 触发关键词)；全未命中返回 None。
      参数：text —— 拼接后的全文。
      返回：(category, cfg, trigger) 或 None。
    """
    for category, cfg in BLACKLIST.items():             # 遍历 5 个违规类别
        for kw in cfg["keywords"]:                      # 遍历该类别关键词
            if kw in text:                              # 子串命中（非正则）
                return category, cfg, kw                # 立刻返回，不再扫后续
    return None                                         # 全未命中


def _weighted_score(text: str) -> tuple[float, list[str]]:
    """T2 软信号加权：词权重累加 + 联系方式/外链加成，上限 1.0。

    【功能/流程定位】
      被 pre_filter_node（API 关闭时）与 _clearly_normal 调用。
      本函数结束后 → 调用方用总分与阈值比较，或判断是否"几乎无信号"。

    【思路/代码流程】
      1. 遍历 _SOFT_SIGNALS，命中则累加权重并记 hits。
      2. 联系方式正则命中 +0.25；外链命中 +0.15。
      3. 总分上限 1.0。
      参数：text —— 全文。
      返回：(总分, 命中项列表)。
    """
    score = 0.0                                         # 累加分初始 0
    hits: list[str] = []                                # 命中项（可观测）
    for kw, w in _SOFT_SIGNALS.items():                 # 遍历软信号词表
        if kw in text:                                  # 子串命中
            score += w                                  # 累加权重
            hits.append(kw)                             # 记命中词
    if _CONTACT_PATTERN.search(text):                   # 联系方式引流
        score += 0.25
        hits.append("[联系方式引流]")
    if _URL_PATTERN.search(text):                       # 外链
        score += 0.15
        hits.append("[外链]")
    return min(score, 1.0), hits                        # 上限 1.0


def _clearly_normal(text: str, report_category: int) -> bool:
    """T1 白名单启发式：必须**同时**满足全部条件才判 clear_normal。

    【功能/流程定位】
      被 pre_filter_node 在 T2 之后调用，过滤明显正常的短内容。
      本函数结束后 → True 则 clear_normal；False 则继续退回 T3。

    条件（任一不满足 → 返回 False，继续后续级联）：
      1. 文本长度 < cascade_normal_max_length（默认15字）
      2. 未命中黑名单
      3. 加权分 <= 0.01（几乎无软信号）
      4. 无联系方式/URL/手机/身份证
      5. report_category == 4（「其他」类举报，误报高发区）

    【项目自定义】白名单故意严格，宁可漏放也不误杀。
    """
    if len(text) >= settings.cascade_normal_max_length:  # 条件1：必须短文本
        return False
    if _blacklist_hit(text) is not None:                # 条件2：未命中黑名单
        return False
    if _weighted_score(text)[0] > 0.01:                 # 条件3：几乎无软信号
        return False
    if (_CONTACT_PATTERN.search(text) or _URL_PATTERN.search(text)
            or _PHONE_PATTERN.search(text) or _IDCARD_PATTERN.search(text)):  # 条件4
        return False
    if report_category != 4:                            # 条件5：举报分类须为「其他」
        return False
    return True                                         # 五条件全满足 → 明确正常


def _templated_evidence(content_list: list[str], category: str,
                        cfg: dict, trigger: str) -> str:
    """T1 黑名单命中时生成确定性证据报告（不调 LLM）。

    【功能/流程定位】
      被 pre_filter_node 在 T1 黑名单命中时调用，写入 state["evidence_detail"]。
      本函数结束后 → pre_filter 返回 clear_violation，路由直奔 evidence（会短路跳过 LLM）。

    【项目自定义】只引用 BLACKLIST 预设法条，避免 LLM 幻觉；
    报告末尾标注「非AI生成」供申诉参考。

    【思路/代码流程】
      拼五章节 Markdown：概述/违规内容/违反条款/处罚依据/申诉说明，
      法条与规则全部来自 cfg 预设，触发词与类别写入概述。
      参数：content_list/category/cfg/trigger。
      返回：Markdown 字符串。
    """
    content_text = "\n".join(f"{i+1}. {c}" for i, c in enumerate(content_list))  # 编号内容
    rules = "\n".join(f"- {r}" for r in cfg["violated_rules"])  # 平台规则列表
    laws = "\n".join(f"- {l}" for l in cfg["violated_laws"])    # 法律列表
    return (
        f"### 一、违规概述\n"
        f"您发布的内容命中平台「{category}」类违规关键词，触发词：`{trigger}`，"
        f"违规类型：{cfg['content_type']}，严重程度分数：{cfg['score']}。\n\n"
        f"### 二、违规内容\n{content_text}\n\n"
        f"### 三、违反条款\n**平台规则：**\n{rules}\n\n**法律法规：**\n{laws}\n\n"
        f"### 四、处罚依据\n依据《网络暴力信息治理规定》第二十一条，平台对违规用户"
        f"可采取警示、删除信息、限制功能、关闭账号等措施。本次命中黑名单关键词，"
        f"属明确违规。\n\n"
        f"### 五、申诉说明\n如您认为判定有误（如关键词出现在引用/反讽/学术讨论语境），"
        f"可通过平台申诉渠道提交复核，平台将在3个工作日内回复。\n"
        f"（本报告由确定性规则引擎生成，非AI生成，引用法条均已核对。）"
    )


# ═══════════════════════════════════════════════════════════════
#  LangGraph 节点：级联主入口
# ═══════════════════════════════════════════════════════════════

async def pre_filter_node(state: dict) -> dict:
    """节点1：级联前置过滤（async，因 T2-api 需 await HTTP）。

    【功能/流程定位】
      对应总体流程 ③。审核图入口节点，用 T1/T2 清掉明确违规/正常，灰区才退回 T3。
      本函数结束后 → 下一个是 route_after_pre_filter（按 tier_verdict 三态分流）。

    【输入】state["content_list"], state["report_category"]（router 填充）
    【输出】tier_verdict + 若 clear_* 则同时填充 classify/judge 等价字段
            （content_type/anomaly_score/rules/laws/judgment，甚至 evidence_detail）

    tier_verdict 三态（供 route_after_pre_filter 使用）：
      clear_violation → 跳 evidence（可能已有 evidence_detail）
      clear_normal    → 跳 action
      ambiguous       → 走 classify LLM 管线

    【思路/代码流程】
      1. cascade_enabled=False → 直接 ambiguous（零回归）。
      2. T1 黑名单命中 → clear_violation + 模板证据，填充分数字段。
      3. T2 API（若开启）：block→clear_violation+API模板证据；pass→clear_normal；
         灰区/失败 fail-open → 继续。
      4. T2 加权（API 关闭时）：分≥阈值 → clear_violation（不填 evidence_detail）。
      5. T1 白名单五条件全满足 → clear_normal。
      6. 否则 → ambiguous 退回 T3。
      参数：state —— 当前图状态（dict，兼容 detect 复用）。
      返回：dict —— 局部更新字段（含 tier_verdict 等）。
    """
    if not settings.cascade_enabled:                    # 级联关闭 → 全部退回 T3（零回归）
        return {
            "tier_verdict": "ambiguous",
            "filter_tier": "T3-llm",
            "filter_reason": "级联已关闭",
        }

    content_list = state["content_list"]                # 取被举报内容列表
    report_category = state["report_category"]          # 取举报分类编号
    full_text = "\n".join(content_list)                 # 拼全文供关键词/正则扫描

    # ── T1 黑名单 ──
    hit = _blacklist_hit(full_text)                     # 子串扫描 BLACKLIST
    if hit is not None:                                 # 命中 → 明确违规，0 LLM
        category, cfg, trigger = hit
        print(f"[级联-T1] 黑名单命中: 类别={category}, 触发词='{trigger}'")
        return {
            "tier_verdict": "clear_violation",          # 路由直奔 evidence
            "filter_tier": "T1-blacklist",
            "filter_reason": f"黑名单命中 {category}: {trigger}",
            "content_type": cfg["content_type"],        # 预设类型
            "classify_reason": f"命中黑名单关键词: {trigger}",
            "anomaly_score": cfg["score"],              # 预设异常分
            "violated_rules": cfg["violated_rules"],    # 预设规则
            "violated_laws": cfg["violated_laws"],      # 预设法律
            "judgment": f"内容命中{category}类黑名单关键词「{trigger}」，属明确违规。",
            "evidence_detail": _templated_evidence(content_list, category, cfg, trigger),  # 模板证据
        }

    # ── T2 商业 API（阿里云内容安全 / 易盾可选）──
    if settings.cascade_api_enabled:                    # API 开关打开才调
        from app.agents.moderation.api_moderation import check_text_api_batch  # 批量检测
        from app.agents.moderation.api_label_map import map_api_label          # label→内部类型
        from app.agents.moderation.api_evidence import api_templated_evidence  # API 模板证据

        api_result = await check_text_api_batch(content_list)  # 批量送审，取最高风险分

        if api_result.error:                            # Fail-open：失败不拦截，继续级联
            print(f"[级联-T2API] 调用失败 fail-open: {api_result.error}")
        else:
            print(
                f"[级联-T2API] score={api_result.risk_score:.2f}, "
                f"suggestion={api_result.suggestion}, "
                f"label={api_result.primary_label}, "
                f"latency={api_result.latency_ms:.0f}ms"
            )

            if api_result.risk_score >= settings.cascade_api_block_threshold:  # 高风险 → 违规
                cfg = map_api_label(api_result.primary_label, provider=api_result.provider)
                return {
                    "tier_verdict": "clear_violation",
                    "filter_tier": "T2-api",
                    "filter_reason": (
                        f"API block label={api_result.primary_label} "
                        f"score={api_result.risk_score:.2f}"
                    ),
                    "content_type": cfg["content_type"],
                    "classify_reason": f"商业API判定违规: label={api_result.primary_label}",
                    "anomaly_score": max(api_result.risk_score, cfg["score"]),  # 就高不就低
                    "violated_rules": cfg["violated_rules"],
                    "violated_laws": cfg["violated_laws"],
                    "judgment": (
                        f"商业文本审核 API 检出违规，"
                        f"标签{api_result.primary_label}，"
                        f"风险分{api_result.risk_score:.2f}。"
                    ),
                    "evidence_detail": api_templated_evidence(
                        content_list, api_result, cfg
                    ),
                    "api_risk_score": api_result.risk_score,      # 可观测
                    "api_primary_label": api_result.primary_label,
                }

            if (settings.cascade_api_pass_threshold > 0
                    and api_result.risk_score <= settings.cascade_api_pass_threshold):  # 低风险 → 正常
                return {
                    "tier_verdict": "clear_normal",
                    "filter_tier": "T2-api",
                    "filter_reason": f"API pass score={api_result.risk_score:.2f}",
                    "content_type": "normal",
                    "classify_reason": "商业API判定正常",
                    "anomaly_score": 0.1,
                    "violated_rules": [],
                    "violated_laws": [],
                    "judgment": "商业文本审核 API 判定内容正常。",
                    "evidence_detail": "",
                    "api_risk_score": api_result.risk_score,
                    "api_primary_label": api_result.primary_label,
                }

            print(f"[级联-T2API] 灰区 score={api_result.risk_score:.2f}，继续级联")

    # ── T2 加权（仅 cascade_api_enabled=False 时启用，避免与 API 重复判）──
    score, hits = _weighted_score(full_text)            # 软信号累加分
    if not settings.cascade_api_enabled:                # API 关时才用加权替代
        if score >= settings.cascade_weighted_high_threshold:  # 超阈值 → 违规
            ctype = (
                "spam" if any("联系方式" in h or "外链" in h for h in hits)
                else "other_violation"
            )
            print(f"[级联-T2] 加权判违规: score={score:.2f}, 命中={hits}")
            rules = (
                ["规则11 禁止引流到外部平台"] if ctype == "spam"
                else ["规则15 其他违规"]
            )
            return {
                "tier_verdict": "clear_violation",
                "filter_tier": "T2-weighted",
                "filter_reason": f"加权评分 {score:.2f}: {','.join(hits)}",
                "content_type": ctype,
                "classify_reason": f"加权信号超阈值: {hits}",
                "anomaly_score": score,
                "violated_rules": rules,
                "violated_laws": [],
                "judgment": f"内容含多重违规信号（{','.join(hits)}），加权评分{score:.2f}。",
                # 不填 evidence_detail → evidence_node 用 LLM 生成
            }

    # ── T1 白名单 ──
    if _clearly_normal(full_text, report_category):     # 五条件全满足 → 明确正常
        print(f"[级联-T1W] 判明确正常: 长度={len(full_text)}, category={report_category}")
        return {
            "tier_verdict": "clear_normal",
            "filter_tier": "T1-whitelist",
            "filter_reason": "短文本+无信号+举报分类为其他",
            "content_type": "normal",
            "classify_reason": "白名单启发式判定正常",
            "anomaly_score": 0.1,
            "violated_rules": [],
            "violated_laws": [],
            "judgment": "内容简短且无任何违规信号，判定正常。",
            "evidence_detail": "",
        }

    # ── T3 退回 LLM ──
    print(f"[级联] 退回LLM: 长度={len(full_text)}, 加权={score:.2f}")
    return {
        "tier_verdict": "ambiguous",                    # 灰区，走 classify 起完整 T3
        "filter_tier": "T3-llm",
        "filter_reason": "级联未明确判定，退回LLM",
    }
