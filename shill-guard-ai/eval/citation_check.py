"""
Citation Integrity Check — 引用完整性 / 幻觉探测代理

背景：
  evidence_node 让 LLM 生成引用法条的报告，但 EVIDENCE_PROMPT 里
  没有传入 rag_context——LLM 凭记忆写法条，可能编一条不存在的法律。
  若引用了不存在的法条，对用户是法律风险 + 信任崩塌。

检测方法（确定性，无需 LLM）：
  1. 正则提取 evidence_detail 里所有 《XXX》 法条名
  2. 对每个名称，检查是否包含 KNOWN_LAWS 中的词条（子串匹配）
  3. 不包含的 = 幻觉引用 (hallucinated citation)

运行模式：
  快速模式（CI）：对预存 EVIDENCE_SAMPLES 运行，< 1s，无 LLM
  完整模式：由 moderation_eval.py 在生成新 evidence 后调用

用法（从项目根运行）：
  python eval/citation_check.py
"""
import re
import sys
from dataclasses import dataclass
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.golden_set import KNOWN_LAWS


# ═══════════════════════════════════════════════════════════════
#  核心函数：提取 + 校验
# ═══════════════════════════════════════════════════════════════

# 提取所有 《》 书名号内的法条名（2~30字，防止误匹配正文）
_LAW_PATTERN = re.compile(r"《([^》]{2,30})》")


def extract_law_citations(text: str) -> list[str]:
    """提取文本中所有 《XXX》 形式的法条名称（去重，保持顺序）。"""
    return list(dict.fromkeys(_LAW_PATTERN.findall(text)))


def is_citation_grounded(law_name: str) -> bool:
    """
    判断一个法条名是否在已知法规库中（双向子串匹配）。

    双向匹配处理全称/简称映射：
      "中华人民共和国刑法" → 包含 "刑法" → True
      "刑法" → 包含于 "中华人民共和国刑法" → True
    """
    low = law_name.lower()
    for known in KNOWN_LAWS:
        if known.lower() in low or low in known.lower():
            return True
    return False


def check_evidence(evidence_detail: str,
                   violated_laws: list[str] | None = None) -> dict:
    """
    检查一份 evidence_detail 的引用完整性。

    双重校验逻辑：
      第一关：KNOWN_LAWS（知识库白名单）
      第二关：violated_laws（judge_node 的实际输出，更权威）
      两关都没过 → 判为幻觉

    Args:
        evidence_detail: evidence_node 输出的完整报告文本
        violated_laws:   judge_node 给出的 violated_laws 列表（可选）

    Returns:
        {
          "citations":       提取到的所有法条名列表,
          "grounded":        合法引用列表,
          "hallucinated":    幻觉引用列表,
          "total":           引用总数,
          "grounded_count":  合法引用数,
          "integrity_rate":  合法比例（无引用时视为 1.0）,
          "passed":          是否零幻觉,
        }
    """
    citations = extract_law_citations(evidence_detail)

    grounded = []
    hallucinated = []

    for law in citations:
        if is_citation_grounded(law):
            grounded.append(law)
        elif violated_laws and any(
            law in vl or vl in law for vl in violated_laws
        ):
            # violated_laws 里有匹配（可能是 LLM 写了全称/缩写变体）
            grounded.append(law)
        else:
            hallucinated.append(law)

    total = len(citations)
    grounded_count = len(grounded)
    # 无引用时视为完整（不是幻觉，只是没引用）
    integrity_rate = grounded_count / total if total > 0 else 1.0

    return {
        "citations": citations,
        "grounded": grounded,
        "hallucinated": hallucinated,
        "total": total,
        "grounded_count": grounded_count,
        "integrity_rate": integrity_rate,
        "passed": len(hallucinated) == 0,
    }


# ═══════════════════════════════════════════════════════════════
#  预存 Evidence 样本（快速模式用，不调 LLM）
#  包含：真实的合法样本 + 一条故意含幻觉的样本（验证检测器有效性）
# ═══════════════════════════════════════════════════════════════

