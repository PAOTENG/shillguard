# ShillGuard MCP 接入排障全记录

> 日期：2026-07-06
> 范围：将项目 RAG/审核/检测能力封装为 MCP server 供 Cursor 调用时遇到的全部问题
> 环境：Windows 10，Anaconda 虚拟环境 `D:\Environment\Anaconda\envs\agent`，Python 3.12
> MCP 客户端：Cursor（stdio 传输）

## 背景与目标

把项目的 4 个能力封装成 MCP tool，让 Cursor 在 Chat 中根据对话上下文自动选择并调用：

| 工具 | 功能 | 底层复用 |
|---|---|---|
| `rag_search_laws` | 检索法律法规/平台规则知识库 | `app.rag.retriever.retrieve` |
| `moderate_content` | 被举报内容完整审核（分类→检索→判定→证据→处置） | `app.agents.moderation.graph` |
| `detect_user_score` | 单用户异常打分 | `app.agents.moderation.detect_router._score_user` |
| `generate_evidence` | 高危用户禁言证据生成 | `app.agents.detect.graph` |

MCP server 入口：`app/mcp/server.py`，用 `mcp[cli]>=1.27,<2` 的 FastMCP，stdio 传输。
Cursor 配置：用户级 `C:\Users\oops\.cursor\mcp.json`，`command=python`，`args=["-m","app.mcp.server"]`，`env={"PYTHONPATH": "D:\\Projects\\shill-guard-ai"}`。

---

## Bug 1：`python -m` 双重导入导致 0 工具注册

### 现象
MCP 客户端连上后 `tools/list` 返回 0 个工具，但 server 进程起来了。

### 控制台报错
```
RuntimeWarning: 'app.mcp.server' found in sys.modules after import of package 'app.mcp',
but prior to execution of 'app.mcp.server'; this may result in unpredictable behaviour
```

### 根因
`python -m app.mcp.server` 的执行机制：
1. 先 import `app.mcp` 包（执行 `app/mcp/__init__.py`）
2. 再把 `app.mcp.server` 当 `__main__` 执行

最初 `mcp = FastMCP("ShillGuard")` 写在 `server.py` 里。两个阶段各执行一次 server.py 顶层代码 → 产生**两个 FastMCP 实例**。工具用 `@mcp.tool()` 装饰器注册在第一个实例上，但 `mcp.run()` 跑的是第二个（空的）实例 → 客户端看到 0 工具。

### 解决
把 FastMCP 单例移到包初始化文件 `app/mcp/__init__.py`：
```python
from mcp.server.fastmcp import FastMCP
mcp = FastMCP("ShillGuard")
```
`server.py` 和所有 tool 模块（`tools_rag`/`tools_moderation`/`tools_detect`）改成 `from app.mcp import mcp`，全项目共用一个实例。

---

## Bug 2：MCP 子进程 cwd 不对，RAG 找不到索引文件

### 现象
`rag_search_laws` 调用返回空/卡住。直接跑 `retrieve()` 却正常返回 3 条。

### 根因
MCP 客户端起子进程时，cwd 不一定是项目根。RAG 用相对路径 `./data/bm25_index.json`、`./chroma_dir`，cwd 不对就找不到索引文件，检索 silently 返回空。

### 解决
在 `server.py` 最顶部强制切到项目根：
```python
from pathlib import Path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
os.chdir(_PROJECT_ROOT)
```

---

## Bug 3：`rag_search_laws` 经 MCP 调用卡死 120 秒（最复杂，多因叠加）

### 现象
`test_mcp_client.py`：`initialize` 成功、`tools/list` 返回 4 个工具，但 `tools/call rag_search_laws` 卡满 120 秒超时。`test_retrieve_direct.py` 直接调 `retrieve()` 却 2 秒返回 3 条。**同一个函数，直接跑通，MCP 跑挂。**

### 排查过程（走过弯路）

#### 弯路 1：误判为 stdout 污染协议通道
**理论**：MCP stdio 模式下 `sys.stdout` 是 JSON-RPC 协议通道（SDK 源码 `mcp/server/stdio.py` 第 49 行 `TextIOWrapper(sys.stdout.buffer)` 确认）。任何 `print`/tqdm 写 stdout 会污染协议。

