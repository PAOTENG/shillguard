# ShillGuard 优化完整实现方案（2026 主流栈）

> 版本：2026-08 修订版  
> 前提：不强制 A2A；多 Agent 以 **LangGraph Supervisor–Worker** + **Hermes Kanban** 为主。  
> 评测：面向 **Agent 领域主流 Benchmark** + **自建领域 Eval**（非 MarkBench / 非以 MCPMark 为主）。  
> 状态：方案文档，待你确认「请实现代码」后再改仓库。

---

## 0. 一句话目标

在保留现有业务 Agent（审核 / 检测 / Chat / RAG / MCP）的前提下，增加 **Coding Agent（选用 Pi SDK，不用 Cursor SDK）+ MCP 工具复用 + 主流多 Agent 编排（Supervisor–Worker / Hermes Kanban）**，并用 **Agent 领域公开 Benchmark（子集）+ ShillGuard 领域套件** 量化效果。

**Coding 壳选型结论：Pi（`@earendil-works/pi-coding-agent`），不用 Claude Code 当 SDK 主线、不用 Cursor SDK。**  
理由见 §1.0。

---

## 1. 2026 推荐技术栈（选型表）

### 1.0 Coding：为什么选 Pi 而不是 Claude Code（CC）

| 维度 | **Pi（选定）** | Claude Code（CC） |
|------|----------------|-------------------|
| 形态 | 开源 harness + **正式 SDK**（`createAgentSession` / `defineTool` / MCP） | 产品型 CLI Coding Agent，生态极大 |
| 二次开发 | **适合**：嵌脚本、CI、自研小入口、自定义 Tool | 更适合人在终端里用；可编程集成不是主叙事 |
| MCP | SDK/配置可挂 MCP | 原生支持 MCP（也可经 CC Switch 管配置） |
| 与 Hermes Kanban | Pi 跑自动化任务；Hermes 管看板多 profile | CC 可做人机改码，但和「SDK 方案」叠床架屋 |
| 本项目匹配度 | 你要的是「用 SDK 二次开发 + Tool/MCP」→ **Pi** | 若只每天手改代码，CC 够用，但不是本方案主线 |

**结论：Coding 壳 = Pi SDK。**  
CC 不作为实现主线（可个人日常用，不写进本方案必装清单）。配置面板若需要，仍可用 **CC Switch** 给 Hermes/其它 CLI 同步 MCP，与「是否用 CC 本体」无关。

| 层级 | 推荐（主流） | 备选 | 本项目用法 | 不推荐 / 后置 |
|------|--------------|------|------------|----------------|
| 域内编排 | **LangGraph** | — | 保持并产品化现有审核/Chat/证据图 | 用 CrewAI 整站重写 |
| 多 Agent 协作（同机持久） | **Hermes Kanban** | LangGraph 子 Agent | Orchestrator 拆卡 → coder / reviewer / eval-runner | 一上来上 A2A |
| 跨框架 Agent 协议 | （可选）A2A | — | 第三期再考虑 | 本期不做 |
| 工具协议 | **MCP** | Function Calling | 现有 FastMCP 四工具 + 加固 | 为每个 CLI 写私有插件 |
| Coding 壳 | **Pi SDK** + **Hermes**（Kanban/人机） | Claude Code 仅个人日常 | Pi：`createAgentSession`+MCP+自定义 Tool；Hermes：看板 | Cursor SDK；CC 当 SDK 主线 |
| 配置分发 | CC Switch（可选） | 手改 json | 统一 MCP 到 Hermes 等 | 把 CC Switch 当成 Agent |
| 记忆 | Checkpointer + 摘要 + mem0 | — | 已有 Chat 三层记忆 | — |
| 异步 | RabbitMQ + Redis task | — | 已有审核异步 | — |
| 观测 | **LangSmith** | Phoenix | 多 Agent / MCP 轨迹 | 只靠 print |
| 公开 Agent 评测 | **SWE-bench Verified（子集）** + **AgentBench（子集）** + （可选）**GAIA / τ-bench** | Terminal-Bench、BFCL | 证明通用 Agent/Coding 能力 | 只刷一个榜当全部 |
| 运行时配置评测 | **HermesBench**（若上 Hermes） | 自建 Kanban 闭环脚本 | 测 Kanban 委托能否闭环 | — |
| 业务评测 | **ShillGuard-AgentEval（自建，必做）** | — | 审核/检测/RAG/MCP 选对 | 用公开榜替代业务指标 |

### 1.1 为什么这样选

