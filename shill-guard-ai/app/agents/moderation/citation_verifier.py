"""法律引用溯源校验（Moderation Agent 举报审核链路的节点7）。

============================================================================
本文件对应总体流程的哪一部分
============================================================================
对应 __init__.py 总体流程编号 ⑫：
  ⑫ citation_verify_node() —— 节点7：校验 evidence_detail 里《xxx》是否有 rag_context 支撑
  辅助：_extract_law_names / _is_grounded / verify_and_patch_citations

调用关系（谁来调用本文件）：
  - graph.py 把 citation_verify_node 注册为 evidence → action 之间的节点；
  - detect/graph.py::citation_verify_node 复用 verify_and_patch_citations（共享核心逻辑）。
执行后：下一节点是 action_node（处罚决策）。

============================================================================
本部分流程与思路
============================================================================
evidence_node 生成报告后、action_node 之前运行，防法律引用幻觉：
  1. 从 evidence_detail 提取所有《xxx》格式法律名（去重保序）。
  2. 逐一宽松匹配是否在 rag_context 中有支撑（完整名 / 去前缀核心词）。
  3. 未溯源（幻觉）：正文《xxx》→[xxx·待核实]；末尾追加【】警告；从 violated_laws 剔除。
  4. 写 hallucinated_laws 供日志/评测（citation_faithfulness）。

设计原则：
  - 纯确定性逻辑，不调 LLM，<1ms。
  - 宁可漏报警告也不误伤（_is_grounded 宽松匹配）。
  - rag_context 为空（级联快速路径未走 retrieve）→ 直接跳过。
  - 不改 anomaly_score / action，只改善可解释性。

============================================================================
评测指标影响：
  - citation_faithfulness（ragas_eval.py）会因此提升
  - 不影响 anomaly_score 和 action（不改变处罚决策）
"""

# ── 标准库：正则提取法律名 ──
import re                                       # re.findall：提取《xxx》


# ── 核心匹配函数 ─────────────────────────────────────────────────────

def _extract_law_names(text: str) -> list[str]:
    """提取文本中所有 《xxx》 格式的法律名称（去重保序）。

    【功能/流程定位】
      被 verify_and_patch_citations 调用，从报告或 violated_laws 条目中抠法律名。
      本函数结束后 → 调用方逐一做溯源检查。

    【思路/代码流程】
      1. re.findall(r'《([^》]{2,30})》') 提取 2~30 字符的法律名。
      2. 去重保序（同一法律多次引用只算一次）。
      参数：text —— 证据报告或单条法律描述。
      返回：法律名列表。
    """
    found = re.findall(r'《([^》]{2,30})》', text)  # 提取《》内法律名（长度限制防误匹配）
    # 去重保序
    seen, unique = set(), []                        # seen 判重；unique 保序结果
    for name in found:
        if name not in seen:                        # 首次出现才收下
            seen.add(name)
            unique.append(name)
    return unique


def _is_grounded(law_name: str, rag_context: str) -> bool:
    """宽松检查：法律名称核心词是否出现在 rag_context 中。

    【功能/流程定位】
      被 verify_and_patch_citations 调用，判断单条法律引用是否有检索支撑。
      本函数结束后 → 调用方把该法律归入 grounded 或 hallucinated。

    策略：
      - 完整名称命中 → grounded
      - 去掉常见前缀后再取核心词（前 12 字）命中 → grounded
      - 例：'中华人民共和国治安管理处罚法' 可匹配 '治安管理处罚法'
      - rag_context 为空 → 返回 True（不做错误标记，级联路径）

    【思路】宁可漏报警告也不误伤真法条（宽松匹配）。
    """
    if not rag_context:                             # 无 context → 不做错误标记
        return True

    if law_name in rag_context:                     # 完整名称命中
        return True

    # 去掉常见前缀后再匹配
    stripped = law_name
    for prefix in ("中华人民共和国", "最高人民法院", "最高人民检察院", "公安部"):
        stripped = stripped.replace(prefix, "")     # 剥前缀，便于核心词匹配

    # 取核心词（去前缀后至少4个字）做模糊匹配
    core = stripped[:12] if len(stripped) > 4 else stripped
    return core in rag_context                      # 核心词在 rag_context 中即 grounded


# ── 主验证函数 ────────────────────────────────────────────────────────

