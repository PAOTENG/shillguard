"""网易易盾文本检测 API 客户端（级联 T2-api 层，保留供回滚）。

============================================================================
本文件对应总体流程的哪一部分
============================================================================
对应 moderation __init__.py 总体流程编号 ③（被 api_moderation.check_text_api 路由调用）：
  - check_text_yidun() —— 调易盾文本检测 v5，映射为 ModerationApiResult
  - 辅助：_get_client / _gen_signature（官方签名算法）

调用关系：
  - cascade_api_provider=yidun 时启用；当前主力为阿里云，本文件保留回滚。
  - 返回 ModerationApiResult，cascade / api_label_map（YIDUN_LABEL_MAP）消费。

============================================================================
本部分流程与思路
============================================================================
  - POST application/x-www-form-urlencoded（非 JSON），含官方签名。
  - httpx.AsyncClient 模块级复用，timeout 来自 settings。
  - 失败填 error，cascade Fail-open。

【官方文档】
  签名算法: https://support.dun.163.com/documents/588434200783982592
  Python demo: https://gitee.com/netease_yidun/antispam-python-demo

【与 cascade 的衔接】
  check_text_yidun() → ModerationApiResult.risk_score
  cascade 用 settings.cascade_api_block_threshold 判 clear_violation
"""
import hashlib
import random
import time
import uuid

import httpx

from app.config import settings
from .base import ModerationApiResult

# 模块级复用 AsyncClient，避免每条内容新建 TCP 连接
_CLIENT: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    """懒加载 httpx 异步客户端，timeout 来自 settings.cascade_api_timeout_ms。"""
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = httpx.AsyncClient(
            timeout=settings.cascade_api_timeout_ms / 1000
        )
    return _CLIENT


def _gen_signature(params: dict, secret_key: str) -> str:
    """【易盾官方签名算法】

    步骤:
      1. 除 signature 外所有参数按 key 的 ASCII 排序
      2. 拼接 key + value（无分隔符）
      3. 末尾追加 secretKey
      4. MD5 十六进制小写

    参数:
        params: 待签名的请求参数字典
        secret_key: 易盾控制台 secretKey
    """
    buff = ""
    for k in sorted(params.keys()):
        if k == "signature":
            continue
        buff += str(k) + str(params[k])
    buff += secret_key
    return hashlib.md5(buff.encode("utf-8")).hexdigest()


def _map_suggestion_to_score(suggestion: int, risk_level: int | None = None) -> float:
    """把易盾离散结果映射为 0~1 连续 risk_score（【项目自定义】）。

    易盾 suggestion 字段（官方）:
      0 = 通过  → base 0.05
      1 = 嫌疑  → base 0.55，可按 suggestionRiskLevel 微调
      2 = 不通过 → base 0.92

    suggestionRiskLevel (v5.3 可选): 0无 1低 2中 3高
    """
    if suggestion == 2:
        base = 0.92
    elif suggestion == 1:
        base = 0.55
    else:
        base = 0.05

    if risk_level is not None and suggestion == 1:
        adjust = {0: 0.0, 1: 0.05, 2: 0.10, 3: 0.15}
        base += adjust.get(risk_level, 0.0)

    return min(base, 1.0)