- **LangGraph**：你已有生产级图；2026 招聘/工程仍是编排主流，继续加深比换框架划算。  
- **Hermes Kanban**：2026 开源侧多 Agent「持久看板 + 多 profile 进程」的代表形态；Supervisor 拆任务、Worker 领卡，比脆弱 in-process swarm 更稳。  
- **MCP**：Agent↔工具事实标准；业务能力只维护一份 Server。  
- **Pi SDK**：开源 Coding Agent 里最契合「二次开发」的可编程入口（session、自定义 Tool、MCP、extensions）；满足「不用 Cursor SDK、在 CC 与 Pi 里二选一」时的工程目标。  
- **Benchmark**：按能力切片——Coding 看 SWE-bench，综合交互看 AgentBench，通用助手可选 GAIA，多轮政策可选 τ-bench；**业务效果必须自建**。

---

## 2. 目标架构

```
┌─────────────────────────────────────────────────────────────────┐
│ 入口：人 / CI /（可选）Admin 按钮                                  │
└────────────────────────────┬────────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ 治理编排层（二选一或组合）                                          │
│  A) Hermes Orchestrator + Kanban（多 profile 持久协作）            │
│  B) Pi SDK Supervisor 脚本（createAgentSession + MCP + 触发评测）    │
└───────────────┬─────────────────────────────┬───────────────────┘
                │ MCP                         │ Kanban 领卡
                ▼                             ▼
┌───────────────────────────┐   ┌─────────────────────────────────┐
│ ShillGuard MCP Server     │   │ Workers（Hermes profiles）       │
│ rag_search_laws           │   │ · coder：改 prompts/cascade/eval │
│ moderate_content          │   │ · reviewer：读 diff/建议         │
│ detect_user_score         │   │ · eval-runner：跑评测套件        │
│ generate_evidence         │   └─────────────────────────────────┘
└─────────────┬─────────────┘
              │ 内部
              ▼
┌───────────────────────────┐
│ 业务多 Agent（LangGraph）   │
│ Supervisor/路由 + Workers   │
│ 审核级联 / Chat∥RAG / 证据  │
└─────────────┬─────────────┘
              ▼
     线上：Java → HTTP /ai/*（不变）

评测层：
  · 公开：SWE-bench Verified 子集 | AgentBench 子集 |（可选）GAIA/τ-bench
  · 运行时：HermesBench / Kanban 闭环
  · 业务：ShillGuard-AgentEval（主指标）
  · 观测：LangSmith
```

### 2.1 多 Agent 模式怎么落（本期）

| 模式 | 落点 |
|------|------|
| Supervisor–Worker | ① LangGraph 业务图内；② Hermes Orchestrator 只拆卡不干活 |
| Pipeline | Kanban：`scout(查法/读代码) → implement → review → eval` |
| Fan-out | Kanban：多样本并行 moderate / 多角度规则调研 |
| Human-in-the-loop | 改生产策略、禁言类动作：看板 blocked → 人评论解锁 |
| A2A | **本期不做** |

---

## 3. 评测体系（Agent 领域 Benchmark + 自建）

### 3.1 公开 Benchmark（证明「会 Agent」）

| 套件 | 作用 | 落地建议 |
|------|------|----------|
| **SWE-bench Verified** | Coding Agent 金标 | 跑 **小子集**（如 10～50 题）或官方 lite 流程；宿主用 **Pi SDK** / Hermes coder profile |
| **AgentBench** | 综合多环境 Agent | 选 **1～2 个环境子集**（如 DB / OS / Web 中与你栈接近的），不求刷满 8 环境 |
| **GAIA**（可选） | 通用多步+工具 | 若治理编排含「调研+汇总」再跑 validation 子集 |
| **τ-bench / τ²**（可选） | 多轮+政策遵守 | 若以后做「模拟运营对话下发审核」再上 |
| **HermesBench**（若用 Hermes） | 配置/Kanban 可靠性 | 打开与 delegation/Kanban 相关的 runtime suite（如 delegated_closure） |

原则：公开榜 **子集 + 可复现命令 + 记录模型与脚手架版本**；不宣称「全面 SOTA」。

### 3.2 ShillGuard-AgentEval（必做，主指标）

学公开榜的「任务 + 自动判定」，自建：

```text
eval/shillguard_agent_eval/
  cases/           # instruction + expected + fixtures
  verifiers/       # 程序断言（分数带、action、tool 名、法条关键词）
  runners/         # 调 MCP / HTTP /（可选）经 Hermes/SDK
  reports/         # pass@1、分项、轨迹 id
```

**任务分层：**

