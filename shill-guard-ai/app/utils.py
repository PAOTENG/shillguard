"""项目公共工具函数。

提取自各 Agent 中重复的辅助逻辑，供全项目统一使用。
"""
import json
import re


def parse_json_from_llm(text: str) -> dict:
    """从 LLM 自由文本输出中提取 JSON 字典。

    解析策略（按优先级）：
      1. 提取 ```json ... ``` 代码块内容
      2. 提取第一个 { 到最后一个 } 之间的内容
      3. json.loads 失败则返回 {}，下游 .get(key, default) 有兜底

    被以下模块使用：
      - app/agents/moderation/graph.py
      - app/agents/moderation/detect_router.py
      - app/agents/detect/graph.py
    """
    match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
    if match:
        text = match.group(1)
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        text = match.group(0)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}