def _parse_yidun_response(data: dict) -> ModerationApiResult:
    """解析易盾 HTTP 响应 JSON → ModerationApiResult。

    业务成功: code == 200，否则 ModerationApiResult.error 非空。
    标签结构: result.antispam.labels[].label / subLabels / details.hitInfos
    """
    code = data.get("code")
    if code != 200:
        return ModerationApiResult(
            provider="yidun",
            error=f"yidun code={code}, msg={data.get('msg')}",
            raw=data,
        )

    antispam = (data.get("result") or {}).get("antispam") or {}
    suggestion_num = int(antispam.get("suggestion", 0))
    risk_level = antispam.get("suggestionRiskLevel")

    suggestion_str = {0: "pass", 1: "review", 2: "block"}.get(suggestion_num, "review")
    score = _map_suggestion_to_score(suggestion_num, risk_level)

    labels = antispam.get("labels") or []
    primary_label = "normal"
    sub_labels: list[str] = []
    hit_keywords: list[str] = []

    if labels:
        first = labels[0]
        primary_label = str(first.get("label", "900"))
        for lb in labels:
            for sub in lb.get("subLabels") or []:
                if not isinstance(sub, dict):
                    continue
                sl = sub.get("subLabel") or sub.get("secondLabel")
                if sl:
                    sub_labels.append(str(sl))
                details = sub.get("details") or {}
                for info in details.get("hitInfos", []) or []:
                    if isinstance(info, dict):
                        word = info.get("value") or info.get("hint")
                        if word:
                            hit_keywords.append(str(word))
                    elif isinstance(info, str):
                        hit_keywords.append(info)
            sub = lb.get("subLabel")
            if sub:
                sub_labels.append(str(sub))
            details = lb.get("details") or {}
            for info in details.get("hitInfos", []) or []:
                if isinstance(info, dict):
                    word = info.get("value") or info.get("hint")
                    if word:
                        hit_keywords.append(str(word))
                elif isinstance(info, str):
                    hit_keywords.append(info)

    risk_desc = antispam.get("riskDescription") or antispam.get("riskdescription") or ""

    return ModerationApiResult(
        provider="yidun",
        suggestion=suggestion_str,
        risk_score=score,
        primary_label=primary_label,
        primary_label_name=risk_desc,
        sub_labels=sub_labels,
        hit_keywords=hit_keywords,
        raw=data,
    )


def _mock_yidun(text: str) -> ModerationApiResult:
    """本地 mock（settings.cascade_api_mock=True 或评测无配额时用）。

    规则与 loadtest/golden_set.json 部分用例对齐，保证 CI 可重复。
    """
    if "小婊子" in text or "去死" in text:
        return ModerationApiResult(
            provider="yidun", suggestion="block", risk_score=0.92,
            primary_label="600", sub_labels=["辱骂"],
        )
    if "很有意思" in text and "捉摸不透" in text:
        return ModerationApiResult(
            provider="yidun", suggestion="review", risk_score=0.55,
            primary_label="600",
        )
    return ModerationApiResult(
        provider="yidun", suggestion="pass", risk_score=0.05,
        primary_label="normal",
    )


async def check_text_yidun(text: str) -> ModerationApiResult:
    """调用易盾 v5 文本检测 API（单条文本）。

    【官方】POST settings.yidun_api_url，Content-Type: application/x-www-form-urlencoded
    【fail-open】异常时返回 error 非空 + suggestion=review，cascade 继续后续层级
    """
    t0 = time.perf_counter()

    if settings.cascade_api_mock:
        result = _mock_yidun(text)
        result.latency_ms = (time.perf_counter() - t0) * 1000
        return result

    if not (settings.yidun_secret_id and settings.yidun_secret_key and settings.yidun_business_id):
        return ModerationApiResult(
            provider="yidun",
            error="yidun credentials missing",
            latency_ms=(time.perf_counter() - t0) * 1000,
        )

    params = {
        "secretId": settings.yidun_secret_id,
        "businessId": settings.yidun_business_id,
        "version": settings.yidun_api_version,
        "timestamp": int(time.time() * 1000),   # 毫秒时间戳
        "nonce": random.randint(100000000, 999999999),
        "dataId": str(uuid.uuid4()),            # 幂等追踪 ID
        "content": text,
    }
    params["signature"] = _gen_signature(params, settings.yidun_secret_key)

    try:
        client = _get_client()
        resp = await client.post(
            settings.yidun_api_url,
            data=params,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        data = resp.json()
        result = _parse_yidun_response(data)
    except Exception as e:
        result = ModerationApiResult(
            provider="yidun",
            error=str(e),
            suggestion="review",
            risk_score=0.5,
        )

    result.latency_ms = (time.perf_counter() - t0) * 1000
    return result
