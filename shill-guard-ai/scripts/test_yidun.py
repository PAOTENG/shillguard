"""易盾文本检测单条联调脚本。

用法（在项目根目录）：
    python scripts/test_yidun.py
    python scripts/test_yidun.py "待检测文本"
    set CASCADE_API_MOCK=true && python scripts/test_yidun.py "小婊子"
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agents.moderation.api_moderation.yidun import check_text_yidun


async def main() -> None:
    text = sys.argv[1] if len(sys.argv) > 1 else "测试文本，网易易盾接口联调"
    result = await check_text_yidun(text)
    print(json.dumps({
        "error": result.error,
        "suggestion": result.suggestion,
        "risk_score": result.risk_score,
        "primary_label": result.primary_label,
        "primary_label_name": result.primary_label_name,
        "hit_keywords": result.hit_keywords,
        "latency_ms": round(result.latency_ms, 2),
        "code": result.raw.get("code"),
        "msg": result.raw.get("msg"),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
