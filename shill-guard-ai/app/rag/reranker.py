"""Cross-Encoder 重排序：对 (query, chunk) 对做精排。

【Bi-Encoder vs Cross-Encoder】
  Bi-Encoder（向量检索）: query 和 doc 分别编码再算相似度，快但粗
  Cross-Encoder（本模块）: query+doc 一起编码，慢但准，适合少量候选精排

【两种实现】
  rerank()     — 本地 FlagEmbedding + bge-reranker-v2-m3（需 torch，MCP 子进程会挂）
  rerank_api() — 硅基流动远程 API（生产默认，retriever.py 调用）

模型: BAAI/bge-reranker-v2-m3（北京智源，多语言 cross-encoder）
"""
from functools import lru_cache

import httpx  # 【官方 httpx】异步 HTTP 客户端

from app.config import settings


@lru_cache
def _get_reranker():
    """懒加载本地 FlagReranker（首次调用才 import torch，避免启动慢）。

    use_fp16=True: 【FlagEmbedding 参数】半精度推理，显存减半
    注意：Windows 无控制台 MCP 子进程不要调用此函数（会挂死）
    """
    from FlagEmbedding import FlagReranker
    reranker = FlagReranker(
        settings.reranker_model,
        use_fp16=True,
    )
    return reranker


def rerank(query: str, chunks: list[str], top_k: int = 5) -> list[tuple[str, float]]:
    """本地 cross-encoder 重排序（同步，适合 asyncio.to_thread 包装）。

    参数:
        query:  检索 query
        chunks: RRF 融合后的候选 chunk 列表
        top_k:  保留条数

    返回:
        [(chunk_text, score), ...] 按 score 降序，score 经 normalize=True 归一化到 0~1
    """
    if not chunks:
        return []

    reranker = _get_reranker()
    pairs = [[query, c] for c in chunks]  # cross-encoder 输入格式：[[q,d1],[q,d2],...]
    scores = reranker.compute_score(pairs, normalize=True)

    if isinstance(scores, float):
        scores = [scores]

    ranked = sorted(zip(chunks, scores), key=lambda x: x[1], reverse=True)
    return ranked[:top_k]


async def rerank_api(query: str, chunks: list[str], top_k: int = 5) -> list[tuple[str, float]]:
    """硅基流动远程 rerank API（OpenAI 兼容 /v1/rerank 格式）。

    【降级策略（已修改）】
      不再降级到本地 torch（首次加载 bge-reranker-v2-m3 需 40s+，网络抖动时代价极高）。
      失败时直接抛出异常，由调用方 retrieve() 的 except 块返回 RRF 候选（约 0ms）。

    超时：5s（原 30s），网络不稳时快速失败，避免长时间阻塞。

    API 响应格式: {"results": [{"index": 0, "relevance_score": 0.98}, ...]}
    """
    if not chunks:
        return []
    if not settings.siliconflow_api_key:
        # 未配置 API key → 直接抛出，让 retrieve() 返回 RRF 候选
        raise ValueError("siliconflow_api_key not configured, skipping rerank")

    payload = {
        "model": settings.reranker_model,
        "query": query,
        "documents": chunks,
        "top_n": top_k,
        "return_documents": False,
    }
    headers = {
        "Authorization": f"Bearer {settings.siliconflow_api_key}",
        "Content-Type": "application/json",
    }
    # 超时 5s：网络抖动时快速失败，不阻塞 rag_node
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.post(
            settings.siliconflow_rerank_url,
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()
    results = data.get("results", [])
    return [(chunks[r["index"]], r["relevance_score"]) for r in results]
