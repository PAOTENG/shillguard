"""
RAG 召回质量评测：对每条 golden query 跑 retrieve()，
检验期望法条关键词是否出现在 top-k 结果中。

指标：
  recall@k    = 命中查询数 / 总查询数
                命中 = top-k 结果里包含至少一个 expected_keyword
  precision@k = 平均每查询里"相关块"占返回块的比例
                相关块 = 包含任意 expected_keyword 的块

用法（从项目根运行）：
  python eval/rag_eval.py
  python eval/rag_eval.py --k 3
"""
import asyncio
import sys
import time
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.rag.retriever import retrieve
from eval.golden_set import GOLDEN_RAG, RAGCase


# ═══════════════════════════════════════════════════════════════
#  单条用例评测
# ═══════════════════════════════════════════════════════════════

async def eval_one(case: RAGCase, k: int) -> dict:
    """跑一条 RAGCase，返回评测结果字典。"""
    t0 = time.perf_counter()
    try:
        chunks = await retrieve(case.query, top_k=k)
    except Exception as e:
        return {
            "id": case.id,
            "query": case.query,
            "expected_keywords": case.expected_keywords,
            "retrieved_count": 0,
            "hit": False,
            "hit_keywords": [],
            "relevant_count": 0,
            "precision": 0.0,
            "ms": (time.perf_counter() - t0) * 1000,
            "error": str(e),
            "description": case.description,
        }
    elapsed_ms = (time.perf_counter() - t0) * 1000

    # 把 top-k 所有块拼成一个大文本，做关键词子串查找
    full_text = "\n".join(chunks)
    hit_keywords = [kw for kw in case.expected_keywords if kw in full_text]

    if case.all_required:
        # 严格模式：必须所有关键词都命中
        hit = len(hit_keywords) == len(case.expected_keywords)
    else:
        # 宽松模式（默认）：至少一个关键词命中即算 recall 成功
        hit = len(hit_keywords) > 0

    # precision：k 个块里有几个块含有任意期望词
    relevant_chunks = [
        c for c in chunks
        if any(kw in c for kw in case.expected_keywords)
    ]
    precision = len(relevant_chunks) / len(chunks) if chunks else 0.0

    return {
        "id": case.id,
        "query": case.query,
        "expected_keywords": case.expected_keywords,
        "retrieved_count": len(chunks),
        "hit": hit,
        "hit_keywords": hit_keywords,
        "relevant_count": len(relevant_chunks),
        "precision": precision,
        "ms": elapsed_ms,
        "error": None,
        "description": case.description,
    }


# ═══════════════════════════════════════════════════════════════
#  批量评测
# ═══════════════════════════════════════════════════════════════

async def run_rag_eval(cases: list[RAGCase], k: int = 5) -> dict:
    """并发评测所有 RAGCase，返回指标汇总。"""
    tasks = [eval_one(c, k) for c in cases]
    results = await asyncio.gather(*tasks)

    total = len(results)
    hit_count = sum(1 for r in results if r["hit"])
    recall_k = hit_count / total if total > 0 else 0.0
    avg_precision = sum(r["precision"] for r in results) / total if total > 0 else 0.0
    avg_ms = sum(r["ms"] for r in results) / total if total > 0 else 0.0
    error_count = sum(1 for r in results if r["error"])

    return {
        "results": list(results),
        "total": total,
        "hit_count": hit_count,
        "recall_k": recall_k,
        "avg_precision": avg_precision,
        "avg_ms": avg_ms,
        "error_count": error_count,
        "k": k,
    }


# ═══════════════════════════════════════════════════════════════
#  报告打印
# ═══════════════════════════════════════════════════════════════

def print_rag_report(summary: dict) -> bool:
    """打印评测报告，返回是否通过 CI 阈值（recall@k ≥ 75%）。"""
    results = summary["results"]
    k = summary["k"]

    print("\n" + "=" * 72)
    print(f"  RAG 召回质量评测报告  (top-{k})")
    print("=" * 72)

    print(f"\n{'ID':>12} {'结果':<7} {'精确率':>6} {'ms':>7}  命中关键词 / 查询")
    print("-" * 72)
    for r in results:
        flag = "[HIT] " if r["hit"] else "[MISS]"
        hit_str = ", ".join(r["hit_keywords"])[:22] if r["hit_keywords"] else "—"
        err_tag = f" ERR:{r['error'][:20]}" if r["error"] else ""
        print(f"{r['id']:>12} {flag} {r['precision']:>5.0%} {r['ms']:>7.0f}ms  "
              f"{hit_str}{err_tag}")
        if not r["hit"] and not r["error"]:
            print(f"             ! 期望词: {r['expected_keywords']}")
            print(f"               查询  : {r['query']}")
    print("-" * 72)

    print(f"\n【指标汇总】")
    print(f"  总查询数          : {summary['total']}")
    print(f"  ★ Recall@{k:<2}       : "
          f"{summary['hit_count']}/{summary['total']} "
          f"= {summary['recall_k'] * 100:.1f}%")
    print(f"  ★ Avg Precision@{k:<2}: {summary['avg_precision'] * 100:.1f}%")
    print(f"  平均检索延迟      : {summary['avg_ms']:.0f}ms")
    if summary["error_count"] > 0:
        print(f"  ! 检索错误数      : {summary['error_count']}")

    # CI 阈值：recall@k ≥ 75%
    threshold = 0.75
    passed = summary["recall_k"] >= threshold
    status = "PASS" if passed else "FAIL"
    print(f"\n  CI 门禁: recall@{k} = {summary['recall_k'] * 100:.1f}% "
          f"(阈值 ≥ {threshold * 100:.0f}%)  [{status}]")
    print("=" * 72)
    return passed


# ═══════════════════════════════════════════════════════════════
#  独立运行入口
# ═══════════════════════════════════════════════════════════════

def main():
    import argparse
    ap = argparse.ArgumentParser(description="RAG 召回质量评测")
    ap.add_argument("--k", type=int, default=5, help="top-k（默认5）")
    args = ap.parse_args()

    print(f"开始 RAG 召回评测（{len(GOLDEN_RAG)} 条 golden query，top-{args.k}）...")
    summary = asyncio.run(run_rag_eval(GOLDEN_RAG, k=args.k))
    passed = print_rag_report(summary)
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
