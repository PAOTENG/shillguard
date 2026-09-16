"""快速测试 RAG 检索：验证向量库能命中正确的文档。"""
from app.rag.retriever import retrieve

queries = [
    "怎么发笔记？最多能传几张图？",
    "忘记密码怎么办？",
    "电子烟能不能带货？",
    "粉丝多少能接广告？佣金怎么算？",
    "怎么开直播？会员有什么权益？",
    "我的笔记被误删了怎么申诉？",
    "平台会收集我哪些数据？",
    "什么内容会被封号？",
]

for q in queries:
    print(f"\n问：{q}")
    snippets = retrieve(q, top_k=2)
    for i, s in enumerate(snippets, 1):
        # 只显示前 80 字，方便看命中了哪份文档
        preview = s.replace("\n", " / ")[:80]
        print(f"  [{i}] {preview}...")
    if not snippets:
        print("  （未命中）")
