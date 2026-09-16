"""证据生成 Agent 的 FastAPI 接口：POST /ai/detect-evidence（Detect Agent 证据链路 B 的对外入口）。

============================================================================
本文件对应总体流程的哪一部分
============================================================================
对应 __init__.py 总体流程编号 ⑥⑦⑫（证据生成链路 B 的 HTTP 接入与调度层）：
  ⑥ detect_evidence() —— HTTP 入口：接请求、逐用户构造 initial_state、调图、汇总结果
  ⑦ get_graph()       —— 懒加载图单例（build_graph 在 graph.py）
  ⑫ detect_evidence() 收尾 —— 包装 UserEvidenceResult 返回 DetectEvidenceResponse

调用关系（谁来调用本文件）：
  - app/main.py 直接 import 本 router 挂载 → POST /ai/detect-evidence。
  - 本文件调用 detect/graph.py::build_graph 与 detect/schemas.py 的契约模型。
  - 不调用打分链路（链路A 在 moderation/detect_router.py）；Java 在两接口间做串联。

============================================================================
本部分流程与思路
============================================================================
本文件只做【HTTP 接入 + 逐用户调度 graph.ainvoke】，Agent 逻辑在 graph.py + prompts.py。
  1. 接收 DetectEvidenceRequest（Java 传来的违规用户列表，字段来自链路A 的级联结果）。
  2. get_graph() 拿证据图单例（首次调用时 build_graph 编译并缓存）。
  3. 串行遍历 users：
     - 无 violatingItems → 直接返回空结果（跳过该用户）。
     - 有 violatingItems → 构造 initial_state → graph.ainvoke 跑 4 节点 → 取 final_state。
     - 单用户失败 → 降级为空结果，打印错误，继续下一个（不阻断整批）。
  4. 把每用户 evidenceDetail + violatingItems 包装成 UserEvidenceResult，返回 DetectEvidenceResponse。

设计要点：
  - 职责单一：只接 HTTP + 调度，不写 Agent 逻辑，便于与 moderation detect_router 风格统一。
  - 图单例懒加载：build_graph 只编译一次，避免每请求重复建图开销。
  - 串行逐用户：当前实现串行（与 detect_users 一致），量大时可改 asyncio.gather + Semaphore 限流。
  - 全链路降级：单用户失败不阻断批次，保证批量出证的健壮性。

============================================================================
【业务链路】
  1. 管理员触发 → POST /ai/detect-users（批量逐条级联，返回 muteAction + violatingItems）
  2. muteAction != "none" 的违规用户 → POST /ai/detect-evidence（本接口）
  3. Java 落库 evidenceDetail + violatingItems 到禁言记录

【职责边界】
  本文件只做 HTTP 接入 + 逐用户调度 graph.ainvoke；
  Agent 逻辑在 detect/graph.py + detect/prompts.py。
"""

# ── FastAPI：路由与请求/响应模型绑定 ──
from fastapi import APIRouter                       # APIRouter：创建子路由对象

# ── 项目内：契约模型与图构建 ──
from app.agents.detect.schemas import (             # 证据生成的 API 契约（Java DTO 对齐）
    DetectEvidenceRequest,                          #   请求体：批量违规用户列表
    DetectEvidenceResponse,                         #   响应体：批量证据结果
    UserEvidenceResult,                             #   单用户证据结果
)
from app.agents.detect.graph import build_graph     # 证据图构建函数（4 节点线性图）

router = APIRouter()                                # 创建证据生成路由对象，由 main.py 挂载

_graph_instance = None                              # 图单例缓存（模块级全局，懒加载）


def get_graph():
    """懒加载证据 agent 图单例。

    【功能/流程定位】
      对应总体流程 ⑦。被 detect_evidence() 调用，首次调用时调 build_graph() 编译图并缓存，
      后续直接返回缓存实例，避免每请求重复建图。
      本函数结束后 → 调用方 detect_evidence() 用返回的 graph.ainvoke 驱动证据链路。

    【思路/代码流程】
      1. 声明使用模块级全局 _graph_instance。
      2. 首次（None）→ build_graph() 编译 4 节点图并赋值给 _graph_instance。
      3. 返回缓存实例。
      返回：编译后的 LangGraph 图实例。
    """
    global _graph_instance                          # 声明修改模块级全局（Python 函数内赋值需 global）
    if _graph_instance is None:                     # 首次调用：尚未构建
        _graph_instance = build_graph()             # 构建并编译 4 节点证据图，缓存到模块全局
    return _graph_instance                          # 返回（缓存的）图单例


