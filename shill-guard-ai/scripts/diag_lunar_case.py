"""针对农历好日子用例的分步诊断。

用法（cmd）:
  D:\\Environment\\Anaconda\\envs\\agent\\python.exe -X utf8 scripts\\diag_lunar_case.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import time

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

QUERY = "今天是多少号？中国农历多少号？今年农历7月份有几号的日子是好日子？双数，并且宜嫁娶？"
USER_ID = "diag_lunar_user"


def ms(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)


async def main() -> None:
    print("=" * 72)
    print("农历用例分步诊断")
    print(f"Query: {QUERY}")
    print("=" * 72)

    # 1) mem0
    print("\n[1] mem0.search")
    from app.agents.chat.memory import search_memories
    t0 = time.perf_counter()
    mem = await search_memories(QUERY, USER_ID)
    print(f"  elapsed={ms(t0)}ms  result_len={len(mem)}  preview={mem[:80]!r}")

    # 2) RAG 拆开：embed / BM25 / rerank_api / local fallback
    print("\n[2] RAG 拆分")
    from app.rag.retriever import _vector_search_async, _rrf_fusion
    from app.rag.es_client import es_search
    from app.rag.reranker import rerank_api
    from app.config import settings

    t0 = time.perf_counter()
    vec = await _vector_search_async(QUERY, top_k=settings.rag_recall_k)
    print(f"  vector_search={ms(t0)}ms  hits={len(vec)}")

    t0 = time.perf_counter()
    bm25 = await es_search(QUERY, top_k=settings.rag_recall_k)
    print(f"  bm25(es)={ms(t0)}ms  hits={len(bm25)}")

    fused = _rrf_fusion(vec, bm25)
    candidates = [c for c, _, _ in fused[:5]]
    print(f"  candidates={len(candidates)}")

    if candidates:
        t0 = time.perf_counter()
        try:
            # 强制只测 API，避免本地 fallback 干扰结论：临时清空 key 后再恢复不合适
            # 这里直接测现有 rerank_api（含 fallback）
            ranked = await rerank_api(QUERY, candidates, top_k=settings.rag_rerank_top_k)
            print(f"  rerank_api(+fallback)={ms(t0)}ms  ranked={len(ranked)}")
            for i, (chunk, score) in enumerate(ranked[:3]):
                print(f"    #{i+1} score={score:.3f}  {chunk[:60]!r}")
        except Exception as e:
            print(f"  rerank FAILED after {ms(t0)}ms: {type(e).__name__}: {e}")

    # 3) Main LLM 直连
    print("\n[3] Main LLM 直连（无图）")
    from app.llm import get_llm
    from langchain_core.messages import HumanMessage, SystemMessage
    llm = get_llm()
    t0 = time.perf_counter()
    try:
        resp = await llm.ainvoke([
            SystemMessage(content="你是助手，简短回答。"),
            HumanMessage(content="今天公历几号？一句话回答。"),
        ])
        print(f"  llm={ms(t0)}ms  reply={str(resp.content)[:80]!r}")
    except Exception as e:
        print(f"  llm FAILED after {ms(t0)}ms: {type(e).__name__}: {e}")

    # 4) 环境噪音
    print("\n[4] 环境噪音开关")
    print(f"  LANGCHAIN_TRACING_V2={os.environ.get('LANGCHAIN_TRACING_V2')!r}")
    print(f"  LANGCHAIN_API_KEY set={bool(os.environ.get('LANGCHAIN_API_KEY'))}")
    print(f"  HTTPS_PROXY={os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')!r}")
    print(f"  HTTP_PROXY={os.environ.get('HTTP_PROXY') or os.environ.get('http_proxy')!r}")
    print(f"  mem0_enabled={settings.mem0_enabled}")
    print(f"  siliconflow_api_key set={bool(settings.siliconflow_api_key)}")

    print("\n完成。")


if __name__ == "__main__":
    asyncio.run(main())
