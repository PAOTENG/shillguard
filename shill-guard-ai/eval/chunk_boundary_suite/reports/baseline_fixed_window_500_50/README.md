# 基线快照：固定窗口 500/50

保存时间用途：后续改父子切分后做前后对比，避免 `reports/chunk_integrity_report.json` 被重跑覆盖。

## 本目录文件

| 文件 | 说明 |
|---|---|
| `chunk_integrity_report.json` | 固定窗口离线评测完整结果（主对比文件） |
| `test_cases.json` | 当时用的 39 条用例（保证对比同题） |
| `manifest.json` | 当时对抗条款元数据 |
| `config.json` | 切分参数与门禁 |

## 基线汇总（勿改数字，以 JSON 为准）

- 策略：`chunk_size=500`, `overlap=50`, `step=450`
- 用例数：39
- `half_hit_possible_rate`：1.0（100%）
- `intact_in_single_chunk_rate`：0.0（0%）
- `sliding_window_failure_reproduced_rate`：1.0（100%）
- 含义：对抗难例上，固定窗口稳定半条命中、无单块完整条款

## 对比时怎么用

1. 新策略跑完后得到新的 `reports/chunk_integrity_report.json`（或另存 `reports/parent_child_xxx/`）
2. 与本目录 `chunk_integrity_report.json` 的 `summary` / `results` 逐项对比
3. 理想：失败复现率从 100% 降到接近 0%；parent 上下文覆盖完整条款与锚点