@router.post("/detect-evidence", response_model=DetectEvidenceResponse)
async def detect_evidence(request: DetectEvidenceRequest) -> DetectEvidenceResponse:
    """对一批违规用户逐个运行证据生成 LangGraph，生成可用于申诉/禁言通知的完整报告。

    【功能/流程定位】
      对应总体流程 ⑥⑫。证据生成链路 B 的 HTTP 入口，接收 Java 传来的违规用户列表，
      逐用户跑证据图，汇总 evidenceDetail + violatingItems 返回。
      本函数结束后 → Java 侧落库（⑬，不在 Python 内）。

    【思路/代码流程】
      1. get_graph() 取证据图单例。
      2. 遍历 request.users：
         - 无 violatingItems → 空 UserEvidenceResult（跳过）。
         - 构造 initial_state（violating_items/mute_action/content_type/anomaly_score/
           violated_rules/violated_laws/judgment），与 DetectEvidenceState 输入字段对齐。
         - graph.ainvoke 跑 4 节点 → final_state；异常 → 降级空结果继续。
         - 包装 UserEvidenceResult（evidenceDetail + violatingItems）。
      3. 返回 DetectEvidenceResponse(results)。

    输入 users[] 每项含（均来自 /ai/detect-users 的级联结果）：
      violatingItems, muteAction, contentType, violatedRules, violatedLaws, anomalyScore, judgment

    【当前实现】串行逐用户；量大时可改 asyncio.gather + Semaphore 限流。

      参数：request —— DetectEvidenceRequest，含 users 列表。
      返回：DetectEvidenceResponse —— 含每个用户的证据结果列表。
    """
    graph = get_graph()                             # 取证据图单例（首次会 build_graph）
    results: list[UserEvidenceResult] = []          # 收集每用户的证据结果

    for user in request.users:                      # 串行遍历违规用户（量大可改并行 + 限流）
        if not user.violatingItems:                 # 无违规条目 → 没必要跑证据图
            results.append(UserEvidenceResult(userId=user.userId))  # 空 evidenceDetail + 空 violatingItems
            continue                                # 跳过该用户，处理下一个

        # 构造图的初始 state：字段名对齐 DetectEvidenceState 的输入字段（snake_case）
        initial_state = {
            "violating_items": user.violatingItems,      # 已确认违规条目（核心素材）
            "mute_action": user.muteAction,              # 禁言动作（3天/7天，决定报告处罚依据）
            "content_type": user.contentType,            # 主导违规类型（指导 RAG 检索方向）
            "anomaly_score": user.anomalyScore,          # 最高违规分数（写进报告）
            "violated_rules": user.violatedRules,        # 已知违反规则（参考 + 校验）
            "violated_laws": user.violatedLaws,          # 已知违反法律（参考 + 校验）
            "judgment": user.judgment,                   # 打分阶段判定说明（写进报告）
        }
        try:
            final_state = await graph.ainvoke(initial_state)  # 异步驱动 4 节点证据图，等全部跑完
        except Exception as e:                       # 单用户跑图失败 → 降级为空结果，不阻断批次
            print(f"[证据] 用户 {user.userId} agent 执行失败: {e}")
            results.append(UserEvidenceResult(userId=user.userId))  # 空 evidenceDetail
            continue                                # 继续下一个用户

        # 包装该用户证据结果：evidenceDetail 来自图，violatingItems 优先用图回传值，回退原始输入
        results.append(UserEvidenceResult(
            userId=user.userId,                                           # 用户ID
            evidenceDetail=final_state.get("evidence_detail", ""),        # 4 节点产出的 Markdown 证据报告
            violatingItems=final_state.get("violating_items", user.violatingItems),  # 图可能回传处理后的违规条目
        ))
        print(                                       # 打印该用户出证统计，便于观测
            f"[证据] 用户 {user.userId}: "
            f"证据{len(final_state.get('evidence_detail', ''))}字, "
            f"违规条目{len(final_state.get('violating_items', user.violatingItems))}条"
        )

    return DetectEvidenceResponse(results=results)  # 返回批量证据响应，Java 侧落库禁言记录
