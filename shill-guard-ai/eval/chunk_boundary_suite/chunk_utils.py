"""与 app/rag/indexer.py 完全一致的滑动窗口切分，供本套件离线复现。"""
from __future__ import annotations

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
STEP = CHUNK_SIZE - CHUNK_OVERLAP  # 450


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[dict]:
    """返回带起止偏移的 chunk 列表。"""
    step = chunk_size - overlap
    out: list[dict] = []
    for i in range(0, len(text), step):
        piece = text[i : i + chunk_size]
        if piece.strip():
            out.append(
                {
                    "index": len(out),
                    "start": i,
                    "end": i + len(piece),
                    "text": piece,
                }
            )
    return out


def find_span(text: str, needle: str) -> tuple[int, int] | None:
    pos = text.find(needle)
    if pos < 0:
        return None
    return pos, pos + len(needle)


def analyze_article_split(doc_text: str, full_article: str) -> dict:
    """判断完整条款是否被滑动窗口切断，以及是否存在「半条命中」。"""
    chunks = chunk_text(doc_text)
    span = find_span(doc_text, full_article)
    if span is None:
        return {
            "found_in_doc": False,
            "intact_in_single_chunk": False,
            "half_hit_possible": False,
            "error": "full_article 未出现在文档中（请检查生成脚本）",
            "chunks": chunks,
        }

    start, end = span
    intact_idxs = []
    head_only_idxs = []
    tail_only_idxs = []
    # 半条判定：取条款前 40% 与后 40% 作为 head/tail 探针
    cut = max(20, len(full_article) // 5)
    head = full_article[:cut]
    tail = full_article[-cut:]

    for c in chunks:
        t = c["text"]
        has_full = full_article in t
        has_head = head in t
        has_tail = tail in t
        if has_full:
            intact_idxs.append(c["index"])
        if has_head and not has_tail:
            head_only_idxs.append(c["index"])
        if has_tail and not has_head:
            tail_only_idxs.append(c["index"])

    # 条款跨边界：起止不落在同一 chunk 的 [start,end) 内
    straddling = True
    for c in chunks:
        if c["start"] <= start and end <= c["end"]:
            straddling = False
            break

    return {
        "found_in_doc": True,
        "article_start": start,
        "article_end": end,
        "article_len": len(full_article),
        "straddling_boundary": straddling,
        "intact_in_single_chunk": len(intact_idxs) > 0,
        "intact_chunk_indexes": intact_idxs,
        "head_only_chunk_indexes": head_only_idxs,
        "tail_only_chunk_indexes": tail_only_idxs,
        "half_hit_possible": len(head_only_idxs) > 0 and not intact_idxs,
        "head_probe": head,
        "tail_probe": tail,
        "num_chunks": len(chunks),
        "chunks": chunks,
    }
