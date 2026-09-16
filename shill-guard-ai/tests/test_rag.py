"""RAG 混合检索验证脚本：分别测试三路检索效果。"""
import sys
sys.path.insert(0, ".")

from app.rag.retriever import _vector_search, _bm25_search, _rrf_fusion, retrieve
from app.config import settings

# 测试问题
test_queries = [
    "怎么删除好友",
    "账号被封了怎么办",
    "发帖有什么规范",
    "怎么添加好友",
    "直播有什么要求",
]

recall_k = settings.rag_recall_k

for query in test_queries:
    print("=" * 70)
    print(f"🔍 查询: {query}")
    print("=" * 70)

    # 1. 向量检索
    print("\n【向量检索 ChromaDB】top-5:")
    vec_results = _vector_search(query, top_k=recall_k)
    for i, (chunk, dist, meta) in enumerate(vec_results[:5]):
        print(f"  {i+1}. [距离={dist:.4f}] [{meta.get('source','?')}]")
        print(f"     {chunk[:80]}...")

    # 2. BM25检索
    print("\n【BM25 关键词检索】top-5:")
    bm25_results = _bm25_search(query, top_k=recall_k)
    for i, (chunk, score, meta) in enumerate(bm25_results[:5]):
        print(f"  {i+1}. [BM25分={score:.4f}] [{meta.get('source','?')}]")
        print(f"     {chunk[:80]}...")

    # 3. RRF融合
    print("\n【RRF 融合排序】top-5:")
    fused = _rrf_fusion(vec_results, bm25_results)
    for i, (chunk, score, meta) in enumerate(fused[:5]):
        print(f"  {i+1}. [RRF分={score:.5f}] [{meta.get('source','?')}]")
        print(f"     {chunk[:80]}...")

    # 4. 最终结果（含重排序）
    print("\n【最终结果（混合检索 + 重排序）】top-5:")
    final = retrieve(query)
    for i, chunk in enumerate(final):
        print(f"  {i+1}. {chunk[:80]}...")

    print()

print("=" * 70)
print("验证完成！如果上方三路都有结果，说明混合检索已生效。")
print("=" * 70)
