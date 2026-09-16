# 理想结果说明书

## A. 滑动窗口（当前策略）——应「失败」

目的：证明问题可稳定复现，不是偶发。

| 字段 | 期望 |
|---|---|
| `half_hit_possible_rate` | = 1.0 |
| `intact_in_single_chunk_rate` | = 0.0 |
| `sliding_window_failure_reproduced_rate` | ≥ 0.80（当前实测 1.0） |

单条用例期望（见 `test_cases.json` → `sliding_window_expected`）：

- `article_intact_in_top_chunk = false`
- `half_hit = true`
- 症状：命中相关前半段，缺锚点/罚则，易错引邻近条款

### 典型报错样例（人工可读）

以 `CB-001` / `NV-18` 为例：

- 问：跟帖评论、弹幕、点赞相关规定  
- 固定窗口 top chunk：只有「第十八条……制作、复制、发布、传播」前半句  
- **缺少**：删除/屏蔽/关闭评论等处置 + `【切分锚点-NV18】`  
- **风险**：模型可能改引第十七条视听节目条款，或只写「加强管理」而无措施  

以 `CB-028` 附近 / `SPC-500` 为例：

- 问：转发次数门槛  
- top chunk：只有「五百次以上……完整口径见后半段」  
- **缺少**：五千次点击/浏览与五百次转发的并列完整表述 + 锚点  
- **风险**：五百/五千写反或只写一个门槛  

## B. 父子切分（目标策略）——应「成功」

实现后，对同一 `test_cases.json`：

| 检查 | 理想阈值 |
|---|---|
| parent 含 `expected_full_article` | ≥ 90% |
| parent 含 `must_include_anchor` | ≥ 90% |
| 半条失败复现率（同 A 的判定逻辑，但上下文改为 parent） | ≤ 10% |

业务侧理想现象：

- 证据里处置措施/罚则档/告诉程序/并列门槛等 **不再残缺**  
- 不再把诱饵条款（如第十七条）当成主依据  

## C. 和 RAGAS 的关系（避免误用）

- **Context Recall**：法名关键词在半条里也可能命中 → **不一定掉**  
- **Faithfulness / 你们的 citation 名称校验**：半条里已有法名时仍可能高分 → **抓不住「条不全」**  
- 本套件主指标是：**完整条款是否进入生成上下文**（`expected_full_article` / `must_include_anchor`）

## D. 回归命令速查

```bat
cd /d d:\project\shill-guard-ai
D:\Environment\Anaconda\envs\agent\python.exe -m eval.chunk_boundary_suite.run_chunk_integrity
```

退出码 `0` = 滑动窗口失败模式已复现（套件自检 PASS）。  
父子落地后应另写对照脚本，期望该失败率下降，而不是继续为 100%。