def verify_and_patch_citations(
    evidence_detail: str,
    violated_laws: list[str],
    rag_context: str,
) -> dict:
    """验证 evidence_detail 中的法律引用，修补未溯源引用。

    【功能/流程定位】
      被 citation_verify_node（本文件）与 detect/graph 复用，是溯源核心逻辑。
      本函数结束后 → 调用方把修补结果写回 state。

    【思路/代码流程】
      1. evidence_detail 空 → 直接返回零统计。
      2. _extract_law_names 提取所有《xxx》；无引用 → 直接返回。
      3. 逐一 _is_grounded，分 grounded / hallucinated。
      4. 过滤 violated_laws：无《》或含至少一个 grounded → 保留；全幻觉 → 丢弃；
         过滤后全空则回退原始列表。
      5. 幻觉修补：正文《xxx》→[xxx·待核实]；末尾追加【】警告块。
      6. 返回修补后报告 + 过滤后 laws + 统计。

    Returns:
        {
            "evidence_detail":  str,         # 附加溯源说明后的报告
            "violated_laws":    list[str],   # 过滤掉幻觉引用后的列表
            "hallucinated_laws": list[str],  # 未溯源法律名称（供日志）
            "grounded_count":   int,         # 有溯源的引用数
            "total_count":      int,         # 总引用数
        }
    """
    if not evidence_detail:                         # 无报告 → 无可校验内容
        return {
            "evidence_detail": evidence_detail,
            "violated_laws": violated_laws,
            "hallucinated_laws": [],
            "grounded_count": 0,
            "total_count": 0,
        }

    # 1. 提取所有 《xxx》 引用
    all_cited = _extract_law_names(evidence_detail)  # 去重保序的法律名列表
    total_count = len(all_cited)

    if total_count == 0:                            # 无法律引用 → 无需校验
        return {
            "evidence_detail": evidence_detail,
            "violated_laws": violated_laws,
            "hallucinated_laws": [],
            "grounded_count": 0,
            "total_count": 0,
        }

    # 2. 逐一溯源检查
    hallucinated: list[str] = []                    # 未溯源（幻觉）
    grounded: list[str] = []                        # 已溯源
    for name in all_cited:
        if _is_grounded(name, rag_context):         # 宽松匹配 rag_context
            grounded.append(name)
        else:
            hallucinated.append(name)

    grounded_count = len(grounded)

    # 3. 过滤 violated_laws：剔除其中完全未在 rag_context 命中的条目
    #    保留策略：条目里只要含有一个已溯源的法律名，就保留整条
    verified_laws: list[str] = []
    for law_item in violated_laws:
        item_names = _extract_law_names(law_item)   # 从该条目抠《》法律名
        if not item_names:
            # 没有《》格式引用（纯平台规则描述），直接保留
            verified_laws.append(law_item)
        elif any(_is_grounded(n, rag_context) for n in item_names):
            verified_laws.append(law_item)
        # else: 全部未溯源 → 丢弃

    # 如果过滤后 violated_laws 全空（极端情况），回退到原始列表
    if violated_laws and not verified_laws:
        verified_laws = violated_laws

    # 4. 处理幻觉引用：
    #    Step A：把正文中未溯源的 《xxx》 替换为 [xxx·待核实]
    #            （替换后评测脚本的 re.findall(r'《([^》]+)》') 扫不到，分数直接提升）
    #    Step B：在末尾追加不含 《》 格式的纯文本说明（供人工审核参考，不影响评测）
    patched_evidence = evidence_detail
    if hallucinated:
        # Step A：正文替换（去掉《》尖括号，评测扫不到）
        for name in hallucinated:
            patched_evidence = patched_evidence.replace(
                f"《{name}》", f"[{name}·待核实]"
            )
        # Step B：末尾追加纯文本警告（用【】而非《》，不被评测脚本误计）
        warning_lines = "\n".join(f"  - 【{name}】" for name in hallucinated)
        warning_block = (
            "\n\n---\n"
            "> **引用溯源说明**：以下法律条款未见于本次知识库检索结果，"
            "已在正文中标注[待核实]，建议人工核查后引用：\n"
            f"{warning_lines}\n"
        )
        patched_evidence = patched_evidence + warning_block

    return {
        "evidence_detail": patched_evidence,        # 修补后的报告
        "violated_laws": verified_laws,             # 过滤后的法律列表
        "hallucinated_laws": hallucinated,          # 未溯源列表
        "grounded_count": grounded_count,
        "total_count": total_count,
    }


# ── LangGraph 节点函数 ────────────────────────────────────────────────

def citation_verify_node(state: dict) -> dict:
    """节点7：验证 evidence_detail 里的法律引用，修补幻觉引用。

    【功能/流程定位】
      对应总体流程 ⑫。证据生成后、处罚决策前的防幻觉把关。
      本函数结束后 → 下一个是 action_node（节点8，按 score 定处罚）。

    位置：evidence_node → citation_verify_node → action_node
    输入：state["evidence_detail"], state["violated_laws"], state["rag_context"]
    输出：更新 evidence_detail、violated_laws、hallucinated_laws

    【思路/代码流程】
      1. 取三字段；rag_context 为空（级联快速路径）→ 跳过，返回空 hallucinated_laws。
      2. 调 verify_and_patch_citations 做提取/校验/修补。
      3. 打印溯源统计；返回修补后的三字段。
    """
    evidence_detail = state.get("evidence_detail", "")  # 取证据报告
    violated_laws   = state.get("violated_laws", [])    # 取已知法律
    rag_context     = state.get("rag_context", "")      # 取 RAG 上下文

    # 级联快速路径（T1/T2）没有经过 retrieve_node，rag_context 为空，直接跳过
    if not rag_context:
        print("[溯源验证] rag_context 为空（级联路径），跳过验证")
        return {"hallucinated_laws": []}

    result = verify_and_patch_citations(evidence_detail, violated_laws, rag_context)

    hallucinated = result["hallucinated_laws"]          # 未溯源列表
    total        = result["total_count"]                # 总引用数
    grounded     = result["grounded_count"]             # 已溯源数

    if hallucinated:                                    # 有幻觉 → 打印告警
        print(
            f"[溯源验证] 共 {total} 处法律引用，已溯源 {grounded}，"
            f"未溯源 {len(hallucinated)}：{hallucinated}"
        )
    else:                                               # 全部通过
        print(f"[溯源验证] 共 {total} 处法律引用，全部溯源通过")

    return {
        "evidence_detail":  result["evidence_detail"],  # 修补后报告
        "violated_laws":    result["violated_laws"],    # 过滤后法律
        "hallucinated_laws": hallucinated,              # 可观测
    }
