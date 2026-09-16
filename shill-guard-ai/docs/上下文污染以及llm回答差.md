# 上下文污染与 LLM 回答质量差问题记录

> 记录日期：2026-07-12  
> 项目：ShillGuard AI — Chat Agent 多轮对话系统  
> 问题来源：下午开发过程中真实复现，本文档完整还原发现→排查→修复的全过程

---

## 一、问题全景：污染链是什么

在实现三层记忆（滑动窗口 + LLM 摘要 + mem0 跨会话）之后，发现如下连锁问题：

```
第 1 轮：用户说"我叫小明，25岁"
         │
         ▼
LLM 被注入了 memories/summary/RAG 原文 → 回答前复读一大段 bullet list：
  "• 用户叫小明，25岁
   • 用户问过台风动态
   好的，你叫小明..."

         │ 这段复读内容被写进 PostgreSQL 历史
         ▼
第 N 轮：摘要压缩时把复读内容也压缩进去
         → 摘要里出现"用户问过台风"（实为助手复读，不是用户问的）

         │
         ▼
第 M 轮：mem0 写入了（user, assistant）对话对，其中 assistant 含复读内容
         → mem0 提取出"台风"相关事实
         → 下次检索 mem0 时把台风注入到与台风无关的对话

         │
         ▼
污染闭环形成：每一轮都在放大前几轮的错误
```

这就是工业文献中描述的 **"Memory Laundering"**（记忆漂白/自强化循环）：  
助手自己生成的内容被当成"用户事实"写入记忆，再次被检索后影响新一轮生成。

---

## 二、逐个问题记录

### 问题 1：LLM 复读背景 bullet list

**现象：**  
LLM 回答前先输出 2-5 行 bullet：
```
• 用户叫小明，25岁
• 用户问过台风动态
• 用户使用 FastAPI 开发...

你好，小明！...（真正的答案）
```

**根本原因：**  
`build_system_prompt` 把 `memories`、`summary`、`rag_context` 以 bullet 格式直接注入 system prompt。  
LLM 接收到结构化 bullet 数据后，倾向于"先列举再回答"（这是标准的 LLM 行为，不是 bug）。

**排查过程：**  
1. 先加了 prompt 规则："不要复读背景"→ 无效，LLM 仍然复读
2. 再加 regex 清洗 `strip_leading_context_echo()`，在 `chat_node` 里 post-hoc 剥离 bullet 块  
   → 但这造成了**新问题**：SSE 流已经把 bullets 发给了前端，但存储的版本是清洗后的  
   → 用户看到了 bullets，但 PostgreSQL 历史里没有，产生"历史记录与用户所见不符"的反模式
3. 根本解法：**架构隔离（Worker LLM）**

**最终修复（工业标准做法）：**
- 新增 `context_processor_node`（Worker LLM）：读取所有原始 memories/summary/RAG
- 通过 `with_structured_output(WorkerContextResult)` 强制输出单句 JSON
- `chat_node`（Main LLM）只接收 `processed_context`（1句话），物理上无法复读原始 bullet

**移除的补丁：**
- 删除 `graph.py` 中的 `strip_leading_context_echo` 调用（消除 stream/storage 不一致）
- 保留 `output_sanitizer.py` 文件但不再主动调用（作为历史记录）

---

### 问题 2：SSE 流污染 — Worker LLM JSON 泄漏给用户

**现象：**  
`router.py` 的 SSE 事件监听用的是：
```python
if event["event"] == "on_chat_model_stream":
```
这会捕获图中所有 LLM 的流输出，包括 `context_processor_node`（Worker LLM）。

Worker 使用 `function_calling` 方式输出结构化 JSON，其 stream chunk 可能包含 JSON 片段，
这些片段会被推送给前端。

**修复：**  
在事件过滤时增加节点名判断：
```python
node_name = event.get("metadata", {}).get("langgraph_node", "")
if event["event"] == "on_chat_model_stream" and node_name == "chat":
```
只推送 `chat` 节点的输出，Worker 的结构化 JSON 不再泄漏。

---

### 问题 3：mem0 记忆污染 — 助手复读进入长期记忆

**现象：**  
`add_memories_background` 传入 `(user, assistant)` 对话对，其中 assistant 含 bullet 复读。  
mem0 内置 LLM 从助手发言中提取到"台风"、"用户问过..."等事实写入向量库。  
下次与台风无关的对话中，检索 mem0 时把这些事实注入 Worker，造成污染。

**临时修复（下午的补丁）：**  
改为只传用户发言：`mem0.add(user_message.strip(), user_id=user_id)`

**问题：**  
这不符合 Mem0 设计（其内置 LLM 从对话对中双向提取事实），降低了记忆提取质量，  
导致"我叫小明"这类信息因缺少对话上下文而被 mem0 误分类为临时信息。

**根本修复（工业标准）：**
1. 架构上先解决 assistant 复读问题（Worker 隔离）
2. 恢复传入完整对话对 `(user, assistant)`
3. 写入前经 **OWASP Agent Memory Guard (ASI06)** 校验：
   ```python
   _amg_guard.write("conversation.user", user_message)
   _amg_guard.write("conversation.assistant", assistant_message)
   ```
   检测到 prompt injection / 自强化循环 → 抛 `PolicyViolation` → 静默跳过写入

---

### 问题 4：年龄答"不知道" — Worker 找不到用户自述信息

**现象（多轮对话测试）：**
```
第 1 轮：用户：我今年25岁
第 4 轮：用户：我多大了？
         LLM 回答：抱歉，我不知道你的年龄。
```

