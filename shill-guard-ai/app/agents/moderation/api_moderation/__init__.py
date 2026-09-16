"""商业 API 统一入口（工厂 + 批量聚合）。

============================================================================
本文件对应总体流程的哪一部分
============================================================================
对应 __init__.py 总体流程编号 ③（被 cascade.py::pre_filter_node 的 T2 API 分支调用）：
  - check_text_api()       —— 按 settings.cascade_api_provider 路由到阿里云/易盾
  - check_text_api_batch() —— 对 content_list 逐条检测，取最高 risk_score（就重不就轻）

调用关系：
  - cascade.py 只依赖本包返回的 ModerationApiResult，不关心底层厂商。
  - 新增厂商：实现 check_text_xxx()，在 check_text_api 加分支即可（Adapter 模式）。

============================================================================
本部分流程与思路
============================================================================
  - 工厂路由：settings.cascade_api_provider 决定走 aliyun 还是 yidun。
  - 批量策略：多条内容分别调 API，取 risk_score 最高的一条（任一违规按最严重处理）；
    全部失败则返回第一个 error 结果，供 cascade Fail-open。

【当前支持的 provider】
  aliyun  阿里云内容安全（TextModeration 增强版，主力）
  yidun   网易易盾（保留，供回滚）
"""

# ── 项目内：配置 + 统一结果 + 各厂商客户端 ──
from app.config import settings                 # cascade_api_provider 路由开关
from .base import ModerationApiResult           # 统一返回结构（Adapter）
from .yidun import check_text_yidun             # 易盾客户端（保留）
from .aliyun import check_text_aliyun           # 阿里云客户端（主力）


async def check_text_api(text: str) -> ModerationApiResult:
    """按 settings.cascade_api_provider 路由到具体厂商客户端。

    【功能/流程定位】
      对应总体流程 ③ 的 T2 API 单条检测。被 check_text_api_batch 或单条路径调用。
      本函数结束后 → 调用方拿到 ModerationApiResult（含 risk_score/label/error）。

    【思路/代码流程】
      provider=aliyun → check_text_aliyun；yidun → check_text_yidun；其他 → ValueError。
      参数：text —— 单条待审文本。
      返回：ModerationApiResult。
    """
    if settings.cascade_api_provider == "aliyun":       # 主力：阿里云内容安全
        return await check_text_aliyun(text)
    if settings.cascade_api_provider == "yidun":        # 保留：易盾回滚路径
        return await check_text_yidun(text)
    raise ValueError(f"unknown cascade_api_provider: {settings.cascade_api_provider}")


async def check_text_api_batch(content_list: list[str]) -> ModerationApiResult:
    """对多条被举报内容分别检测，聚合为单一结果供 cascade 决策。

    【功能/流程定位】
      对应总体流程 ③。被 cascade.py::pre_filter_node 直接调用。
      本函数结束后 → cascade 用 risk_score 与 block/pass 阈值比较定三态。

    【思路/代码流程】
      1. 单条 → 直接 check_text_api，避免多余循环。
      2. 多条 → 逐条 await check_text_api，收集 results。
      3. 过滤掉 error 的；全失败 → 返回第一个（含 error，供 Fail-open）。
      4. 否则 max(valid, key=risk_score) —— 就重不就轻，任一违规按最严重处理。

    单条时直接调用 check_text_api，避免多余循环。
    多条时 max(valid, key=risk_score) — 任一违规即按最严重处理。
    """
    if len(content_list) == 1:                          # 单条短路，少一次循环
        return await check_text_api(content_list[0])

    results = []                                        # 收集每条检测结果
    for text in content_list:
        results.append(await check_text_api(text))      # 串行逐条（厂商限流友好）

    valid = [r for r in results if not r.error]         # 过滤调用失败的
    if not valid:                                       # 全部失败 → 返回第一个 error 结果
        return results[0]
    return max(valid, key=lambda r: r.risk_score)       # 取最高风险分（就重不就轻）
