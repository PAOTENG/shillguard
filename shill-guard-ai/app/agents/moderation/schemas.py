"""审核 Agent 的数据模型（API 契约：Java ↔ Python）。

============================================================================
本文件对应总体流程的哪一部分
============================================================================
对应 __init__.py 总体流程编号 ①② + 轮询的契约层：
  - ModerateRequest         —— POST /ai/moderate 请求体（Java 组装）
  - ModerateSubmitResponse  —— POST 立即响应（只含 taskId）
  - ModerateTaskResult      —— GET 轮询响应（status + result/error）
  - ModerateResult          —— 审核完成结果（落进 TaskResult.result）
  - ModerateResponse        —— 遗留批量包装（当前异步模式未使用）

调用关系（谁来调用本文件）：
  - router.py::moderate / moderate_result / _run_moderate_task 使用上述模型。
  - 本文件不调用业务逻辑，纯 Pydantic 契约。
  - 字段名 camelCase 与 Java DTO 一一对应。

============================================================================
本部分流程与思路
============================================================================
  - Pydantic BaseModel：FastAPI 自动校验请求 + 生成 OpenAPI + 序列化响应。
  - 字段 camelCase 对齐 Java，减少跨语言映射层。
  - 异步模式：POST 只返回 taskId；结果在 GET 的 ModerateTaskResult.result 里。

============================================================================
【Pydantic BaseModel 作用（官方 FastAPI 集成）】
  - 自动校验请求 JSON（缺字段/类型错误 → 422 Unprocessable Entity）
  - 自动生成 OpenAPI/Swagger 文档（访问 /docs）
  - 响应时自动序列化为 JSON
"""

# ── Pydantic：数据模型基类与字段定义 ──
from pydantic import BaseModel, Field                 # BaseModel=模型基类；Field=默认值+描述
from typing import List, Optional                     # List / Optional 类型注解


class ModerateRequest(BaseModel):
    """POST /ai/moderate 请求体（Java AgentController 组装）。

    【功能/流程定位】
      对应总体流程 ①。被 router.py::moderate() 接收，字段填入图 initial_state
      与结果 ModerateResult 的 reportId/reportedUserId。

    【思路】必填用 Field(...)；contentType 默认 comment；reportCategory 见 prompts 映射。
    """
    reportId: int = Field(..., description="举报记录ID")                    # 必填：举报主键
    reportedUserId: int = Field(..., description="被举报用户ID")            # 必填：被举报用户
    contentType: str = Field("comment", description="内容类型：comment 或 post")  # 内容形态
    contentList: List[str] = Field(..., description="被举报的内容列表（可能多条）")  # 审核素材
    reportCategory: int = Field(
        0,
        description="举报分类编号，见 prompts.get_report_category_desc",
    )                                                                       # 0~4，注入 CLASSIFY


class ModerateResult(BaseModel):
    """审核完成后的结果（GET /ai/moderate/result/{taskId} 中返回）。

    【功能/流程定位】
      对应总体流程 ② 收尾。由 _run_moderate_task 从图 final_state 包装，
      经 ModerateTaskResult.result 返回给 Java 落库/处置。

    【思路】含打分、类型、条款、证据、处罚动作、级联可观测字段（tierVerdict/filterTier）。
    """
    reportId: int = Field(..., description="举报记录ID")
    reportedUserId: int = Field(..., description="被举报用户ID")
    anomalyScore: float = Field(..., description="异常分数 0~1，越高越严重")
    contentType: str = Field(..., description="LLM/级联判定的内容类型")
    violatedRules: List[str] = Field(default=[], description="违反的平台规则列表")
    violatedLaws: List[str] = Field(default=[], description="违反的法律条文列表")
    evidenceSummary: str = Field("", description="判定说明（一句话摘要）")
    evidenceDetail: str = Field("", description="完整证据报告（Markdown）")
    action: str = Field(
        "none",
        description="处罚动作：none=忽略 | manual_review=人工复核 | auto_mute=自动禁言",
    )
    tierVerdict: str = Field(
        "ambiguous",
        description="级联判定：clear_violation / clear_normal / ambiguous",
    )
    filterTier: str = Field(
        "T3-llm",
        description="命中层级：T1-blacklist / T1-whitelist / T2-api / T2-weighted / T3-llm",
    )


class ModerateResponse(BaseModel):
    """（遗留）批量审核响应包装，当前异步模式未使用。

    【功能/流程定位】历史同步批量接口遗留；现行用 ModerateSubmitResponse + 轮询。
    """
    taskId: str = Field(..., description="任务ID")
    results: List[ModerateResult] = Field(default=[], description="审核结果列表")


class ModerateSubmitResponse(BaseModel):
    """POST /ai/moderate 立即响应：只返回 taskId，结果需轮询。

    【功能/流程定位】对应总体流程 ① 的返回体。Java 拿到 taskId 后开始轮询。
    """
    taskId: str = Field(..., description="异步任务 ID（UUID）")
    status: str = Field("pending", description="pending / processing / done / error")


class ModerateTaskResult(BaseModel):
    """GET /ai/moderate/result/{task_id} 轮询响应。

    【功能/流程定位】对应轮询接口。status=done 时 result 有值；error 时 error 有值；
    not_found 表示 taskId 无效或服务重启丢失。
    """
    taskId: str                                                 # 任务 ID
    status: str  # pending | processing | done | error | not_found
    result: Optional[ModerateResult] = None   # status=done 时填充
    error: Optional[str] = None               # status=error 时填充
