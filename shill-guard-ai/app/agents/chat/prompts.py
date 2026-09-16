"""对话 Agent 的系统提示词构建（Main LLM 的 prompt 组装）。

============================================================================
本文件对应总体流程的哪一部分
============================================================================
对应 __init__.py 总体流程编号 ⑩（被 ⑦ chat_node 调用）：
  - SYSTEM_PROMPT        —— Main LLM 的固定回答规范（角色 + 9 条规则）
  - build_system_prompt()—— 组装最终 system prompt（规范 + 北京时间 + 背景结论 + 上传文档）

调用关系：graph.py::chat_node 调用 build_system_prompt() 拿到完整 system prompt，
拼到消息序列首位后发给 Main LLM。本文件是 prompt 工厂，无独立运行入口。

============================================================================
【架构隔离后的 Prompt 设计】
  chat_node (Main LLM) 只接收两个数据字段：
    - processed_context：Worker LLM 提炼的简洁背景结论（1-3句话）
    - doc_context：用户主动上传的文档（用户行为，可直接注入）

  原始字段（memories / summary / rag_context）由 context_processor_node 消费，
  不再出现在 Main LLM 的 system prompt 里。这样 Main LLM 物理上无法复读原文。

【回答规范写在最前】
  称呼规则、简洁要求、格式规则放在 SYSTEM_PROMPT 顶部，
  正向约束（"只输出X"）比负向约束（"不要输出X"）更可靠。
"""
# datetime/timezone/timedelta：构造北京时间（UTC+8）并格式化当前时间
from datetime import datetime, timezone, timedelta

# SYSTEM_PROMPT：Main LLM 的固定角色与回答规范（每次请求都注入，写死不变）。
# 设计要点：规则放最前；正向约束优先；代码必须用 Markdown 代码块。
SYSTEM_PROMPT = (
    "你是 ShillGuard 平台的 AI 助手，具备通用知识，也了解 ShillGuard 平台的功能。\n"
    "\n"
    "【回答规范 - 每次必须遵守】\n"
    "1. 称呼用户时一律用'你'，不要在称呼中嵌入名字（如禁止说'李四你好'）；"
    "但若用户询问自己的姓名、年龄等个人信息，直接用[相关背景]里的事实回答。\n"
    "2. 回答简洁直接，通常 1-3 句话足够；用户明确要求详细解释时才展开。\n"
    "3. 你的回答只包含对用户问题的直接答案。\n"
    "4. 不要在回答开头罗列或重复[相关背景]的原文；但可以利用背景中的事实直接回答用户的问题。\n"
    "5. 禁止在回答开头输出要点列表（•/-/*）；直接给出结论。\n"
    "6. 只回答用户当前问题，不要把其他话题的信息混进本次回答。\n"
    "7. 涉及 ShillGuard 平台功能时，可参考[相关背景]作答，但只输出结论。\n"
    "8. 与平台无关的问题正常回答，不要拒绝。\n"
    "9. 回答中包含代码时，必须使用 Markdown 代码块格式并标注语言，例如：\n"
    "   ```python\n"
    "   # 代码内容\n"
    "   ```\n"
    "   禁止将代码嵌入普通段落文字中。\n"
)


def build_system_prompt(
    processed_context: str = "",
    doc_context: str = "",
) -> str:
    """组装完整的 system prompt（架构隔离版）。

    【功能 / 流程定位】
      总体流程 ⑩，被 graph.py::chat_node 调用。
      本函数结束后，调用方 chat_node 把返回字符串作为 SystemMessage 拼到消息序列首位。

    【思路 / 代码流程】
      1. 取 SYSTEM_PROMPT 固定规范作为基底
      2. 注入当前北京时间（供"今天/最新"类时间问题判断）
      3. 注入 processed_context（Worker 提炼的单句背景，标注"仅供参考勿重复"）
      4. 注入 doc_context（用户上传文档，可直接引用）
      架构隔离核心：此处只注入 processed_context/doc_context，绝不注入原始
      memories/summary/rag，从 prompt 源头杜绝 Main LLM 复读原文。

    参数:
        processed_context: context_processor_node 提炼的简洁背景结论
                           例："用户在用FastAPI+PostgreSQL开发ShillGuard内容审核平台"
                           Main LLM 只看这一句，永远不看原始 memories/summary/RAG
        doc_context:       用户上传文档文本（用户主动上传，可直接引用）

    返回:
        注入上下文后的 system prompt 字符串
    """
    # 构造北京时间时区（UTC+8）
    BJ = timezone(timedelta(hours=8))
    # 取当前北京时间并格式化为 "YYYY年MM月DD日 HH:MM"
    now_str = datetime.now(BJ).strftime("%Y年%m月%d日 %H:%M")

    # 以固定规范为基底
    prompt = SYSTEM_PROMPT
    # 注入当前时间：让 LLM 回答"今天/最新"类问题时以此时为准
    prompt += f"\n当前北京时间：{now_str}。涉及'今天'、'最新'等时间问题请以此为准。\n"

    # Worker LLM 提炼的背景结论（简洁，不含原始数据）
    # 注意：此处内容仅供 LLM 内部参考，不得出现在回答中
    if processed_context:
        # 标注"仅供参考，不要在回答中重复此内容"，再次提醒勿复读
        prompt += (
            f"\n[相关背景 - 仅供参考，不要在回答中重复此内容]\n"
            f"{processed_context}\n"
        )

    # 用户上传文档（用户主动行为，可直接使用）
    if doc_context:
        # doc_context 是用户主动上传，可直接引用，无需隔离
        prompt += f"\n[用户上传文档]\n{doc_context}\n"

    # 返回完整 system prompt
    return prompt