| ID | 测什么 | 判定 |
|----|--------|------|
| E1 | 单 MCP 工具选对并成功 | tool 名 + 关键字段 |
| E2 | 多工具编排（查法→审核） | 顺序/结果断言 |
| E3 | LangGraph 级联/路由 | 终态 action、是否短路 |
| E4 | Kanban Pipeline 闭环 | 卡状态 done + eval 报告生成 |
| E5 | Coding 改夹具→分数变化 | git 可回滚 + 分数相对基线 |

指标：`pass@1`、（重要任务）`pass@3`、平均步数/tool calls、延迟、（可选）成本；业务另报：级联短路率、灰区占比。

### 3.3 和公开榜的关系（写进文档防踩坑）

- SWE-bench 高 ≠ 审核准。  
- AgentBench 高 ≠ Kanban 稳。  
- **上线/验收以 ShillGuard-AgentEval 为准**；公开榜作能力背书。

---

## 4. 分阶段实现计划

### 阶段 0：冻结决策（0.5 天）

1. Coding 主线：**Pi SDK**（脚本/CI/二次开发）+ **Hermes**（Kanban/人机）。  
2. 公开评测最小集：**SWE-bench Verified 子集 + AgentBench 1 环境子集**；有余力再加 GAIA。  
3. 安全：Coding/Kanban **禁止**直接调生产禁言；只动 `eval/`、`demos/`、prompts 草稿或明确白名单路径。

### 阶段 1：MCP 加固（3～5 天）

- 统一启动：`python -m app.mcp.server` + env（Windows 硬化沿用）。  
- Tool 说明书（入参/出参 JSON 样例）。  
- （建议）只读评测 Tool：`run_fixture_moderate` / `get_task_status`。  
- Pi / Hermes /（可选）CC Switch 同一份 MCP 配置。

**出口：** Pi 与 Hermes 各成功调用 4 工具一次。

### 阶段 2：业务多 Agent 产品化（LangGraph）（3～5 天）

- 角色卡：Cascade / Retrieve / Judge / Evidence / Chat-Worker / Chat-Main / Detect。  
- 统一超时、降级、LangSmith 项目名。  
- 导出节点级指标（可接现有 `cascade_metrics.jsonl`）。

**出口：** 一张「Supervisor–Worker 角色表」+ 示例 trace。

### 阶段 3：Pi Coding Agent SDK（5～7 天）

目录（旁路）：`demos/governance_coding_agent/`