@dataclass
class EvidenceSample:
    id: str
    source_content: str             # 产生该 evidence 的原始内容（供参考）
    evidence_detail: str            # 实际 evidence_node / cascade 模板输出
    violated_laws: list[str]        # judge_node 给出的 violated_laws
    expect_no_hallucination: bool = True  # True=期望零幻觉；False=期望检测器报错


# T1-blacklist 模板证据（cascade._templated_evidence() 生成，确定性，无幻觉）
_T1_EVIDENCE_PORN = (
    "### 一、违规概述\n"
    "您发布的内容命中平台「pornography」类违规关键词，触发词：`约炮`，"
    "违规类型：pornography，严重程度分数：0.92。\n\n"
    "### 二、违规内容\n1. 约炮加我微信abc123\n\n"
    "### 三、违反条款\n**平台规则：**\n- 规则9 禁止涉黄低俗内容\n\n"
    "**法律法规：**\n"
    "- 《网络信息内容生态治理规定》第六条\n"
    "- 《互联网信息服务管理办法》第十五条\n\n"
    "### 四、处罚依据\n"
    "依据《网络暴力信息治理规定》第二十一条，平台可采取警示、删除信息、"
    "限制功能、关闭账号等措施。\n\n"
    "### 五、申诉说明\n"
    "如有异议可通过平台申诉渠道提交复核。\n"
    "（本报告由确定性规则引擎生成，非AI生成，引用法条均已核对。）"
)

_T1_EVIDENCE_FRAUD = (
    "### 一、违规概述\n"
    "您发布的内容命中平台「fraud」类违规关键词，触发词：`刷单兼职`，"
    "违规类型：fraud，严重程度分数：0.88。\n\n"
    "### 三、违反条款\n**法律法规：**\n"
    "- 《刑法》第二百六十六条 诈骗罪\n\n"
    "### 四、处罚依据\n"
    "依据《网络暴力信息治理规定》第二十一条，平台采取禁言措施。\n"
    "（本报告由确定性规则引擎生成，非AI生成，引用法条均已核对。）"
)

_T1_EVIDENCE_PRIVACY = (
    "### 三、违反条款\n**法律法规：**\n"
    "- 《个人信息保护法》\n"
    "- 《刑法》第二百五十三条之一 侵犯公民个人信息罪\n\n"
    "### 四、处罚依据\n"
    "依据《网络暴力信息治理规定》第二十一条，采取禁言措施。\n"
    "（本报告由确定性规则引擎生成，非AI生成，引用法条均已核对。）"
)

# 故意含幻觉的样本（用于验证检测器本身有效，expect_no_hallucination=False）
_HALLUCINATED_EVIDENCE = (
    "### 三、违反条款\n**法律法规：**\n"
    "- 《中华人民共和国互联网暴力防治法》第十八条\n"
    "- 《网络空间安全管理条例》第五条\n"
    "- 《刑法》第二百四十六条\n\n"
    "（前两条法律根本不存在，是 LLM 幻觉）"
)


EVIDENCE_SAMPLES: list[EvidenceSample] = [
    EvidenceSample(
        id="ES-T1-PORN",
        source_content="约炮加我微信abc123",
        evidence_detail=_T1_EVIDENCE_PORN,
        violated_laws=["《网络信息内容生态治理规定》第六条",
                       "《互联网信息服务管理办法》第十五条"],
        expect_no_hallucination=True,
    ),
    EvidenceSample(
        id="ES-T1-FRAUD",
        source_content="刷单兼职日赚过千",
        evidence_detail=_T1_EVIDENCE_FRAUD,
        violated_laws=["《刑法》第二百六十六条 诈骗罪"],
        expect_no_hallucination=True,
    ),
    EvidenceSample(
        id="ES-T1-PRIVACY",
        source_content="人肉他，挂人，曝光他身份证",
        evidence_detail=_T1_EVIDENCE_PRIVACY,
        violated_laws=["《个人信息保护法》",
                       "《刑法》第二百五十三条之一"],
        expect_no_hallucination=True,
    ),
    EvidenceSample(
        id="ES-HALLUCINATION-DETECTOR-TEST",
        source_content="测试样本：验证检测器能识别幻觉引用",
        evidence_detail=_HALLUCINATED_EVIDENCE,
        violated_laws=["《刑法》第二百四十六条"],
        expect_no_hallucination=False,  # 故意含幻觉，期望检测器报错
    ),
]


