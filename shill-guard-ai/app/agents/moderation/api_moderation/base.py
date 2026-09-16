"""商业文本审核 API 的统一返回结构（Adapter 模式）。

============================================================================
本文件对应总体流程的哪一部分
============================================================================
对应 __init__.py 总体流程编号 ③（被 api_moderation 各厂商客户端与 cascade 使用）：
  - ModerationApiResult —— 单次商业 API 文本检测的标准化结果 dataclass

调用关系：
  - aliyun.py / yidun.py 把厂商原始 JSON 填进本结构返回；
  - cascade.py 只依赖本结构字段（risk_score/primary_label/error/...），不关心底层厂商。

============================================================================
本部分流程与思路
============================================================================
Adapter 模式：cascade 与厂商 SDK 解耦。新增百度等厂商时，实现 check_text_xxx()
→ 返回 ModerationApiResult 即可，cascade / api_label_map / api_evidence 无需改。

【dataclass】
  【官方 Python 3.7+】@dataclass 自动生成 __init__，比手写 dict 更清晰。
"""

# ── 标准库：dataclass 定义不可变风格的结果容器 ──
from dataclasses import dataclass, field


@dataclass
class ModerationApiResult:
    """单次商业 API 文本检测的标准化结果。

    【功能/流程定位】
      T2 API 层的统一输出契约。cascade 用 risk_score 与阈值比较；
      map_api_label 用 primary_label；api_templated_evidence 用命中词与延迟。
      error 非空 → cascade Fail-open（不拦截，继续白名单/加权/T3）。
    """

    provider: str = ""              # "aliyun"（主力）/ "yidun"（保留）/ "baidu"（预留）
    suggestion: str = "review"      # pass | review | block（统一字符串，便于日志）
    risk_score: float = 0.5         # 0~1 连续分，供 cascade 阈值比较
    primary_label: str = "normal"   # 厂商主标签，易盾为数字字符串如 "600"
    primary_label_name: str = ""    # 中文描述，如「谩骂」
    sub_labels: list[str] = field(default_factory=list)    # 子标签列表
    hit_keywords: list[str] = field(default_factory=list)  # 命中敏感词
    raw: dict = field(default_factory=dict)              # 原始 JSON，调试用
    latency_ms: float = 0.0         # 请求耗时（可观测性）
    error: str | None = None          # 非空 = 调用失败 → cascade fail-open
