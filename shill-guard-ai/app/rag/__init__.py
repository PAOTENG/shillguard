"""RAG 检索子系统：混合检索 + 重排序，供 moderation/chat/detect 共用。

核心模块：
- retriever.py              : 对外主入口 retrieve() — 搜 Child，回填 Parent
- parent_child_splitter.py  : 条级 Child + 节/邻条 Parent（结构优先切分）
- parent_store.py           : Parent 文本持久化（data/rag_parents.json）
- query_expander.py         : 三路 query 扩展（Q1 原文 / Q2 类型模板 / Q3 Step-Back）
- indexer.py                : 建库 CLI，Child→Chroma+ES，Parent→JSON
- es_client.py              : Elasticsearch BM25 检索（生产环境）
- bm25_index.py             : 本地 JSON BM25（遗留/离线备用）
- reranker.py               : 硅基流动 bge-reranker API
- law_taxonomy.py           : 法律本体约束（Step-Back 输出白名单）
- doc_parser.py             : sources/ 文档解析
- admin_router.py           : 索引管理 HTTP 接口
- sources/                  : 约 1000 个国家法律法规 Markdown 文件（按类别前缀命名）
"""