# ═══════════════════════════════════════════════════════════════
#  批量评测
# ═══════════════════════════════════════════════════════════════

def run_citation_eval(samples: list[EvidenceSample]) -> dict:
    """对所有预存样本运行引用完整性检查，返回汇总结果。"""
    results = []
    for s in samples:
        check = check_evidence(s.evidence_detail, s.violated_laws)
        # 检测器是否按预期工作：
        #   expect_no_hallucination=True  且 passed=True  → 正确
        #   expect_no_hallucination=False 且 passed=False → 正确（检测器抓到了幻觉）
        detector_correct = (check["passed"] == s.expect_no_hallucination)
        results.append({
            "id": s.id,
            "check": check,
            "expect_no_hallucination": s.expect_no_hallucination,
            "detector_correct": detector_correct,
        })

    total = len(results)
    detector_accuracy = sum(1 for r in results if r["detector_correct"]) / total if total else 1.0

    # 真实幻觉：仅统计"期望无幻觉"样本里出现的幻觉引用
    real_hallucinations = sum(
        len(r["check"]["hallucinated"])
        for r in results
        if r["expect_no_hallucination"]
    )
    valid_total_citations = sum(
        r["check"]["total"]
        for r in results
        if r["expect_no_hallucination"]
    )
    overall_integrity = (
        1.0 - real_hallucinations / valid_total_citations
        if valid_total_citations > 0 else 1.0
    )

    return {
        "results": results,
        "total": total,
        "detector_accuracy": detector_accuracy,
        "real_hallucinations": real_hallucinations,
        "overall_integrity": overall_integrity,
    }


# ═══════════════════════════════════════════════════════════════
#  报告打印
# ═══════════════════════════════════════════════════════════════

def print_citation_report(summary: dict) -> bool:
    """打印报告，返回是否通过 CI（零幻觉）。"""
    results = summary["results"]

    print("\n" + "=" * 72)
    print("  Citation Integrity 引用完整性报告（幻觉探测）")
    print("=" * 72)

    for r in results:
        c = r["check"]
        flag = "[OK]  " if r["detector_correct"] else "[FAIL]"
        expect_tag = "期望无幻觉" if r["expect_no_hallucination"] else "期望有幻觉（校验检测器）"
        print(f"\n  {r['id']}  {flag}  {expect_tag}")
        if c["citations"]:
            print(f"    提取法条 : {c['citations']}")
        if c["grounded"]:
            print(f"    合法引用 : {c['grounded']}")
        if c["hallucinated"]:
            print(f"    幻觉引用 : {c['hallucinated']}")
        print(f"    完整率   : {c['integrity_rate'] * 100:.0f}%  "
              f"({c['grounded_count']}/{c['total']})")

    print("\n" + "─" * 72)
    print(f"  样本总数          : {summary['total']}")
    print(f"  检测器准确率      : {summary['detector_accuracy'] * 100:.0f}%")
    print(f"  ★ 真实幻觉引用数  : {summary['real_hallucinations']}")
    print(f"  ★ 整体引用完整率  : {summary['overall_integrity'] * 100:.0f}%")

    passed = summary["real_hallucinations"] == 0
    status = "PASS" if passed else "FAIL"
    print(f"\n  CI 门禁: 幻觉引用数 = {summary['real_hallucinations']} "
          f"(阈值 = 0)  [{status}]")
    print("=" * 72)
    return passed


# ═══════════════════════════════════════════════════════════════
#  独立运行入口
# ═══════════════════════════════════════════════════════════════

def main():
    print(f"开始引用完整性检查（{len(EVIDENCE_SAMPLES)} 个预存样本）...")
    summary = run_citation_eval(EVIDENCE_SAMPLES)
    passed = print_citation_report(summary)
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
