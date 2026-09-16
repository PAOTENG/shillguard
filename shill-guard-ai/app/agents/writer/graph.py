"""续写 Agent 的 LangGraph 图（最简 Agent 模板）。

【用途】帮用户续写帖子内容，只有一个 LLM 节点。

【学习价值】
  这是项目里最简单的 LangGraph 示例，写新 Agent 时可以先复制此文件改：
    1. WriteState → 你的 State
    2. write_node → 你的节点逻辑
    3. build_graph → 加更多节点和边

【官方概念】
  Annotated[list[BaseMessage], add_messages] — 消息 reducer，新消息追加不覆盖
  StateGraph → add_node → set_entry_point → add_edge → compile
"""
from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages

from app.llm import get_llm
from app.agents.writer.prompts import SYSTEM_PROMPT


class WriteState(TypedDict):
    """续写图状态：只有 messages 一个字段。"""
    messages: Annotated[list[BaseMessage], add_messages]


def write_node(state: WriteState) -> dict:
    """唯一节点：把 messages 喂给 LLM，返回 AI 续写结果。"""
    llm = get_llm()
    msgs = state["messages"]
    # 若第一条不是 SystemMessage，补一条角色设定
    if not msgs or not isinstance(msgs[0], SystemMessage):
        msgs = [SystemMessage(content=SYSTEM_PROMPT)] + list(msgs)
    response = llm.invoke(msgs)
    return {"messages": [response]}  # add_messages reducer 会追加 AIMessage


def build_graph():
    """最简图：write → END（无分支、无记忆）。"""
    g = StateGraph(WriteState)
    g.add_node("write", write_node)
    g.set_entry_point("write")
    g.add_edge("write", END)
    return g.compile()
