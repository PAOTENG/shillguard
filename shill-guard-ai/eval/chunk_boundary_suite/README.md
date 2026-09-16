# chunk_boundary_suite · 固定窗口切分对抗评测集

独立目录，**不写入** `app/rag/sources/`，避免污染主法规库。

## 要证明什么

固定长度滑动窗口（与线上一致：`chunk_size=500`, `overlap=50`, `step=450`）会把完整法条切成 HEAD|TAIL：

1. HEAD 含检索关键词 → 容易被命中  
2. TAIL 含处罚/要件 + `【切分锚点-xxx】` → 不在同一 chunk  
3. 结果：检索「命中相关片段」，但上下文缺后半段 → 证据易**条款不完整或张冠李戴**

## 目录结构

```text
eval/chunk_boundary_suite/
  config.json                 # 切分参数与门禁
  chunk_utils.py              # 与 indexer 同款切分
  build_adversarial_docs.py   # 生成对抗法规
  build_test_cases.py         # 生成测试用例
  run_chunk_integrity.py      # 离线复现「半条命中」（不需 LLM）
  run_retrieve_probe.py       # 可选：真实向量检索探针
  sources/*.md                # 13 部对抗法规（每条一文件）
  manifest.json               # 条款元数据
  test_cases.json             # 39 条查询用例
  reports/                    # 评测输出
  README.md                   # 本文件
  EXPECTED_RESULTS.md         # 理想结果说明
```

## 测试命令（Windows cmd）

```bat
cd /d d:\project\shill-guard-ai

REM 1) 生成对抗法规（精确跨 500 字边界）
D:\Environment\Anaconda\envs\agent\python.exe -m eval.chunk_boundary_suite.build_adversarial_docs

REM 2) 生成测试用例（每条款 3 问：精确/口语/易混，共 39 条）
D:\Environment\Anaconda\envs\agent\python.exe -m eval.chunk_boundary_suite.build_test_cases

REM 3) 离线完整性评测（核心：应 PASS = 滑动窗口失败被复现）
D:\Environment\Anaconda\envs\agent\python.exe -m eval.chunk_boundary_suite.run_chunk_integrity

REM 4) 父子切分评测（对照基线；应 PASS = parent 覆盖完整条款）
D:\Environment\Anaconda\envs\agent\python.exe -m eval.chunk_boundary_suite.run_parent_child_integrity

REM 4b) A/B 总对比：固定窗口 vs 父子（离线必跑 + 可选真实向量检索）
D:\Environment\Anaconda\envs\agent\python.exe -m eval.chunk_boundary_suite.run_ab_compare

REM 5) 可选：真实 embedding 检索探针（需配置 embed_api_key）
D:\Environment\Anaconda\envs\agent\python.exe -m eval.chunk_boundary_suite.run_retrieve_probe

REM 6) 全库重建索引（Child→Chroma/ES，Parent→data/rag_parents.json）
D:\Environment\Anaconda\envs\agent\python.exe -m app.rag.indexer
```

## 当前离线跑分（滑动窗口）

| 指标 | 结果 | 含义 |
|---|---|---|
| 文档数 | 13 | 覆盖网暴/治安/刑法/个保/网安/生态/管理办法/指导意见/两高解释/民法典/平台规范/未成年人 |
| 用例数 | 39 | 每条款 × 3 种问法 |
| half_hit_possible | **100%** | 都能构造「只有前半段的 chunk」 |
| intact_in_single_chunk | **0%** | 没有任何单 chunk 装得下完整条款 |
| sliding_window_failure_reproduced | **100%** | 按 hooks 排序的 top chunk：有关键词、无全文、无切分锚点 |

报告文件：`reports/chunk_integrity_report.json`  
**固定窗口基线快照（防覆盖）**：`reports/baseline_fixed_window_500_50/`（含报告 + 当时用例/manifest/config）

## 报错长什么样（滑动窗口下的「坏结果」）

对任意 `test_cases.json` 中的用例，固定窗口下应出现：

- top chunk **含** `must_include_hooks` 中的词  
- top chunk **不含** `expected_full_article`  
- top chunk **不含** `must_include_anchor`（如 `【切分锚点-NV18】`）  
- 业务风险见每条 `sliding_window_expected.risk`（例如误引邻近第十七条、漏情节较重档、五百/五千写反等）

## 父子切分实测（已落地）

策略：`article_child_section_parent`（条级 Child + 节/邻条 Parent）

| 指标 | 固定窗口基线 | 父子切分 |
|---|---|---|
| intact（单块含完整条款） | **0%** | **100%**（child） |
| parent_cover_ok | n/a | **100%** |
| 半条失败率 | **100%** | **0%** |

报告：`reports/parent_child_integrity_report.json`  
快照：`reports/parent_child_article_section/`

详见 `EXPECTED_RESULTS.md`。

## 设计要点（为何能精准打中固定窗口）

1. 每条金条款拆成 **HEAD=90 字 + TAIL**，条款起点固定在 char **410**，切点在 **500**  
2. **query hooks 只出现在 HEAD**，不出现在 TAIL/诱饵段 → 关键词命中必落半条  
3. **切分锚点与完整罚则只在 TAIL** → 半条上下文必然缺关键依据  
4. 前后放置 **诱饵条款**（第十七条/十九条等）→ 半条时更容易张冠李戴  

## 注意

- 本套件法规带 `【切分锚点-xxx】`，**仅供评测**，不要当正式法条入库主 RAG。  
- 离线脚本不改 `app/rag/indexer.py`，只复用相同切分常数。  
- 实现父子切分后，请另建 collection 对照，勿覆盖生产 `shillguard_kg`。
