"""阿里云内容安全文本审核 API 客户端（级联 T2-api 层，主力厂商）。

============================================================================
本文件对应总体流程的哪一部分
============================================================================
对应 moderation __init__.py 总体流程编号 ③（被 api_moderation.check_text_api 路由调用）：
  - check_text_aliyun() —— 调阿里云 TextModeration/Plus，映射为 ModerationApiResult
  - 辅助：_get_client / _map_risk_level_to_score / 标准与 PLUS 服务分流

调用关系：
  - cascade_api_provider=aliyun 时，check_text_api → 本文件；
  - 返回 ModerationApiResult 供 cascade 阈值比较与 api_templated_evidence。

============================================================================
本部分流程与思路
============================================================================
  - SDK 同步库用 asyncio.to_thread 包裹，避免堵 FastAPI 事件循环。
  - Client 模块级懒加载复用连接。
  - riskLevel(none/low/medium/high) + labels 置信度 → 0~1 risk_score（项目自定义映射）。
  - 失败填 error 字段，cascade Fail-open。

【官方文档】
  SDK 接入指南: https://help.aliyun.com/zh/document_detail/2933065.html
  TextModeration 通用服务 / TextModerationPlus PLUS 服务

【两套 API 的区别】
  标准服务（TextModeration）：comment_detection 等（无 _pro 后缀）
  PLUS 服务（TextModerationPlus）：comment_detection_pro 等（带 _pro）
  两套 Service 参数不互通，传错会返回 400 service is invalid。

【与 cascade 的衔接】
  check_text_aliyun() → ModerationApiResult.risk_score
  cascade 用 settings.cascade_api_block_threshold 判 clear_violation
"""
import asyncio
import json
import time
import uuid

from alibabacloud_green20220302.client import Client
from alibabacloud_green20220302 import models
from alibabacloud_tea_openapi.models import Config
from alibabacloud_tea_util import models as util_models

from app.config import settings
from .base import ModerationApiResult

# 模块级复用 Client（官方建议避免重复建连，提升检测性能）
_CLIENT: Client | None = None

# 需要走 TextModerationPlus 接口的服务集合（官方文档定义）
_PLUS_SERVICES: frozenset[str] = frozenset({
    "nickname_detection_pro",
    "chat_detection_pro",
    "comment_detection_pro",
    "ad_compliance_detection_pro",
    "comment_multilingual_pro_cb",
    "comment_multilingual_pro",
    "llm_query_moderation",
    "llm_response_moderation",
    "text_aigc_detector",
    "ugc_moderation_byllm_pro",
    "ugc_moderation_byllm",
    "ugc_moderation_byllm_cb",
    "aigc_moderation_byllm",
})


def _get_client() -> Client:
    """懒加载 SDK Client，复用连接。"""
    global _CLIENT
    if _CLIENT is None:
        config = Config(
            access_key_id=settings.aliyun_access_key_id,
            access_key_secret=settings.aliyun_access_key_secret,
            region_id=settings.aliyun_green_region,
            endpoint=settings.aliyun_green_endpoint,
            connect_timeout=settings.cascade_api_timeout_ms,
            read_timeout=settings.cascade_api_timeout_ms,
        )
        _CLIENT = Client(config)
    return _CLIENT


def _map_risk_level_to_score(risk_level: str, labels_str: str) -> float:
    """阿里云 riskLevel + labels 置信度 → 0~1 连续分（项目自定义映射）。

    riskLevel: none | low | medium | high
    labels_str 示例: "profanity:80,cyberbullying:60"
    """
    level_base = {
        "high":   0.92,
        "medium": 0.65,
        "low":    0.40,
        "none":   0.05,
    }
    base = level_base.get((risk_level or "none").lower(), 0.50)

    # 若 labels 带置信度，取最高值微调，使分数更精确
    if labels_str:
        for part in labels_str.split(","):
            part = part.strip()
            if ":" in part:
                try:
                    conf = float(part.split(":")[1])
                    if conf >= 90:
                        base = max(base, 0.92)
                    elif conf >= 70:
                        base = max(base, 0.75)
                    elif conf >= 50:
                        base = max(base, 0.55)
                except (ValueError, IndexError):
                    pass

    return min(base, 1.0)


