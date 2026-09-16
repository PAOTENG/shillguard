"""【已废弃】早期索引构建占位脚本，请改用 app/rag/indexer.py。

实际实现见 app/rag/indexer.py 的 build_index()：
  - 遍历 app/rag/sources/ 下所有法规文件
  - 切块（500字/块，50字重叠）
  - 双写 ChromaDB（向量）+ Elasticsearch（BM25）

运行：
    python -m app.rag.indexer

本文件保留仅作历史对照，不再维护。
"""
if __name__ == "__main__":
    print("[已废弃] 请改用: python -m app.rag.indexer")
