"""厂商 label → ShillGuard 内部违规类型映射。

============================================================================
本文件对应总体流程的哪一部分
============================================================================
对应 __init__.py 总体流程编号 ③（被 cascade.py T2 API block 分支调用）：
  - map_api_label() —— 把厂商 primary_label 映射为内部 content_type/score/rules/laws
  - ALIYUN_LABEL_MAP / YIDUN_LABEL_MAP / DEFAULT_VIOLATION —— 映射表

调用关系：
  - cascade.py 在 API risk_score ≥ block 阈值后调 map_api_label，填 state + 喂 api_templated_evidence。
  - 本文件无 IO，纯映射表。

============================================================================
本部分流程与思路
============================================================================
商业 API 返回厂商私有 label（阿里云字符串 / 易盾数字码），本文件把它翻译成
本平台统一的 content_type + 预设分数 + 预设法条，供级联短路时直接定罪与出模板证据。
未知 label 回退 DEFAULT_VIOLATION，避免映射表漏覆盖导致崩溃。

【阿里云 label 定义】（TextModeration 增强版，comment_detection_pro）
  profanity         辱骂 | cyberbullying    网络暴力
  sexual_content    色情 | sexual_suggestive 低俗
  violence          暴恐 | political_content 涉政
  contraband        违禁 | ad_compliance     广告法
  negative_content  不良内容 | spam          灌水广告

【易盾 label 定义】（文本检测 v5，已弃用，保留供回滚）
  100 色情 | 200 广告 | 260 广告法 | 300 暴恐 | 400 违禁
  500 涉政 | 600 谩骂 | 700 灌水 | 900 其他 | 1100 涉价值观

【维护】
  阿里云新增 label 时在 ALIYUN_LABEL_MAP 追加；未知 label 回退 DEFAULT_VIOLATION。
"""

YIDUN_LABEL_MAP: dict[str, dict] = {
    "100": {
        "content_type": "pornography",
        "score": 0.90,
        "violated_rules": ["规则9 禁止涉黄低俗内容"],
        "violated_laws": ["《网络信息内容生态治理规定》第六条"],
    },
    "200": {
        "content_type": "spam",
        "score": 0.80,
        "violated_rules": ["规则11 禁止引流到外部平台"],
        "violated_laws": [],
    },
    "260": {
        "content_type": "spam",
        "score": 0.78,
        "violated_rules": ["规则11 禁止虚假营销"],
        "violated_laws": [],
    },
    "300": {
        "content_type": "violence",
        "score": 0.88,
        "violated_rules": ["规则10 禁止暴恐内容"],
        "violated_laws": [],
    },
    "400": {
        "content_type": "illegal_sales",
        "score": 0.85,
        "violated_rules": ["规则13 禁止违规带货"],
        "violated_laws": [],
    },
    "500": {
        "content_type": "political",
        "score": 0.95,
        "violated_rules": ["规则10 危害国家安全"],
        "violated_laws": ["《网络安全法》"],
    },
    "600": {
        "content_type": "cyberbullying",
        "score": 0.82,
        "violated_rules": ["规则8 禁止网络暴力、人身攻击"],
        "violated_laws": ["《网络暴力信息治理规定》"],
    },
    "700": {
        "content_type": "spam",
        "score": 0.70,
        "violated_rules": ["规则11 禁止灌水刷屏"],
        "violated_laws": [],
    },
    "900": {
        "content_type": "other_violation",
        "score": 0.75,
        "violated_rules": ["规则15 其他违规"],
        "violated_laws": [],
    },
    "1100": {
        "content_type": "other_violation",
        "score": 0.80,
        "violated_rules": ["规则15 其他违规"],
        "violated_laws": [],
    },
}

DEFAULT_VIOLATION = {
    "content_type": "other_violation",
    "score": 0.75,
    "violated_rules": ["规则15 其他违规"],
    "violated_laws": [],
}

# ── 阿里云内容安全标签映射 ──────────────────────────────────────────────────
ALIYUN_LABEL_MAP: dict[str, dict] = {
    "profanity": {
        "content_type": "cyberbullying",
        "score": 0.85,
        "violated_rules": ["规则8 禁止网络暴力、人身攻击"],
        "violated_laws": ["《网络暴力信息治理规定》"],
    },
    "cyberbullying": {
        "content_type": "cyberbullying",
        "score": 0.88,
        "violated_rules": ["规则8 禁止网络暴力"],
        "violated_laws": ["《网络暴力信息治理规定》"],
    },
    "sexual_content": {
        "content_type": "pornography",
        "score": 0.90,
        "violated_rules": ["规则9 禁止涉黄低俗内容"],
        "violated_laws": ["《网络信息内容生态治理规定》第六条"],
    },
    "sexual_suggestive": {
        "content_type": "pornography",
        "score": 0.80,
        "violated_rules": ["规则9 禁止低俗内容"],
        "violated_laws": ["《网络信息内容生态治理规定》第六条"],
    },
    "violence": {
        "content_type": "violence",
        "score": 0.88,
        "violated_rules": ["规则10 禁止暴恐内容"],
        "violated_laws": [],
    },
    "political_content": {
        "content_type": "political",
        "score": 0.95,
        "violated_rules": ["规则10 危害国家安全"],
        "violated_laws": ["《网络安全法》"],
    },
    "contraband": {
        "content_type": "illegal_sales",
        "score": 0.85,
        "violated_rules": ["规则13 禁止违规带货"],
        "violated_laws": [],
    },
    "ad_compliance": {
        "content_type": "spam",
        "score": 0.78,
        "violated_rules": ["规则11 禁止虚假营销"],
        "violated_laws": [],
    },
    "spam": {
        "content_type": "spam",
        "score": 0.72,
        "violated_rules": ["规则11 禁止灌水刷屏"],
        "violated_laws": [],
    },
    "negative_content": {
        "content_type": "other_violation",
        "score": 0.75,
        "violated_rules": ["规则15 其他违规"],
        "violated_laws": [],
    },
    "inappropriate_profanity": {
        "content_type": "cyberbullying",
        "score": 0.82,
        "violated_rules": ["规则8 禁止网络暴力、人身攻击"],
        "violated_laws": ["《网络暴力信息治理规定》"],
    },
}


def map_api_label(primary_label: str, provider: str = "aliyun") -> dict:
    """厂商 primary_label → 内部 cfg dict。

    【功能/流程定位】
      对应总体流程 ③ 的 T2 API 分支。被 cascade.py::pre_filter_node 调用。
      本函数结束后 → 调用方用 cfg 填 state（content_type/score/rules/laws）并生成模板证据。

    【思路/代码流程】
      1. primary_label 转 str（兼容数字码）。
      2. provider=yidun → 查 YIDUN_LABEL_MAP；否则查 ALIYUN_LABEL_MAP。
      3. 未命中 → DEFAULT_VIOLATION（other_violation + 规则15）。

    参数:
        primary_label: 厂商返回的主标签
            阿里云: 字符串如 "profanity" / "cyberbullying"
            易盾:   数字字符串如 "600"
        provider: "aliyun"（默认）| "yidun"

    返回 dict 含 keys: content_type, score, violated_rules, violated_laws
    """
    label = str(primary_label)                          # 统一字符串 key
    if provider == "yidun":                             # 易盾数字码映射
        return YIDUN_LABEL_MAP.get(label, DEFAULT_VIOLATION)
    return ALIYUN_LABEL_MAP.get(label, DEFAULT_VIOLATION)  # 阿里云字符串映射，未知回退默认
