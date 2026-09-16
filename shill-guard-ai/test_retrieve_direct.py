"""直接调 rag_retrieve，绕开 MCP，定位是不是检索本身卡死。"""
import os
from pathlib import Path

os.chdir(Path(__file__).resolve().parent)  # 切到项目根

print("开始加载 retriever...", flush=True)
from app.rag.retriever import retrieve

print("开始检索...", flush=True)
chunks = retrieve("网络暴力", top_k=3)

print(f"=== 检索完成，返回 {len(chunks)} 条 ===", flush=True)
for i, c in enumerate(chunks):
    print(f"--- chunk[{i}] ---")
    print(c[:300])