**尝试**：
1. `builtins.print` monkeypatch → 强制 `print()` 走 stderr。失败。
2. `os.dup2(stderr, 1)` + 自定义 `sys.stdout` 代理（`.buffer` 走管道、文本走 stderr）。失败。

**为什么没用**：`initialize`/`tools/list` 一直成功，说明协议通道没坏。卡的是工具执行，不是协议。修错方向。

#### 弯路 2：误判为线程死锁
**理论**：FastMCP 把 `def` 工具丢进 anyio 工作线程，torch 在非主线程加载模型死锁。

**尝试**：把 `rag_search_laws` 改成 `async def`，让它在主线程事件循环跑。失败，trace 一样卡在 `_get_reranker()`。

#### 关键转折：写文件 trace 看现场
不再猜，写 `app/mcp/_trace.py`（`trace()` 把带时间戳的行写进 `mcp_trace.log`，不经过 stdout/stderr），在 `retrieve()` 每一步和 `rerank()` 内部打点。

trace 结果一锤定音：
```
retrieve: RRF 后候选 5 条
retrieve: 调用 rerank
rerank: 即将 _get_reranker()（加载模型）   ← 最后一条，之后 120s 静默
```
卡点在 `_get_reranker()` 里加载 `FlagReranker` 模型。

### 真因 3.1：HuggingFace 联网校验超时
transformers/huggingface-hub 默认会向 `huggingface.co` 发 HEAD 请求校验 `tokenizer_config.json`。国内网络连不上，重试 5 次（指数退避 1+2+4+8+8 秒 + 5×10s 连接超时 ≈ 70-120 秒），正好对上 120s 超时。

### 真因 3.2：transformers 5.0 移除了 `prepare_for_model`
直接跑时 reranker 加载完模型到 `compute_score` 报：
```
XLMRobertaTokenizer has no attribute prepare_for_model
```
- 实测环境版本：`transformers==5.13.0`、`tokenizers==0.22.2`、`huggingface-hub==1.21.0`、`FlagEmbedding==1.4.0`、`torch==2.7.1+cu118`、reranker 模型 `BAAI/bge-reranker-v2-m3`。
- `prepare_for_model` 是 tokenizer 的老 API，在 **transformers 5.0 被移除**（官方 `MIGRATION_GUIDE_V5.md` "Removed Methods" 列表确认）。`bge-reranker-v2-m3` 基于 XLM-RoBERTa，其 tokenizer 加载路径仍调用这个老 API → `AttributeError`。
- `retrieve()` 里 `try/except` 捕获后降级用 RRF 结果，所以**直接跑"看起来正常"，其实 reranker 没干活**。
- MCP 子进程里则表现为挂起（见真因 3.3）。

### 真因 3.3：无控制台子进程里 `import torch` 挂死
MCP 客户端用 `CREATE_NO_WINDOW` 标志起子进程（`mcp/os/win32/utilities.py` 第 173 行确认），无控制台窗口。在这个环境里 `from FlagEmbedding import FlagReranker`（会 import torch）**卡在 import 阶段挂死**，连 `CUDA_VISIBLE_DEVICES=""`、`use_fp16=False` 都救不了（卡点在 import，还没到 CUDA 初始化/模型构造）。

**验证**：细粒度 trace 显示 `_get_reranker: 即将 import FlagEmbedding` 之后完全静默，import 这一行就挂了。

### 修复尝试（按顺序）

#### 尝试 A：`use_fp16=False`（CPU 推理）
**意图**：绕开 CUDA 初始化。
**结果**：失败。卡点在 import FlagEmbedding，`use_fp16` 参数在构造阶段才生效，根本走不到。

#### 尝试 B：`CUDA_VISIBLE_DEVICES=""`
**意图**：让 torch 看不到 GPU，不触发 CUDA 初始化。
**结果**：失败。卡点在 import torch 本身，与 CUDA 可见性无关。

#### 尝试 C：移除 dup2/stdout 代理
**意图**：排除代理 `fileno()` 返回管道 fd 干扰 torch。
**结果**：失败。卡点不变。

### 真正解决 3.1：transformers 降级
查依赖约束（不靠猜）：
- `sentence-transformers 5.6.0` 要求 `transformers>=4.41.0,<6.0.0`
- `FlagEmbedding 1.4.0` 要求 `transformers>=4.44.2,<6.0.0`
- FlagEmbedding 官方维护者在 issue #1266 明确推荐 `transformers==4.46.0`

