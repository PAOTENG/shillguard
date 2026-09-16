"""CRAG 检索质量过滤器（Corrective Retrieval Augmented Generation）

在 retrieve_node 和 judge_node 之间运行：对每个检索到的 chunk 用轻量 LLM 打分，
过滤低质量 chunk，避免 judge LLM 基于不相关法条产生幻觉。

【CRAG 三档分类（论文标准）】
  Correct   (score >= 0.7)：明确涉及该类违规的法律条款/处罚规定，直接使用
  Ambiguous (0.4 <= score < 0.7)：间接相关或背景知识，降权保留
  Incorrect (score < 0.4)：与违规类型无关，丢弃

【设计原则】
  - 复用 get_expander_llm()（便宜小模型），一次 LLM 调用批量处理全部 chunk
  - 若所有 chunk 均被判 Incorrect，保留分数最高的前 3 条（防止上下文全空）
  - 容错：LLM 调用失败或 JSON 解析失败时，直接返回原始 chunks 不拦截

【参考】Corrective RAG, Yan et al., 2024. arXiv:2401.15884
"""
import json
import re

from langchain_core.messages import HumanMessage

from app.llm import get_expander_llm


_GRADER_PROMPT = """你是法律检索质量评估专家。评估以下法律/规则文本片段对于判定"用户内容是否违规"的有效性。

## 被审核的用户内容
{content}

## 违规类型初判
{content_type}

## 检索到的法律片段列表（共 {n} 条）
{chunks_text}

## 评分标准
对每个片段打分（0.0 ~ 1.0），仅根据该片段对本次违规判定的直接价值评分：
- 0.8 ~ 1.0：高度相关，明确涉及该类违规的法律条款、罪名定义或处罚规定
- 0.5 ~ 0.7：部分相关，间接涉及、背景条文或上位法原则
- 0.0 ~ 0.4：不相关，内容与该类违规判定无实质关联

## 输出要求
输出 JSON，scores 列表长度必须与片段数量严格一致：
{{"scores": [分数1, 分数2, ...]}}

注意：只输出 JSON，不要任何解释。"""


# 评分阈值（对应 CRAG 论文三档）
_CORRECT_THRESHOLD = 0.7
_AMBIGUOUS_THRESHOLD = 0.4
# Ambiguous 保留但权重降低，用于排在 Correct 之后
_AMBIGUOUS_PENALTY = 0.15   # 从 Ambiguous chunk 的分数中扣减，使其排在 Correct 后面


async def score_chunks(
    chunks: list[str],
    content_text: str,
    content_type: str,
) -> list[float]:
    """用轻量 LLM 对每个 chunk 打分，返回 0.0~1.0 的分数列表。

    容错：任何异常均返回全 1.0（不过滤，降级为原始 RAG 行为）。
    """
    if not chunks:
        return []

    # 构造片段列表文本，加编号方便 LLM 对应
    chunks_text = "\n\n".join(
        f"[{i+1}] {chunk[:300]}"   # 截断单个 chunk，避免 prompt 过长
        for i, chunk in enumerate(chunks)
    )

    prompt = _GRADER_PROMPT.format(
        content=content_text[:200],
        content_type=content_type,
        n=len(chunks),
        chunks_text=chunks_text,
    )

    try:
        llm = get_expander_llm()
        resp = await llm.ainvoke([HumanMessage(content=prompt)])
        raw = resp.content.strip()

        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if not m:
            return [1.0] * len(chunks)

        data = json.loads(m.group(0))
        scores = data.get("scores", [])

        # 长度校验：若 LLM 输出数量不对，退化为不过滤
        if len(scores) != len(chunks):
            return [1.0] * len(chunks)

        # 确保全是 float 且在 [0, 1]
        return [max(0.0, min(1.0, float(s))) for s in scores]

    except Exception as e:
        print(f"[CRAG] 打分调用失败（退化为不过滤）: {e}")
        return [1.0] * len(chunks)


def filter_chunks_by_score(
    chunks: list[str],
    scores: list[float],
) -> tuple[list[str], dict]:
    """根据分数过滤 chunk，返回（过滤后 chunk 列表, 统计信息）。

    CRAG 三档：
      Correct   (>= 0.7)：直接保留，排在最前
      Ambiguous (0.4 ~ 0.7)：保留但排在 Correct 之后
      Incorrect (< 0.4)：丢弃

    兜底：若全部 Incorrect，保留分数最高的前 3 条（避免 judge 收到空上下文）。
    """
    if not chunks or not scores:
        return chunks, {"correct": 0, "ambiguous": 0, "incorrect": 0, "fallback": False}

    correct, ambiguous, incorrect = [], [], []
    for chunk, score in zip(chunks, scores):
        if score >= _CORRECT_THRESHOLD:
            correct.append((chunk, score))
        elif score >= _AMBIGUOUS_THRESHOLD:
            ambiguous.append((chunk, score))
        else:
            incorrect.append((chunk, score))

    stats = {
        "correct": len(correct),
        "ambiguous": len(ambiguous),
        "incorrect": len(incorrect),
        "fallback": False,
    }

    # 按分数降序排列各档
    correct.sort(key=lambda x: -x[1])
    ambiguous.sort(key=lambda x: -x[1])
    incorrect.sort(key=lambda x: -x[1])

    filtered = [c for c, _ in correct] + [c for c, _ in ambiguous]

    # 兜底：全部被丢弃时，取分数最高的前 3 条
    if not filtered:
        stats["fallback"] = True
        all_sorted = sorted(zip(chunks, scores), key=lambda x: -x[1])
        filtered = [c for c, _ in all_sorted[:3]]
        print(
            f"[CRAG] 全部 {len(incorrect)} 个 chunk 低于阈值，"
            f"启用兜底，保留最高分前 3 条"
        )

    return filtered, stats


async def crag_filter(
    chunks: list[str],
    content_text: str,
    content_type: str,
) -> tuple[list[str], dict]:
    """CRAG 主入口：打分 + 过滤，返回（过滤后的 chunk 列表, 统计 dict）。

    统计 dict 结构：
        {
            "correct": int,      # Correct 档数量
            "ambiguous": int,    # Ambiguous 档数量
            "incorrect": int,    # Incorrect 档（已丢弃）数量
            "fallback": bool,    # 是否触发兜底逻辑
            "before": int,       # 过滤前 chunk 数
            "after": int,        # 过滤后 chunk 数
        }
    """
    scores = await score_chunks(chunks, content_text, content_type)
    filtered, stats = filter_chunks_by_score(chunks, scores)

    stats["before"] = len(chunks)
    stats["after"] = len(filtered)

    print(
        f"[CRAG] 过滤: {stats['before']} → {stats['after']} chunks  "
        f"(correct={stats['correct']}, ambiguous={stats['ambiguous']}, "
        f"incorrect={stats['incorrect']}, fallback={stats['fallback']})"
    )

    return filtered, stats
