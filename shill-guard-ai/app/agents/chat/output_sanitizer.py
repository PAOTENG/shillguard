"""对话 Agent 输出清洗工具（备用防御层）。

============================================================================
本文件对应总体流程的哪一部分
============================================================================
当前定位：**备用兜底，已不再主动调用**。
架构隔离（context_processor_node）上线后，Main LLM 物理上看不到原始背景，
不会复读 bullet，因此 graph.py 已移除 strip_leading_context_echo 的调用。
本文件保留作为历史记录与最后一道 regex 防线：若未来 Worker 失效导致复读复现，
可临时在 chat_node 内重新启用本函数做事后清洗。

设计原意（历史背景）：
  防止 Main LLM 在回答开头复读背景要点（bullet 列表），
  避免污染 PostgreSQL 历史，进而污染 mem0 / 摘要 / 后续检索。
  但事后 regex 清洗有"流式已发出 vs 存储被改"的不一致缺陷，故被架构隔离取代。

============================================================================
调用关系：当前无调用方（备用）。如需启用，在 graph.py::chat_node 拿到
result.content 后调用 strip_leading_context_echo(result.content)。
"""
# re：正则匹配开头的 bullet 行（•/-/* / 序号 / "用户"/"助手" 开头）
import re


# _BULLET_LINE：识别"复读背景"特征行的正则。
# ^[\s•\-\*]     —— 开头是空白/•/-/* （bullet 符号）
# |\d+[\.\、]    —— 或 开头是 数字./数字、 （序号）
# |^用户         —— 或 以 "用户" 开头（复读"用户：xxx"格式）
# |^助手         —— 或 以 "助手" 开头（复读"助手：xxx"格式）
_BULLET_LINE = re.compile(
    r"^[\s•\-\*]"
    r"|\d+[\.\、]"
    r"|^用户"
    r"|^助手"
)


def strip_leading_context_echo(text: str) -> str:
    """去掉回答开头连续的要点列表行，保留真正的直接回答。

    【功能 / 流程定位】
      备用防御函数（当前未被主动调用）。如启用，应在 chat_node 生成回答后调用，
      清洗后再写入 chat_messages / mem0。本函数结束后返回清洗后文本给调用方。
      无"下一个函数"——这是文本清洗的终点。

    【思路 / 代码流程】
      1. 按行切分
      2. 从头扫描：空行 / 匹配 _BULLET_LINE 的行视为"复读前导"跳过
      3. 遇到第一行真正回答即停止
      4. 切掉前导行后拼接；若清洗后为空则回退原文（避免吞掉全部内容）

    示例输入：
        • 用户小明，25岁\\n• 青岛今日天气...\\n这我可不知道...

    示例输出：
        这我可不知道...

    参数:
        text: LLM 原始回答

    返回:
        去掉开头复读行后的回答；清洗后为空则返回原文
    """
    # 空文本或纯空白直接返回，不处理
    if not text or not text.strip():
        return text

    # 按行切分
    lines = text.split("\n")
    # cut：要切掉的前导行数（保留 lines[cut:]）
    cut = 0
    for i, line in enumerate(lines):
        # 当前行 strip 后判断
        s = line.strip()
        # 空行：算作前导，继续往后看（cut = i+1）
        if not s:
            cut = i + 1
            continue
        # 匹配 bullet 特征：算作前导复读行，继续往后看
        if _BULLET_LINE.search(s):
            cut = i + 1
            continue
        # 遇到第一行真正回答 → 停止扫描
        break

    # 切掉前导行并 strip
    cleaned = "\n".join(lines[cut:]).strip()
    # 清洗后非空则返回清洗结果；为空则回退原文（兜底，避免吞光）
    return cleaned if cleaned else text
