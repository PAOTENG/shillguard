"""Parent 文本持久化存储（child 命中后回填用）。

Chroma/ES 只索引 child；parent 按 parent_id 存在 JSON 文件，
避免把最长 1500 字的 parent 塞进向量库 metadata。
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

from app.config import settings

_lock = threading.Lock()
_cache: dict[str, dict] | None = None


def parent_store_path() -> Path:
    path = getattr(settings, "rag_parent_store_path", None) or "./data/rag_parents.json"
    return Path(path)


def _load_unlocked() -> dict[str, dict]:
    global _cache
    if _cache is not None:
        return _cache
    path = parent_store_path()
    if not path.exists():
        _cache = {}
        return _cache
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    # 兼容 {parents: {...}} 或直接 dict
    if isinstance(data, dict) and "parents" in data and isinstance(data["parents"], dict):
        _cache = data["parents"]
    elif isinstance(data, dict):
        _cache = data
    else:
        _cache = {}
    return _cache


def load_parents() -> dict[str, dict]:
    with _lock:
        return dict(_load_unlocked())


def get_parent(parent_id: str) -> dict | None:
    with _lock:
        return _load_unlocked().get(parent_id)


def get_parent_text(parent_id: str) -> str | None:
    rec = get_parent(parent_id)
    if not rec:
        return None
    return rec.get("text")


def save_all_parents(parents: dict[str, dict]) -> None:
    """全量覆盖写入（建库时用）。"""
    global _cache
    path = parent_store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "strategy": "article_child_section_parent",
        "count": len(parents),
        "parents": parents,
    }
    tmp = path.with_suffix(".json.tmp")
    with _lock:
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        tmp.replace(path)
        _cache = dict(parents)


def upsert_parents(records: list[dict]) -> None:
    """增量写入/更新若干 parent 记录。"""
    global _cache
    with _lock:
        store = _load_unlocked()
        for rec in records:
            pid = rec.get("parent_id")
            if not pid:
                continue
            store[pid] = rec
        _cache = store
        path = parent_store_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "strategy": "article_child_section_parent",
            "count": len(store),
            "parents": store,
        }
        tmp = path.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        tmp.replace(path)


def delete_parents_by_source(source_file: str) -> int:
    """删除某 source 下全部 parent，返回删除条数。"""
    global _cache
    with _lock:
        store = _load_unlocked()
        remove = [k for k, v in store.items() if v.get("source_file") == source_file]
        for k in remove:
            del store[k]
        _cache = store
        path = parent_store_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "strategy": "article_child_section_parent",
            "count": len(store),
            "parents": store,
        }
        tmp = path.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        tmp.replace(path)
        return len(remove)


def clear_cache() -> None:
    global _cache
    with _lock:
        _cache = None