执行（在你的 agent 环境）：
```bash
pip install "transformers==4.46.0" -i https://pypi.tuna.tsinghua.edu.cn/simple
```
结果：`transformers 5.13.0→4.46.0`、`tokenizers 0.22.2→0.20.3`、`huggingface-hub 1.21.0→0.36.2`（自动跟着降，因 4.46 要求 huggingface-hub<1.0）。

直接跑 `test_retrieve_direct.py`（设 `TRANSFORMERS_OFFLINE=1 HF_HUB_OFFLINE=1`）→ `[RAG-DEBUG] 重排序完成: 返回3条`，reranker 真正生效，结果经 cross-encoder 精排。

### 真正解决 3.2：离线模式
在 `server.py` 顶部（任何 HF 相关 import 之前）设：
```python
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_OFFLINE"] = "1"
```
跳过联网校验，直接用本地模型缓存。

### 真正解决 3.3：MCP 路径跳过 reranker
torch import 在无控制台子进程里挂死是**环境硬限制**（CREATE_NO_WINDOW 由 MCP SDK 决定，改不动）。所以 MCP 路径直接跳过 reranker，用 RRF 融合结果：

`server.py`：
```python
os.environ["SHILLGUARD_DISABLE_RERANK"] = "1"
```
`retriever.py` 的 rerank 步骤：
```python
if os.environ.get("SHILLGUARD_DISABLE_RERANK"):
    return candidates[:top_k]   # 直接返回 RRF 结果，不 import FlagEmbedding/torch
```

### 最终架构（按环境能力做能力降级）
| 路径 | 检索流程 | reranker | 原因 |
|---|---|---|---|
| MCP（Cursor 调用） | 向量+BM25+RRF | 跳过 | 无控制台子进程 import torch 挂死 |
| FastAPI（审核/检测服务） | 向量+BM25+RRF+cross-encoder 精排 | 启用 | 终端启动有控制台，torch import 正常 |

### 验证
`test_mcp_client.py` 返回 3 条法律条款，~3 秒：
```
=== 调用返回 ===
isError=False, content数=1
text: # 最高人民法院、最高人民检察院、公安部关于依法惩治网络暴力违法犯罪的指导意见 ...
```

---

## Bug 4：Cursor 不自动调用 MCP 工具，走了网络搜索

### 现象
重启 Cursor 后，Chat 里发"帮我查一下网络暴力相关的法律法规条款"，Cursor **没有调用 `rag_search_laws`**，而是用了网络搜索回答。

### 根因
1. **docstring 写得太窄**：原 docstring 反复强调"判断某条内容是否违规""审核依据"，把工具框成"审核流程专用"，通用法规查询匹配不上。
2. **模型预训练先验偏向网络搜索**：LLM 训练数据里见过海量"网络搜索"模式，几乎没见过私有 MCP JSON-RPC 调用。查询类任务模型倾向走网络搜索或自己答。
3. **MCP 生态无标准优先级机制**：经调研（GitHub issue #1537），Claude Code/Cursor/Cline/Roo Code 均无工具优先级配置。模型靠 name+docstring+schema+系统指令自回归决策。
4. **任务"看似可由训练数据回答"**：AgenticMarket 文章原话——"If the task seems answerable from training data, they'll skip the tool entirely."

### 解决

#### 4.1 重写 `rag_search_laws` docstring（宽化 + 不可替代性）
- 列出适用场景（含"查询某类违法行为相关法律条款，例如网络暴力…"，直接命中测试 prompt）
- 去掉"不是网络搜索"这种劝退话术
- 加"涉及法律法规的问题请优先调用本工具，而不是凭模型记忆回答"
- 加"平台自建治理规定是私有数据，网络搜索无法获取，必须用本工具检索"

#### 4.2 新建 Cursor 规则文件 `.cursor/rules/shillguard-mcp.mdc`
```yaml
---
description: ShillGuard MCP 工具优先级——法律/审核/检测类问题优先用本地 MCP 工具，而非网络搜索
alwaysApply: true
---
```
正文用命令式 Markdown 明确 4 个工具的触发场景，核心规则："法律/规则类问题 → 必须调 `rag_search_laws`，不要用网络搜索"。

