总体顺序原则
由简到难，每步都能独立测试：



第1步：文档解析器（无依赖，基础工具）
第2步：持久化 Memory（改一行代码，立刻生效）
第3步：用户上传文档处理（router + graph 改造）
第4步：RAG 知识库（最复杂，建议最后做）
第1步：app/rag/doc_parser.py（新建）
干什么：把用户上传的文件（PDF/Word/TXT）解析成纯文本字符串。

实现逻辑：



接收文件字节流 + 文件名
    ↓
判断后缀：.pdf → pypdf 解析 | .docx → python-docx 解析 | .txt → 直接 decode
    ↓
返回字符串
不涉及任何其他模块，可以单独写完单独测试。

第2步：改 graph.py（持久化 Memory）
干什么：把 MemorySaver 换成 SqliteSaver，记忆存到本地 SQLite 文件，重启不丢失。

改动极小：



python
# 改前
from langgraph.checkpoint.memory import MemorySaver
return g.compile(checkpointer=MemorySaver())
 
# 改后
from langgraph.checkpoint.sqlite import SqliteSaver
checkpointer = SqliteSaver.from_conn_string("./data/memory.db")
return g.compile(checkpointer=checkpointer)
同时需要：在 config.py 加一个 memory_db_path 配置项。

第3步：改造 router + graph 支持用户上传文档
这步涉及两个文件的改动：

3a. 改 schemas.py
ChatRequest 目前是纯 JSON，要改成支持文件上传。FastAPI 里，文件上传必须用 Form + UploadFile，不能用 BaseModel，所以 router 的参数声明方式要变。

逻辑：



router 接收：message(Form字段) + thread_id(Form字段) + file(可选 UploadFile)
    ↓
如果有 file：调 doc_parser 解析 → 得到 doc_text
如果没有 file：doc_text = ""
    ↓
把 doc_text 作为额外上下文传进 graph
3b. 改 graph.py
ChatState 加一个 doc_context 字段，chat_node 里把它拼进 system prompt：



system prompt = 原始 SYSTEM_PROMPT
如果 doc_context 不为空：
    system prompt += "\n\n用户上传了以下文档，请基于文档内容回答：\n" + doc_context
3c. 改 router.py


POST /ai/chat
接收 multipart/form-data
    ↓
解析文件（如有）
    ↓
构建 inputs = {messages: [HumanMessage], doc_context: doc_text}
    ↓
graph.astream_events → SSE 流式返回（逻辑不变）
第4步：RAG 知识库（三个文件）
这步最复杂，分三个子文件：

4a. 新建 app/rag/sources/（目录）
你自己把知识库文件（PDF/MD/TXT）放进这个目录。这些是管理员预置的，不是用户上传的。

4b. 新建 app/rag/indexer.py
干什么：把 sources/ 里的文档建成向量索引存到 ChromaDB。

逻辑：



遍历 sources/ 下所有文件
    ↓
用 doc_parser 解析 → 得到文本
    ↓
切块（每块 500 字，重叠 50 字）
    ↓
用 OpenAI embedding 向量化每个块
    ↓
存入 ChromaDB（collection 名固定为 "kg"）
这个脚本只需要跑一次（或知识库更新时重跑），不需要每次对话都跑。运行方式：




powershell
python -m app.rag.indexer
4c. 新建 app/rag/retriever.py
干什么：对话时根据用户问题检索最相关的知识库片段。

逻辑：



接收 query 字符串
    ↓
query 向量化
    ↓
ChromaDB 相似度搜索 → top 3 片段
    ↓
返回字符串列表
4d. 改 graph.py（加 RAG 节点）
在 chat_node 之前加一个 rag_node：



graph 流程：
    用户消息进来
        ↓
    rag_node：检索知识库 → 把结果写入 state["rag_context"]
        ↓
    chat_node：system prompt 里加入 rag_context，再调 LLM
文件改动总览


需要新建的文件：
├── app/rag/doc_parser.py        ← 第1步
├── app/rag/indexer.py           ← 第4步
├── app/rag/retriever.py         ← 第4步
└── app/rag/sources/             ← 第4步（目录，放你的知识文档）
 
需要修改的文件：
├── app/agents/chat/graph.py     ← 第2步 + 第3步 + 第4步
├── app/agents/chat/router.py    ← 第3步
├── app/agents/chat/prompts.py   ← 第3步 + 第4步（prompt 加槽位）
└── app/config.py                ← 第2步（加 memory_db_path）
依赖安装确认
在开始写代码之前，确保这些包已装好：



powershell
conda activate agent
pip install chromadb langchain-chroma pypdf python-docx python-multipart