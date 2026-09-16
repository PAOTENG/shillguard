"""恶意行为用户检测 · 证据生成 Agent 的数据模型（API 契约）。

============================================================================
本文件对应总体流程的哪一部分
============================================================================
对应 __init__.py 总体流程编号 ⑥⑫ 的契约层（被 router.py::detect_evidence 使用）：
  - UserEvidenceInput     —— 请求体里单个违规用户的输入模型（Java 打包发来）
  - DetectEvidenceRequest —— 批量证据生成请求体（users 列表）
  - UserEvidenceResult    —— 单用户证据生成结果（evidenceDetail + violatingItems）
  - DetectEvidenceResponse—— 批量证据生成响应体（results 列表）

调用关系（谁来调用本文件）：
  - router.py::detect_evidence() 用 DetectEvidenceRequest 解析请求、DetectEvidenceResponse 序列化响应。
  - 本文件不调用任何业务逻辑，纯 Pydantic 契约模型。
  - 字段名必须与 Java DTO 一一对应（camelCase），是 Java ↔ Python 的接口契约。

============================================================================
本部分流程与思路
============================================================================
契约层思路：
  - 用 Pydantic BaseModel 定义请求/响应结构，FastAPI 自动做参数校验 + 文档生成。
  - 字段名用 camelCase（userId/muteAction/violatingItems...），与 Java DTO 对齐，
    Java 侧直接序列化/反序列化，无需字段名映射。
  - 用 Field(..., description=) 标注每个字段含义 + 默认值，既给 FastAPI /docs 用，
    也给代码读者当字段级文档。
  - 输入模型(UserEvidenceInput)字段全部来自链路A /ai/detect-users 的级联结果，
    保证两链路数据衔接顺畅。

============================================================================
【流程位置】
  Java 调 /ai/detect-users → 得到每用户 muteAction + violatingItems
  → 对 muteAction != "none" 的用户调本 Agent /ai/detect-evidence
  → 本 Agent 结合 RAG 法律法规，生成完整证据报告 + 列出具体违规帖子/评论
  → Java 把证据写进 agent_mute_record 与 user_risk_record，用于禁言与申诉复核

注意：本文件是 Java 与 Python 的接口契约，字段名必须与 Java DTO 一一对应。
"""

# ── Pydantic：数据模型基类与字段定义 ──
from pydantic import BaseModel, Field                 # BaseModel=模型基类；Field=字段定义(默认值+描述)
from typing import List                               # List 类型注解（兼容旧 Pydantic v1 风格）


class UserEvidenceInput(BaseModel):
    """单个违规用户的证据生成输入（Java 打包发来）。

    【功能/流程定位】
      请求体 DetectEvidenceRequest.users 列表的单项，字段全部来自链路A
      /ai/detect-users 的级联结果。router.py 把它转成 graph 的 initial_state。

    【思路/代码流程】
      每个字段用 Field(默认值, description=) 标注：必填用 ... ，可选给默认值。
      字段名 camelCase 与 Java DTO 对齐。

    【字段来源链路】
      violatingItems / muteAction / contentType / violatedRules / violatedLaws /
      anomalyScore / judgment ← 均由 detect-users 级联结果填充。
    """
    userId: int = Field(..., description="用户ID")    # 必填：用户ID（Java 主键）
    violatingItems: List[str] = Field(                # 必填：已确认违规内容原文列表（证据核心素材）
        ...,
        description=(
            "经 /ai/detect-users 级联确认的违规内容原文列表（非全部内容），"
            "直接作为证据报告的核心素材"
        ),
    )
    muteAction: str = Field(                          # 禁言动作，默认 mute_3days
        "mute_3days",
        description="禁言动作：mute_3days | mute_7days，供证据报告描述处罚依据",
    )
    contentType: str = Field(                         # 主导违规类型，默认 other_violation
        "other_violation",
        description="主导违规类型（来自 /ai/detect-users 的 contentType），指导 RAG 检索方向",
    )
    violatedRules: List[str] = Field(default=[], description="级联已识别的违反平台规则（T1/T2 命中时有值）")  # 已知规则
    violatedLaws: List[str] = Field(default=[], description="级联已识别的违反法律条文（T1/T2 命中时有值）")  # 已知法律
    anomalyScore: float = Field(0.0, description="最高违规内容的异常分数")  # 最高违规分数，默认 0.0
    judgment: str = Field("", description="打分阶段的判定说明摘要")          # 判定说明，默认空串


class DetectEvidenceRequest(BaseModel):
    """批量证据生成请求体。

    【功能/流程定位】
      POST /ai/detect-evidence 的请求体，被 router.py::detect_evidence() 接收。
      本模型结束后 → router 遍历 users 逐个跑证据图。

    【思路/代码流程】
      只含一个 users 字段（待出证用户列表），FastAPI 自动把 JSON body 反序列化为本模型。
    """
    users: List[UserEvidenceInput] = Field(..., description="待生成证据的违规用户列表")  # 必填：违规用户列表


class UserEvidenceResult(BaseModel):
    """单个用户的证据生成结果。

    【功能/流程定位】
      响应体 DetectEvidenceResponse.results 列表的单项，由 router.py 在每用户跑完图后包装。

    【思路/代码流程】
      evidenceDetail 默认空串（用户跳过/失败时为空），violatingItems 默认空列表。
      Java 拿到后落库 agent_mute_record + user_risk_record，用于禁言通知与申诉展示。
    """
    userId: int = Field(..., description="用户ID")    # 必填：用户ID
    evidenceDetail: str = Field(                      # 完整证据报告（Markdown），默认空串
        "",
        description="完整证据报告（Markdown，含违反的法律法规条款+平台规则+引用的违规内容原文）",
    )
    violatingItems: List[str] = Field(                # 具体违规帖子/评论原文列表，默认空
        default=[],
        description="具体违规的帖子/评论原文列表（用于禁言通知与申诉展示）",
    )


class DetectEvidenceResponse(BaseModel):
    """批量证据生成响应体。

    【功能/流程定位】
      POST /ai/detect-evidence 的响应体，被 router.py::detect_evidence() 返回。
      FastAPI 据本模型（router 装饰器的 response_model）自动序列化 JSON 给 Java。

    【思路/代码流程】
      只含一个 results 字段（每用户证据结果列表），与请求 users 一一对应（顺序一致）。
    """
    results: List[UserEvidenceResult] = Field(default=[], description="每个用户的证据结果")  # 证据结果列表，默认空
