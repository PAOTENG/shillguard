# 父子切分 vs 固定窗口 A/B 对比报告

- 生成时间: 2026-07-30 17:16:58
- 用例数: 39
- 套件: `eval/chunk_boundary_suite`（对抗法规 13 篇 × 3 问法）

## 一、离线切分完整性（不调 embedding）

| 指标 | 固定窗口 500/50 | 父子 Child→Parent | 变化 |
|---|---:|---:|---:|
| 单块含完整条款率 | 0.0% | 100.0% | +100.0% |
| 注入上下文覆盖完整条款+锚点 | 0.0% | 100.0% | +100.0% |
| 半条失败率 | 100.0% | 0.0% | -100.0% |

## 二、真实向量检索（独立 chroma，child 命中后回填 parent）

| 指标 | 固定窗口 | 父子 |
|---|---:|---:|
| 注入上下文覆盖完整条款+锚点 | 0.0% | 97.4% |
| 仍失败用例数 | 39 | 1 |
| 相对固定窗口改善比例 | - | 97.4% |

## 三、结论门禁

- offline_passed: **True** （要求父子 context_cover≥90% 且 half_fail≤10%）
- retrieve_passed: **True** （若跑了检索，要求父子 cover≥80%）
- overall_passed: **True**

## 四、对照基线快照

- 固定窗口历史快照: `D:/project/shill-guard-ai/eval/chunk_boundary_suite/reports/baseline_fixed_window_500_50`
- 本报告目录: `D:/project/shill-guard-ai/eval/chunk_boundary_suite/reports/ab_compare`