依赖：`npm install @earendil-works/pi-coding-agent`（文档：[pi.dev/docs/latest/sdk](https://pi.dev/docs/latest/sdk)）。

- `run_oneshot`：`createAgentSession` + `session.prompt`，只读分析仓库。  
- `run_with_mcp`：会话挂载 ShillGuard MCP，跑 E1/E2 类任务。  
- `defineTool`：仅 `/health`、读最新 eval 报告等薄胶水（领域能力走 MCP）。  
- prompt 模板：规则工程剧本 5 条。

**出口：** 一条 cmd 命令跑通「查法 → moderate → 出结构化摘要」。

### 阶段 4：Hermes Kanban 多 Agent（5～7 天）

Profiles 建议：

| Profile | 职责 |
|---------|------|
| `orchestrator` | 只拆卡、验收，不写业务大段代码 |
| `coder` | 改白名单路径 + 用 MCP 抽检 |
| `reviewer` | 对照 AgentEval 期望读 diff |
| `eval-runner` | 跑 `shillguard_agent_eval` / 公开子集脚本 |

看板流水线示例（Pipeline）：

1. scout：MCP 抽检 + 读 cascade  
2. implement：改 fixture/prompt 草稿  
3. review：评论通过/打回  
4. eval：跑 E 系列，结果贴回卡片  

**出口：** 一次用户目标从「建卡」到「eval 报告」全自动或半自动闭环；可选跑 HermesBench delegation 相关套件。

### 阶段 5：Benchmark 接入（7～10 天，可与 3/4 并行）

1. **ShillGuard-AgentEval v0**：先 20 条（E1–E3），verifier 脚本化。  
2. **SWE-bench Verified 子集**：固定题目列表、固定模型、记录 scaffold（Pi SDK vs Hermes）。  
3. **AgentBench 子集**：选 1 环境，跑通官方/社区 runner，存原始日志。  
4. （可选）GAIA validation 小样；HermesBench。  
5. 汇总报告模板：`reports/YYYYMMDD_summary.md`（公开子集分数 + 领域 pass@1 + Kanban 闭环是否通过）。

**出口：** 一键或「两条命令」生成汇总报告。

### 阶段 6：固化（3～5 天）

- `scripts/run_all_evals.cmd`（Windows cmd）。  
- CI：PR 跑 E1–E2；夜间跑 E3–E5 + 公开子集。  
- 文档：架构、复现、边界（线上 Java 路径不变）。

---

## 5. 目录规划（实现时建议）

```text
shill-guard-ai/
  demos/
    governance_coding_agent/     # Pi SDK 脚本
  eval/
    shillguard_agent_eval/       # 领域主评测
    public_bench/                # 包装 SWE-bench / AgentBench 子集的说明与锁定题目
  docs/ 或 技术文档汇总/         # 本方案与复现手册
  app/mcp/                       # 仅做加固与可选新 Tool（少动核心图）
```

核心 `app/agents/**` 以「指标与文档化」为主，避免为赶时髦大重构。

---

## 6. 成功标准（验收）

| 项 | 标准 |
|----|------|
| MCP | Pi SDK 与 Hermes 均可稳定调 4 工具 |
| 多 Agent | LangGraph 角色清晰；Kanban 至少 1 条 Pipeline 闭环 |
| 领域 Eval | ≥20 任务，E1–E3 可复现；报告含 pass@1 |
| 公开 Benchmark | SWE-bench 子集 + AgentBench 子集各至少完整跑通 1 次并留档 |
| 安全 | 无 Coding/Kanban 直连生产禁言 |
| 线上 | Java→`/ai/*` 行为不回归 |

---

## 7. 你需要准备的东西（修订清单）

### 7.1 账号与密钥

- [ ] 主 LLM API +（可选）便宜模型（Worker/评测）  
- [ ] Pi 所用模型/Provider 密钥（按 Pi ModelRuntime 文档配置）  
- [ ] Hermes 所用模型通道（直连或 OpenRouter 等）  
- [ ] 现有 Embedding / Rerank /（可选）阿里云绿网  
- [ ] LangSmith  

### 7.2 环境

- [ ] conda `agent`、本仓可 `run.py`  
- [ ] **Docker Desktop**（跑公开 Benchmark 环境强烈建议）  
- [ ] 内存 ≥16GB 推荐  
- [ ] Node.js（Pi SDK / 部分 bench 工具链）  
- [ ] Git；评测机固定依赖版本  

### 7.3 软件

- [ ] Hermes Agent（Kanban）  
- [ ] `@earendil-works/pi-coding-agent`（Pi SDK）  
- [ ] （可选）CC Switch；Claude Code 不作为本方案必装  
- [ ] SWE-bench Verified 官方/社区 runner  
- [ ] AgentBench 仓库与依赖  
- [ ] （可选）GAIA、τ-bench、HermesBench  

### 7.4 设计产物

- [ ] 本架构图（已定稿可直接用本节）  
- [ ] MCP Tool 说明书  
- [ ] Kanban profile 与流水线定义  
- [ ] AgentEval 20 条任务规格  
- [ ] 公开子集「锁定题目列表」防每次换题无法对比  

### 7.5 数据

- [ ] 审核/检测黄金集（含期望 action/分数带）  
- [ ] RAG 抽检问句  
- [ ] 可回滚的 `eval/fixtures`  

### 7.6 明确不做（本期）

- [ ] A2A 跨框架互联  
- [ ] 用公开榜替代业务验收  
- [ ] CrewAI/AutoGen 替换 LangGraph  
- [ ] Coding Agent 接管线上禁言主路径  

---

## 8. 工期直觉（单人）

| 阶段 | 约 |
|------|-----|
| 0～2 | 1.5～2 周 |
| 3～4 | 1.5～2 周 |
| 5～6 | 1.5～2 周 |
| **合计** | **约 5～6 周**到可演示+有分数 |

若砍公开榜只留 SWE 小子集 + 领域 Eval，可压到约 4 周。

---

## 9. 与旧方案差异（修订说明）

| 旧方案 | 新方案 |
|--------|--------|
| 强调 A2A | **取消必选**；改 Hermes Kanban + LangGraph Supervisor–Worker |
| 主评测 MCPMark/MarkBench | 改为 **Agent 领域主流：SWE-bench + AgentBench（+可选 GAIA/τ/HermesBench）** |
| 业务评测 ShillGuard-Mark | 更名为 **ShillGuard-AgentEval**，仍为验收主指标 |
| Coding 用 Cursor SDK | **改为 Pi SDK**（CC 与 Pi 二选一后的结论） |
| 技术栈发散 | **收敛：LangGraph + MCP + Pi SDK + Hermes Kanban + LangSmith** |

---

## 10. 下一步

你确认本方案后，实现顺序建议：

1. 阶段 1 MCP 加固 + 阶段 3 **Pi SDK** demo（最快可见）  
2. 阶段 5 领域 Eval v0（有分数）  
3. 阶段 4 Kanban  
4. 阶段 5 公开 Benchmark 子集  

回复「请实现代码」并指定从阶段几开始即可开工。
