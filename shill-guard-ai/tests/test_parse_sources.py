"""测试 doc_parser 能否解析所有 sources/ 文件。"""
from pathlib import Path
from app.rag.doc_parser import parse_document

SOURCES = Path(__file__).resolve().parent.parent / "app" / "rag" / "sources"

for f in sorted(SOURCES.iterdir()):
    if not f.is_file():
        continue
    try:
        text = parse_document(f.read_bytes(), f.name)
        head = text[:80].replace("\n", " / ")
        print(f"[OK] {f.name:24} {len(text):5d} chars | {head}")
    except Exception as e:
        print(f"[FAIL] {f.name:24} {type(e).__name__}: {e}")
