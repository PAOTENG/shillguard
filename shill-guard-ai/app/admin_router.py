"""实验控制接口：运行时切换级联开关 + LangSmith 项目名。

供 loadtest/ragas_eval.py 在对比实验中调用：
  POST /ai/admin/set-experiment  body: {"cascade_on": true/false}

效果：
  cascade_on=true  → 开启 T1+T2-api 级联，LangSmith 项目写入 shillguard-cascade-ON
  cascade_on=false → 关闭所有级联，全部走 T3-LLM，写入 shillguard-cascade-OFF

【安全说明】
  仅供内部评测使用，生产环境应在路由层加鉴权或直接删除此 router。
"""
import os

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import settings

router = APIRouter()

PROJECT_CASCADE_ON  = "shillguard-cascade-ON"
PROJECT_CASCADE_OFF = "shillguard-cascade-OFF"


class ExperimentRequest(BaseModel):
    cascade_on: bool


class ExperimentResponse(BaseModel):
    cascade_enabled: bool
    cascade_api_enabled: bool
    langchain_project: str


@router.post("/admin/set-experiment", response_model=ExperimentResponse)
def set_experiment(req: ExperimentRequest) -> ExperimentResponse:
    """运行时切换级联开关，并同步更新 LangSmith 项目名。

    ragas_eval.py 在每批测试开始前调用一次，之后所有 LLM 调用的 trace
    自动归档到对应项目，方便 LangSmith 网页直接对比 token 用量。
    """
    project = PROJECT_CASCADE_ON if req.cascade_on else PROJECT_CASCADE_OFF

    # 同步到 os.environ，LangChain 每次创建 tracer 时读取此变量
    os.environ["LANGCHAIN_PROJECT"] = project

    # 同步到 settings（供其他模块引用）
    settings.cascade_enabled    = req.cascade_on
    settings.cascade_api_enabled = req.cascade_on
    settings.langchain_project  = project

    print(
        f"[admin] experiment set: cascade={'ON' if req.cascade_on else 'OFF'}, "
        f"langchain_project={project}"
    )

    return ExperimentResponse(
        cascade_enabled=settings.cascade_enabled,
        cascade_api_enabled=settings.cascade_api_enabled,
        langchain_project=project,
    )


@router.get("/admin/experiment-status", response_model=ExperimentResponse)
def get_experiment_status() -> ExperimentResponse:
    """查询当前实验配置（级联状态 + LangSmith 项目名）。"""
    return ExperimentResponse(
        cascade_enabled=settings.cascade_enabled,
        cascade_api_enabled=settings.cascade_api_enabled,
        langchain_project=os.environ.get("LANGCHAIN_PROJECT", settings.langchain_project),
    )
