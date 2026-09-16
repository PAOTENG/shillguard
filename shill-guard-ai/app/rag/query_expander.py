"""Step-Back + Ontology-Guided Query Expander（RAG 三路检索的查询生成器）。

【解决的问题】
  纯 HyDE（让 LLM 生成假设性文档再检索）在中国法律垂直领域容易「漂移」——
  LLM 可能生成不存在的法律名称。本模块用固定本体约束 LLM 输出空间。

【三路查询】（供 moderation/graph.py retrieve_node 使用）
  Q1 — 原文语义：content_list 原文，不依赖 classify，分类错了也能检到法条
  Q2 — 类型模板：_TYPE_QUERY_MAP[content_type]，保留原有精准关键词逻辑
  Q3 — Step-Back：get_expander_llm() 从 law_taxonomy 本体中选 3 条检索词

【参考】arXiv 2505.03970 法律检索 + OG-RAG 本体约束思路
"""
import json
import re

from langchain_core.messages import HumanMessage  # 【官方 LangChain】用户消息类型

from app.llm import get_expander_llm
from app.rag.law_taxonomy import get_domain_hint, get_step_back_query, get_search_terms

# Step-Back prompt：{{...}} 双花括号在 format 后变成单花括号 JSON 示例
_STEP_BACK_PROMPT = """你是法律检索专家。分析以下用户发布的内容，识别其涉及的法律问题。

## 待分析内容
{content}

## 违规类型初判
{content_type}

## 可用的法律检索词（必须从以下列表中选择，不得使用列表外的法律名称）
{taxonomy_hint}

## 输出要求
从上方"可用的法律检索词"列表中，选出3条与本内容最相关的检索词。
输出 JSON 格式，不要输出其他内容：
{{"queries": ["检索词1", "检索词2", "检索词3"]}}

注意：只能选择列表中已有的词条，不要自创法律名称。"""


async def _generate_stepback_queries(
    content_text: str,
    content_type: str,
) -> list[str]:
    """Q3：调用便宜 expander LLM，从本体约束中选出最多 3 条检索词。

    【容错】LLM 失败 / JSON 解析失败 / 越界词条 → 回退 get_step_back_query(content_type)
    回退保证主流程不中断。
    """
    taxonomy_hint = get_domain_hint(content_type)
    prompt = _STEP_BACK_PROMPT.format(
        content=content_text[:300],
        content_type=content_type,
        taxonomy_hint=taxonomy_hint,
    )
    try:
        llm = get_expander_llm()
        resp = await llm.ainvoke([HumanMessage(content=prompt)])
        raw = resp.content.strip()

        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if m:
            data = json.loads(m.group(0))
            queries = data.get("queries", [])
            # 【项目自定义】二次校验：LLM 输出必须在 law_taxonomy 词条集合内
            valid_terms = set(get_search_terms(content_type))
            validated = [
                q for q in queries
                if any(term in q or q in term for term in valid_terms)
            ]
            if validated:
                return validated[:3]

        return [get_step_back_query(content_type)]

    except Exception as e:
        print(f"[QueryExpander] Step-Back 调用失败（回退到预置查询）: {e}")
        return [get_step_back_query(content_type)]


async def expand_queries(
    content_list: list[str],
    content_type: str,
    type_query: str,
) -> list[str]:
    """生成最多 5 条去重检索 query，供 retrieve_node 并行检索。

    参数:
        content_list: 被审核内容列表
        content_type: classify 或级联给出的违规类型
        type_query:   Q2 模板 query（来自 _TYPE_QUERY_MAP）

    返回:
        [Q1原文, Q2模板, Q3a, Q3b, ...] 最多 5 条
    """
    content_text = " ".join(content_list)[:200]

    stepback_queries = await _generate_stepback_queries(content_text, content_type)

    all_queries: list[str] = []

    # Q1：原文语义（最鲁棒，不依赖分类）
    all_queries.append(content_text)

    # Q2：类型模板
    if type_query and type_query not in all_queries:
        all_queries.append(type_query)

    # Q3：Step-Back 本体约束（可能 1~3 条）
    for q in stepback_queries:
        if q and q not in all_queries:
            all_queries.append(q)

    return all_queries[:5]


def dedup_and_merge(result_lists: list[list[str]]) -> list[str]:
    """多路检索结果合并：被多路同时命中的 chunk 排名更靠前（投票机制）。

    【项目自定义】
      - 去重 key = chunk 前 100 字符（避免格式细微差异）
      - 排序 key = (出现次数 DESC, 平均 rank ASC)

    参数:
        result_lists: 每路 retrieve() 返回的 chunk 文本列表

    返回:
        去重合并后的 chunk 列表，按置信度降序
    """
    from collections import defaultdict

    chunk_stats: dict[str, dict] = defaultdict(lambda: {"count": 0, "rank_sum": 0})

    for result_list in result_lists:
        for rank, chunk in enumerate(result_list):
            key = chunk[:100].strip()
            chunk_stats[key]["count"] += 1
            chunk_stats[key]["rank_sum"] += rank
            chunk_stats[key]["full_text"] = chunk

    sorted_chunks = sorted(
        chunk_stats.values(),
        key=lambda x: (-x["count"], x["rank_sum"] / max(x["count"], 1)),
    )

    return [item["full_text"] for item in sorted_chunks]
