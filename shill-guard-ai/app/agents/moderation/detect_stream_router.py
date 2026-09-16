"""流式恶意用户检测：POST /ai/detect-users-stream（Detect Agent 打分链路 SSE 版）。

============================================================================
本文件对应总体流程的哪一部分
============================================================================
业务属 Detect Agent（见 app/agents/detect/__init__.py 链路A），
是 detect_router.py 的 SSE 实时可视化版本：
  - detect_users_stream() —— HTTP 入口，返回 StreamingResponse
  - _stream_detect()      —— 逐用户 await _process_user，yield SSE 事件
  - _sse()                —— 构造官方 SSE 帧（event + data + 空行）

调用关系：
  - 复用 detect_router._process_user（级联逻辑与 /ai/detect-users 完全一致）
  - 前端管理页用 EventSource / fetch+ReadableStream 实时看日志与分数

============================================================================
本部分流程与思路
============================================================================
与 detect-users 同逻辑、不同传输：批量 JSON 一次返回 → SSE 边跑边推。
每用户用 redirect_stdout 捕获 print 日志推 event:log；完成后推 event:score；
全部结束推 event:done（含完整 results）。

【SSE 事件类型】
  event: stage  — 阶段说明（开始打分）
  event: log    — 捕获的 Python print（级联调试信息等）
  event: score  — 单用户检测完成（含 muteAction / violationCount）
  event: done   — 全部完成，data.results 含完整结果列表
  event: error  — 顶层异常

【官方 SSE 格式】
  event: xxx\ndata: {...}\n\n
"""
import io
import json
import contextlib

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.agents.moderation.detect_router import (
    DetectUsersRequest,
    UserScoreResult,
    _process_user,
)

router = APIRouter()


def _sse(event: str, data: dict) -> str:
    """构造一条 SSE 帧（官方 SSE 规范：event + data 双行 + 空行）。

    【功能/流程定位】被 _stream_detect 调用，把 dict 序列化为 SSE 字符串。
    本函数结束后 → 调用方 yield 给 StreamingResponse。
    """
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _stream_detect(users):
    """异步生成器：逐用户 await _process_user（级联 T1/T2/T3），yield SSE 事件。

    【功能/流程定位】
      Detect 打分链路 SSE 版核心。被 detect_users_stream 的 gen() 消费。
      本函数结束后 → 前端收到 event:done，批次结束。

    【思路/代码流程】
      1. yield stage（开始打分）。
      2. 逐用户：空内容→跳过；否则 redirect_stdout 捕获 print→yield log；
         await _process_user → yield score；异常→yield error log + 空 score。
      3. 全部完成 yield done（含完整 results）。
    """
    total = len(users)
    yield _sse("stage", {"stage": "scoring", "msg": f"开始逐用户级联检测，共 {total} 个用户"})

    results = []
    for idx, user in enumerate(users, 1):
        if not user.contentList:
            results.append(UserScoreResult(userId=user.userId, contentList=user.contentList))
            yield _sse("score", {
                "userId": user.userId, "anomalyScore": 0.0,
                "muteAction": "none", "violationCount": 0,
                "index": idx, "total": total, "skipped": True,
                "msg": "无今日内容，跳过",
            })
            continue

        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                result = await _process_user(user)
            captured = buf.getvalue()
        except Exception as e:
            captured = buf.getvalue()
            for line in captured.splitlines():
                if line.strip():
                    yield _sse("log", {"userId": user.userId, "msg": line, "source": "python"})
            yield _sse("log", {
                "userId": user.userId, "msg": f"检测失败: {e}",
                "source": "python", "level": "error",
            })
            results.append(UserScoreResult(userId=user.userId, contentList=user.contentList))
            yield _sse("score", {
                "userId": user.userId, "anomalyScore": 0.0,
                "muteAction": "none", "violationCount": 0,
                "index": idx, "total": total, "error": str(e),
            })
            continue

        for line in captured.splitlines():
            if line.strip():
                yield _sse("log", {"userId": user.userId, "msg": line, "source": "python"})

        results.append(result)
        yield _sse("score", {
            "userId": user.userId,
            "anomalyScore": result.anomalyScore,
            "muteAction": result.muteAction,
            "violationCount": result.violationCount,
            "contentType": result.contentType,
            "violatedRules": result.violatedRules,
            "violatedLaws": result.violatedLaws,
            "index": idx, "total": total,
        })

    yield _sse("done", {
        "results": [r.model_dump() for r in results],
    })


@router.post("/detect-users-stream")
async def detect_users_stream(request: DetectUsersRequest):
    """SSE 流式打分接口。

    【功能/流程定位】
      Detect 打分链路 SSE 版 HTTP 入口。接 DetectUsersRequest，返回 text/event-stream。
      本函数结束后 → 前端按 event 类型渲染进度；业务结果与 /ai/detect-users 一致。

    【思路/代码流程】
      内层 gen() 异步迭代 _stream_detect；顶层异常 yield event:error；
      用 StreamingResponse 推送，media_type=text/event-stream。
    """
    async def gen():
        try:
            async for chunk in _stream_detect(request.users):
                yield chunk
        except Exception as e:
            yield _sse("error", {"msg": str(e)})

    return StreamingResponse(gen(), media_type="text/event-stream")
