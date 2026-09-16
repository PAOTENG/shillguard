"""阿里云内容安全文本审核单条联调脚本。

用法（cmd，在项目根目录执行）：
    python scripts\test_aliyun.py
    python scripts\test_aliyun.py "你个傻哔"
    python scripts\test_aliyun.py "今天天气不错"
    set CASCADE_API_MOCK=true && python scripts\test_aliyun.py "小婊子"

说明：
    - 首次运行前请先安装 SDK: pip install alibabacloud_green20220302
    - .env 中需配置 ALIYUN_ACCESS_KEY_ID 和 ALIYUN_ACCESS_KEY_SECRET
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agents.moderation.api_moderation.aliyun import check_text_aliyun


async def main() -> None:
    text = sys.argv[1] if len(sys.argv) > 1 else "测试文本，阿里云内容安全接口联调"
    print(f"[测试文本] {text!r}\n")

    result = await check_text_aliyun(text)

    output = {
        "provider":           result.provider,
        "error":              result.error,
        "suggestion":         result.suggestion,
        "risk_score":         result.risk_score,
        "primary_label":      result.primary_label,
        "primary_label_name": result.primary_label_name,
        "sub_labels":         result.sub_labels,
        "hit_keywords":       result.hit_keywords,
        "latency_ms":         round(result.latency_ms, 2),
        "raw":                result.raw,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))

    # 给出人类可读的结论
    if result.error:
        print(f"\n[结论] [FAIL] 调用失败: {result.error}")
    elif result.suggestion == "block":
        print(f"\n[结论] [BLOCK] 违规（risk_score={result.risk_score:.2f}）-> 触发 T2-api 拦截")
    elif result.suggestion == "pass":
        print(f"\n[结论] [PASS] 正常（risk_score={result.risk_score:.2f}）-> 通过")
    else:
        print(f"\n[结论] [REVIEW] 灰区（risk_score={result.risk_score:.2f}）-> 继续走 T3-LLM 复核")


if __name__ == "__main__":
    asyncio.run(main())