def _parse_aliyun_response(body) -> ModerationApiResult:
    """解析 TextModeration SDK 响应 body → ModerationApiResult。

    响应结构:
      body.code       - 业务码，200 = 成功
      body.data.riskLevel  - "none" | "low" | "medium" | "high"
      body.data.labels     - 逗号分隔标签字符串，如 "profanity:80,cyberbullying:60"
      body.data.reason     - 命中说明文字
    """
    code = getattr(body, "code", None)
    if code != 200:
        msg = getattr(body, "msg", "") or getattr(body, "message", "")
        return ModerationApiResult(
            provider="aliyun",
            error=f"aliyun code={code}, msg={msg}",
            raw={"code": code, "msg": msg},
        )

    data = getattr(body, "data", None)
    if data is None:
        return ModerationApiResult(
            provider="aliyun",
            error="aliyun: response data is empty",
            raw={"code": code},
        )

    # 兼容 SDK 可能用 snake_case 或 camelCase
    risk_level: str = (
        getattr(data, "risk_level", None)
        or getattr(data, "riskLevel", None)
        or "none"
    )
    labels_str: str = str(getattr(data, "labels", None) or "")
    reason: str = str(getattr(data, "reason", None) or "")

    score = _map_risk_level_to_score(risk_level, labels_str)

    if score >= 0.85:
        suggestion = "block"
    elif score <= 0.15:
        suggestion = "pass"
    else:
        suggestion = "review"

    # 解析 labels：取第一个作为 primary_label，其余作为 sub_labels
    primary_label = "normal"
    sub_labels: list[str] = []
    if labels_str:
        parts = [p.split(":")[0].strip() for p in labels_str.split(",") if p.strip()]
        if parts:
            primary_label = parts[0]
            sub_labels = parts[1:]

    hit_keywords: list[str] = [reason] if reason else []

    return ModerationApiResult(
        provider="aliyun",
        suggestion=suggestion,
        risk_score=score,
        primary_label=primary_label,
        primary_label_name=reason or primary_label,
        sub_labels=sub_labels,
        hit_keywords=hit_keywords,
        raw={
            "code": code,
            "riskLevel": risk_level,
            "labels": labels_str,
            "reason": reason,
        },
    )


def _mock_aliyun(text: str) -> ModerationApiResult:
    """本地 mock（CASCADE_API_MOCK=true 时用，不消耗 API 配额）。

    规则与 loadtest/golden_set.json 部分用例对齐，保证 CI 可重复。
    """
    if "小婊子" in text or "去死" in text:
        return ModerationApiResult(
            provider="aliyun", suggestion="block", risk_score=0.92,
            primary_label="profanity", primary_label_name="辱骂内容",
        )
    if "很有意思" in text and "捉摸不透" in text:
        return ModerationApiResult(
            provider="aliyun", suggestion="review", risk_score=0.55,
            primary_label="cyberbullying",
        )
    return ModerationApiResult(
        provider="aliyun", suggestion="pass", risk_score=0.05,
        primary_label="normal",
    )


async def check_text_aliyun(text: str) -> ModerationApiResult:
    """调用阿里云 TextModeration API（单条文本）。

    【功能/流程定位】
      对应总体流程 ③ 的 T2 API（主力厂商）。被 check_text_api 路由调用。
      本函数结束后 → 返回 ModerationApiResult 供 cascade 阈值比较。

    【思路】mock 开关→假结果；无 AK→error；否则 to_thread 调 SDK，
    riskLevel+labels→risk_score，填 ModerationApiResult。

    【fail-open】异常时返回 error 非空 + suggestion=review，
    cascade 不拦截，继续白名单/加权/T3-LLM 层级。
    """
    t0 = time.perf_counter()

    if settings.cascade_api_mock:
        result = _mock_aliyun(text)
        result.latency_ms = (time.perf_counter() - t0) * 1000
        return result

    if not settings.aliyun_access_key_id or not settings.aliyun_access_key_secret:
        return ModerationApiResult(
            provider="aliyun",
            error="aliyun credentials missing（检查 ALIYUN_ACCESS_KEY_ID / SECRET）",
            latency_ms=(time.perf_counter() - t0) * 1000,
        )

    service_params = json.dumps(
        {"content": text, "dataId": str(uuid.uuid4())},
        ensure_ascii=False,
    )
    runtime = util_models.RuntimeOptions(
        read_timeout=settings.cascade_api_timeout_ms,
        connect_timeout=settings.cascade_api_timeout_ms,
    )
    use_plus = settings.aliyun_green_service in _PLUS_SERVICES

    try:
        client = _get_client()

        def _call(c: Client) -> object:
            """同步调用，区分 PLUS / 标准 API。"""
            if use_plus:
                req = models.TextModerationPlusRequest(
                    service=settings.aliyun_green_service,
                    service_parameters=service_params,
                )
                return c.text_moderation_plus_with_options(req, runtime)
            else:
                req = models.TextModerationRequest(
                    service=settings.aliyun_green_service,
                    service_parameters=service_params,
                )
                return c.text_moderation_with_options(req, runtime)

        # SDK 是同步库，在线程池中执行，避免阻塞 FastAPI 事件循环
        response = await asyncio.to_thread(_call, client)

        # 官方建议：HTTP 500 时切换北京节点重试一次
        body_code = getattr(getattr(response, "body", None), "code", 0)
        if response.status_code == 500 or body_code == 500:
            beijing_config = Config(
                access_key_id=settings.aliyun_access_key_id,
                access_key_secret=settings.aliyun_access_key_secret,
                region_id="cn-beijing",
                endpoint="green-cip.cn-beijing.aliyuncs.com",
                connect_timeout=settings.cascade_api_timeout_ms,
                read_timeout=settings.cascade_api_timeout_ms,
            )
            backup_client = Client(beijing_config)
            response = await asyncio.to_thread(_call, backup_client)

        if response.status_code != 200 or not response.body:
            result = ModerationApiResult(
                provider="aliyun",
                error=f"http status={response.status_code}",
                suggestion="review",
                risk_score=0.5,
            )
        else:
            result = _parse_aliyun_response(response.body)

    except Exception as e:
        result = ModerationApiResult(
            provider="aliyun",
            error=str(e),
            suggestion="review",
            risk_score=0.5,
        )

    result.latency_ms = (time.perf_counter() - t0) * 1000
    return result
