"""ReAct Agent 的 LangGraph 图（逐句注释版）。

ReAct 循环结构：
    ┌──→ agent(思考/决定) ──┐
    │        │              │
    │   有tool_calls?       │ 没有就直接结束
    │        ↓ yes           │
    │      tools(执行)       │
    │        │              │
    └────────┘──────────────┘
"""
from typing import Annotated, TypedDict

# BaseMessage：所有消息的基类（Human/AI/Tool/System 消息都继承它）
from langchain_core.messages import BaseMessage, SystemMessage
# add_messages：一个 reducer，作用是"把新消息追加进列表"而不是覆盖
from langgraph.graph.message import add_messages
# StateGraph：状态图本体；END：结束节点
from langgraph.graph import StateGraph, END
# ToolNode：LangGraph 预置的"批量执行工具调用"节点，省得自己写
from langgraph.prebuilt import ToolNode

from app.llm import get_llm
from app.agents.react.tools import calculator, search_web


# ===== 1) 定义状态 =====
# TypedDict 给状态一个明确的类型结构，IDE 有提示、写错字段会报错
class ReactState(TypedDict):
    # messages 字段：存对话历史。Annotated[..., add_messages] 表示
    # "这个字段用 add_messages reducer 合并"——节点返回新消息时会自动追加而非替换
    messages: Annotated[list[BaseMessage], add_messages]


# ===== 2) 收集工具列表 =====
# 把 agent 能调用的工具放一起；后面要 ①绑给 LLM ②交给 ToolNode 执行
tools = [calculator, search_web]

# 系统提示词：定义 agent 的人设和行为准则
SYSTEM_PROMPT = (
    "你是一个会使用工具的助手。遇到计算或需要搜索的问题时调用对应工具，"
    "拿到结果后再回答用户。普通问题直接回答即可。"
)


# ===== 3) agent 节点：让 LLM 决定"直接回答"还是"调工具" =====
def agent_node(state: ReactState) -> dict:
    # 从配置取 LLM（get_llm 内部已缓存，不会每次新建）
    llm = get_llm()
    # bind_tools 把工具清单告诉 LLM，LLM 就能在回复里输出 tool_calls
    llm_with_tools = llm.bind_tools(tools)

    # 取当前消息历史
    messages = state["messages"]
    # 若还没有 system 消息，就补一条在最前面（定调子）
    if not any(isinstance(m, SystemMessage) for m in messages):
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + list(messages)

    # 调 LLM。它可能返回：
    #   - 普通 AIMessage（直接答案）→ 结束
    #   - 带 tool_calls 的 AIMessage（要调工具）→ 跳到 tools 节点
    response = llm_with_tools.invoke(messages)

    # 返回 {"messages": [response]}：靠 add_messages reducer 自动追加
    return {"messages": [response]}


# ===== 4) 路由函数：决定 agent 之后去哪 =====
def should_continue(state: ReactState) -> str:
    # 看最后一条消息（即 agent 刚生成的 AIMessage）
    last_message = state["messages"][-1]
    # 如果它带了 tool_calls（即 LLM 想调工具），就去 "tools" 节点
    if getattr(last_message, "tool_calls", None):
        return "tools"
    # 否则说明 LLM 已经给出最终答案，直接结束
    return END


# ===== 5) 组装图 =====
def build_graph():
    # 创建一个状态图，状态结构用 ReactState
    graph = StateGraph(ReactState)

    # 加节点：节点名 -> 节点函数
    graph.add_node("agent", agent_node)
    # ToolNode 会自动解析 AIMessage 里的 tool_calls，逐个执行对应工具，
    # 把每个结果包成 ToolMessage 返回
    graph.add_node("tools", ToolNode(tools))

    # 入口：从 "agent" 节点开始
    graph.set_entry_point("agent")

    # 条件边：agent 执行完后，用 should_continue 决定下一步去哪
    # 第二个参数是路由函数，第三个参数把函数返回值映射到目标节点
    graph.add_conditional_edges(
        "agent",
        should_continue,
        {"tools": "tools", END: END},
    )

    # 普通边：tools 执行完后，回到 agent 继续推理（这就是 ReAct 的"循环"）
    graph.add_edge("tools", "agent")

    # 编译图：变成可执行的对象（可 invoke / astream / 带checkpointer）
    return graph.compile()
