"""易盾 401 诊断：对比 v5.2/v5.3，打印脱敏配置与排查清单。"""
import asyncio
import hashlib
import json
import random
import sys
import time
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings


def _mask(s: str, show: int = 4) -> str:
    if not s:
        return "(空)"
    if len(s) <= show * 2:
        return s[:2] + "***"
    return s[:show] + "..." + s[-show:]


def _sign(params: dict, secret_key: str) -> str:
    buff = ""
    for k in sorted(params.keys()):
        if k == "signature":
            continue
        buff += str(k) + str(params[k])
    buff += secret_key
    return hashlib.md5(buff.encode("utf-8")).hexdigest()


async def _probe(version: str) -> dict:
    sid = settings.yidun_secret_id.strip()
    sk = settings.yidun_secret_key.strip()
    bid = settings.yidun_business_id.strip()
    params = {
        "secretId": sid,
        "businessId": bid,
        "version": version,
        "timestamp": int(time.time() * 1000),
        "nonce": random.randint(100000000, 999999999),
        "dataId": str(uuid.uuid4()),
        "content": "易盾联调诊断",
    }
    params["signature"] = _sign(params, sk)
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(settings.yidun_api_url, data=params)
        return resp.json()


async def main() -> None:
    print("=== 易盾配置（脱敏）===")
    print(f"  secretId   : {_mask(settings.yidun_secret_id)} (len={len(settings.yidun_secret_id)})")
    print(f"  secretKey  : {_mask(settings.yidun_secret_key)} (len={len(settings.yidun_secret_key)})")
    print(f"  businessId : {_mask(settings.yidun_business_id)} (len={len(settings.yidun_business_id)})")
    print(f"  api_url    : {settings.yidun_api_url}")
    print(f"  version    : {settings.yidun_api_version}")
    print()

    for ver in ("v5.2", "v5.3", settings.yidun_api_version):
        if ver != settings.yidun_api_version and ver in ("v5.2", "v5.3"):
            pass
        try:
            data = await _probe(ver)
            print(f"[{ver}] code={data.get('code')} msg={data.get('msg')}")
        except Exception as e:
            print(f"[{ver}] 请求异常: {e}")

    print()
    print("=== 401 排查清单（官方文档）===")
    print("1. 控制台 → 服务管理 → 文本检测 → 业务列表 → 复制「业务ID」(不是产品ID)")
    print("2. 控制台 → 查看产品密钥 → secretId/secretKey 必须与该产品一致")
    print("3. 试用是否已开通且未过期（7天试用，到期需联系商务）")
    print("4. 业务是否已上线（未上线可能 402，但密钥错也会 401）")
    print("5. 签名错误返回 410 而非 401 —— 当前 401 说明密钥/业务/试用问题，非代码签名 bug")


if __name__ == "__main__":
    asyncio.run(main())