**根本原因：**  
- 只有 3 轮对话时，历史消息 < 10 条，摘要不触发，`summary = ""`  
- mem0 刚写入，检索时可能召回为空（刚写入不一定立刻可检索到）  
- `context_processor_node` 只看 `memories` 和 `summary`，两者都空，返回 `has_relevant_context=false`  
- `processed_context = ""`，Main LLM 不知道用户年龄

**修复：**  
在 `context_processor_node` 中增加 `[用户此前发言]` 原始输入：
```python
user_said = format_user_said_history(list(state.get("messages", [])))
```
Worker 收到用户原始历史发言，能从中找到"我今年25岁"这条事实，  
即使 mem0/summary 都为空也能正确回答。

---

### 问题 5：摘要只含用户发言 — 上下文不完整

**现象：**  
摘要只有 `• 用户叫小明` 类条目，没有助手的任何答复记录，  
导致 LLM 在第 11 轮后无法通过摘要了解之前对话的完整语境。

**原因（临时补丁遗留）：**  
为避免助手复读内容进摘要，`summarize_old_messages` 过滤了所有 `AIMessage`：
```python
for m in messages:
    if isinstance(m, HumanMessage):  # 只看用户
        lines.append(f"用户：{m.content}")
```

**修复：**  
助手消息现在干净（Worker 隔离保证无复读），还原双角色摘要：
```python
elif isinstance(m, AIMessage) and isinstance(m.content, str) and m.content.strip():
    truncated = m.content.strip()[:200]
    lines.append(f"助手：{truncated}")
```
同时更新 `_SUMMARY_SYSTEM` 以明确记录助手关键结论（不含实时数据）。

---

### 问题 6：UI 历史随摘要消失 — checkpointer 反模式

**现象（潜在问题，第 11 轮后触发）：**  
LangGraph `RemoveMessage` 摘要机制删除旧消息后，`GET /ai/history/{thread_id}` 返回的历史会断裂，  
旧消息消失，用户在 UI 看到的对话记录不完整。

**根本原因：**  
`history_router.py` 直接读 LangGraph checkpointer：
```python
state = await graph.aget_state(config)
messages = state.values.get("messages", [])
```
checkpointer 是 LLM 的工作记忆，设计上就允许被压缩。
用 checkpointer 做 UI 历史是**反模式**（LangGraph 官方明确反对）。

**修复（双轨存储）：**
- 新建 `chat_messages` 表（append-only，永不删除）
- 每次请求写入用户消息，每次 SSE 完成写入助手消息
- `history_router.py` 改为读 `chat_messages` 表
- checkpointer 只给 LangGraph 内部用，与 UI 历史严格解耦

---

## 三、各问题与修复的文件对照

| 问题 | 根本原因 | 修复文件 | 修复方式 |
|------|---------|---------|---------|
| LLM 复读 bullet | 原始上下文直接注入 system prompt | `graph.py` | Worker 隔离：`context_processor_node` |
| SSE 推送 Worker JSON | 事件过滤未限制节点 | `router.py` | 增加 `langgraph_node == "chat"` 过滤 |
| stream/storage 不一致 | 事后 regex 改存储但流已发出 | `graph.py` | 删除 `strip_leading_context_echo` 调用 |
| mem0 污染 | 助手复读内容写入记忆 | `memory.py` + `router.py` | 恢复对话对 + AMG 写入守卫 |
| 年龄不知道 | Worker 看不到原始用户历史 | `graph.py` (`context_processor_node`) | 注入 `format_user_said_history()` |
| 摘要缺助手上下文 | 临时过滤了 AIMessage | `memory.py` | 还原双角色摘要，截断 200 字 |
| UI 历史断裂 | 直接读 checkpointer | `history_store.py`（新建） + `history_router.py` + `router.py` | 双轨存储 |

---

## 四、今天遇到的工程类错误（调试记录）

| 错误 | 原因 | 修复 |
|------|------|------|
| `column "channel_values" does not exist` | 尝试直接 SQL 读 LangGraph state | 改用 `graph.aget_state()` |
| `mem0.get_all()` API 报错 | 新版 mem0 改成 `filters={"user_id": "..."}` | 更新测试脚本 |
| `ProactorEventLoop` 报错 | Windows + psycopg3 需要 SelectorEventLoop | `app/main.py` 加 `WindowsSelectorEventLoopPolicy` |
| Python `SyntaxError` 中文弯引号 | `"你"` 在 `"..."` 字符串内被当成引号结束符 | 换成单引号 `'你'` |
| `Policy.default()` 不存在 | AMG v0.3.0 的方法是 `Policy.strict()` / `Policy.permissive()` | 查 `dir(Policy)` 确认实际 API |

---

## 五、最终架构图（修复后）

```
POST /ai/chat
│
├── append_message(chat_messages, "user")   ← 双轨存储：立刻写 UI 历史
│
└── LangGraph 图执行：
    memory_node
      ├── mem0.search(query, user_id)        ← 检索长期记忆
      └── [条件] summarize_old_messages()    ← 双角色摘要写独立 summary key
    rag_node
      └── 混合检索 + rerank + 阈值过滤
    context_processor_node (Worker LLM)
      ├── 输入: memories + summary + rag + user_said_history
      ├── 输出: WorkerContextResult(JSON)    ← 结构化，无 bullet
      └── processed_context = 单句关键事实
    chat_node (Main LLM)
      ├── 输入: system(processed_context) + 最近6条消息
      └── 输出: 干净回答（无复读来源）

SSE 推送：只推 langgraph_node=="chat" 的 token

finally:
  ├── AMG 校验(user_msg, assistant_msg)
  ├── mem0.add([user, assistant], user_id)  ← 完整对话对
  └── append_message(chat_messages, "assistant")  ← 双轨存储写助手回复

GET /ai/history/{thread_id}
  └── SELECT FROM chat_messages            ← 永远完整，不依赖 checkpointer
```
