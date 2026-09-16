"""ReAct Agent（待你学习用）。

ReAct = Reason + Act（推理 + 行动）：
LLM 先思考要不要调工具 → 要调就调 → 拿到工具结果再思考 → 直到能直接回答用户。

文件说明：
- tools.py   : 自定义工具（agent 能调用的"手"）
- graph.py   : LangGraph 图，定义 agent 节点 / tools 节点 / 循环边
- router.py  : FastAPI 接口 POST /ai/react
"""
