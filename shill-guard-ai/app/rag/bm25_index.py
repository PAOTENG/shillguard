"""BM25 关键词检索索引（本地 JSON 持久化版）。

【当前状态：备用/遗留】
  生产 RAG 的 BM25 路已迁移到 Elasticsearch（app/rag/es_client.py），
  retriever.py 调用 es_search() 而非本模块。
  本文件保留用于：无 ES 环境的本地开发、历史兼容、离线评测对照。

【BM25 算法】
  Best Matching 25：经典概率检索模型，rank_bm25.BM25Okapi 实现。
  适合关键词精确匹配（法条号、专有名词），与向量语义检索互补。

【中文分词】
  jieba.lcut：结巴分词，filter 掉单字符噪声。
"""
import json

import jieba
from rank_bm25 import BM25Okapi
from pathlib import Path

from app.config import settings


def _tokenize(text: str) -> list[str]:
    """中文分词 + 过滤单字符 token。"""
    tokens = jieba.lcut(text)
    return [t.strip() for t in tokens if len(t.strip()) > 1]


class BM25Index:
    """BM25 索引：构建、JSON 持久化、检索。"""

    def __init__(self):
        self.bm25: BM25Okapi | None = None
        self.chunks: list[str] = []
        self.metadatas: list[dict] = []

    def build(self, chunks: list[str], metadatas: list[dict]):
        """从 chunk 列表构建内存索引（indexer 建库时调用）。"""
        self.chunks = chunks
        self.metadatas = metadatas
        tokenized = [_tokenize(c) for c in chunks]
        self.bm25 = BM25Okapi(tokenized)

    def save(self, path: str | None = None):
        """持久化 chunks+metadatas 到 JSON（BM25 参数重建时重新 tokenize）。"""
        path = path or settings.bm25_index_path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        data = {
            "chunks": self.chunks,
            "metadatas": self.metadatas,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

    def load(self, path: str | None = None) -> bool:
        """从磁盘加载；文件不存在返回 False。"""
        path = path or settings.bm25_index_path
        if not Path(path).exists():
            return False
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.chunks = data["chunks"]
        self.metadatas = data["metadatas"]
        tokenized = [_tokenize(c) for c in self.chunks]
        self.bm25 = BM25Okapi(tokenized)
        return True

    def search(self, query: str, top_k: int = 20) -> list[tuple[str, float, dict]]:
        """BM25 检索。

        返回: [(chunk_text, bm25_score, metadata), ...]
        只返回 score > 0 的结果。
        """
        if self.bm25 is None:
            return []
        tokens = _tokenize(query)
        scores = self.bm25.get_scores(tokens)
        top_indices = sorted(
            range(len(scores)), key=lambda i: scores[i], reverse=True
        )[:top_k]
        return [
            (self.chunks[i], float(scores[i]), self.metadatas[i])
            for i in top_indices if scores[i] > 0
        ]


_bm25_index: BM25Index | None = None


def get_bm25_index() -> BM25Index:
    """进程内 BM25 单例；索引文件不存在时返回空实例（search 返回 []）。"""
    global _bm25_index
    if _bm25_index is None:
        _bm25_index = BM25Index()
        if not _bm25_index.load():
            pass
    return _bm25_index