**关键认知**：
- `.mdc` 规则是**项目级**的，放 `.cursor/rules/`，跟 mcp.json 在用户级还是项目级**无关**。
- `alwaysApply: true` 表示每个会话都自动加载，优先级高于 docstring。
- 规则在**会话启动时**加载，改了规则要**完全重启 Cursor** 才生效。

### 调研结论：MCP 工具被选中的影响因素（按权重）
1. 工具元数据质量（name + docstring + schema），动作型命名 + "use when..." 描述
2. 模型预训练先验（对网络搜索/CLI 更熟练）
3. 系统提示/规则（`.cursor/rules/*.mdc`，能强制倾斜）
4. 显式信号（prompt 里点名工具名，几乎 100% 触发）
5. 工具预算上限（Cursor ~40-80 个，超出静默排除；本项目 4 个，不是问题）

---

## 最终保留的修复清单

### `app/mcp/server.py`
| 代码 | 作用 |
|---|---|
| `os.chdir(_PROJECT_ROOT)` | MCP 子进程 cwd 修正，RAG 能找到索引 |
| `TRANSFORMERS_OFFLINE=1` + `HF_HUB_OFFLINE=1` | 跳过 HF 联网校验，用本地缓存 |
| `SHILLGUARD_DISABLE_RERANK=1` | MCP 跳过 rerank（无控制台子进程 import torch 挂死），走 RRF |
| `builtins.print` → stderr | 防止 print 污染 stdio JSON-RPC 协议通道 |

### `app/mcp/__init__.py`
- `mcp = FastMCP("ShillGuard")` 单例，解决 `python -m` 双重导入

### `app/mcp/tools_rag.py`
- `async def rag_search_laws`（主线程事件循环跑）
- 宽化 docstring + 不可替代性说明

### `app/rag/retriever.py`
- `import os` + `SHILLGUARD_DISABLE_RERANK` 检查（MCP 跳过 rerank，FastAPI 走完整精排）

### `app/main.py`（FastAPI 入口）
- `TRANSFORMERS_OFFLINE=1` + `HF_HUB_OFFLINE=1`（FastAPI reranker 也走本地缓存）

### `.cursor/rules/shillguard-mcp.mdc`
- `alwaysApply: true`，4 个工具的优先调用规则

### 环境变更
- `transformers 5.13.0 → 4.46.0`（修 `prepare_for_model` 报错，FastAPI reranker 复活）
- 连带：`tokenizers 0.22.2→0.20.3`、`huggingface-hub 1.21.0→0.36.2`

---

## 遗留问题

### reranker 的 transformers 版本兼容（已修但记录）
`transformers 5.0` 移除 `prepare_for_model`，`bge-reranker-v2-m3` 的 XLM-R tokenizer 路径报错。降级到 `4.46.0` 解决。若未来想升回 transformers 5.x，需等 FlagEmbedding 出完全兼容 v5 的版本（1.4.0 已做部分 v5 兼容 PR #1563，但 XLM-R prepare_for_model 路径未覆盖），或改用 `sentence_transformers.CrossEncoder` 重写 `rerank()` 绕开该路径。

### MCP 路径无 reranker（设计取舍）
MCP 子进程无控制台 → import torch 挂死 → MCP 只能走 RRF 召回融合，无 cross-encoder 精排。FastAPI 路径不受影响。这是 MCP SDK `CREATE_NO_WINDOW` 决定的环境限制，非代码可解决。

---

## 排查方法论复盘

1. **死锁/卡死类问题，先用无侵入执行轨迹确认卡点，再谈理论**——写文件 trace（不走 stdout/stderr）是关键手段，比凭经验猜方向高效得多。
2. **"同一函数两副面孔"通常不是函数本身的问题，而是执行环境差异**——主线程 vs 工作线程、有控制台 vs 无控制台、cwd、网络可达性、依赖版本，逐项排查。
3. **多个独立问题叠加时，要分开归因**——本次 transformers 版本问题（归 FastAPI reranker）和子进程环境问题（归 MCP reranker）是两个独立 bug，一度误以为是同一个，浪费了多轮。
4. **改依赖版本前先查约束**——`importlib.metadata.requires()` 查 sentence-transformers/FlagEmbedding 对 transformers 的版本要求，避免降一个炸一个。
5. **MCP 工具不被自动调用，先查元数据 + 加规则文件**——Cursor 无标准优先级机制，`.cursor/rules/*.mdc` 是当前最有效的强制倾斜手段。
