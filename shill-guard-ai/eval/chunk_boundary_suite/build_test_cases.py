"""根据 manifest 自动生成测试用例（query → 期望完整条款 / 滑动窗口失败模式）。"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "manifest.json"
OUT = ROOT / "test_cases.json"


def build_cases() -> list[dict]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    cases: list[dict] = []
    n = 0
    for doc in manifest["docs"]:
        law = doc["law_short"]
        aid = doc["article_id"]
        hooks = doc["query_hooks"]
        full = doc["full_article"]
        anchor = doc["must_have_anchor"]
        fname = doc["filename"]

        # 每条款生成 3 类 query：精确 / 口语 / 易混淆
        variants = [
            {
                "style": "precise",
                "query": " ".join(hooks[:3]) + f" {law}",
                "desc": "精确关键词 + 法名",
            },
            {
                "style": "colloquial",
                "query": _colloquial(aid, hooks),
                "desc": "口语化用户问题",
            },
            {
                "style": "confusable",
                "query": _confusable(aid, hooks, law),
                "desc": "近义易混问法（半条时更易张冠李戴）",
            },
        ]
        for v in variants:
            n += 1
            cases.append(
                {
                    "id": f"CB-{n:03d}",
                    "article_id": aid,
                    "source_file": fname,
                    "law_short": law,
                    "query": v["query"],
                    "query_style": v["style"],
                    "description": v["desc"],
                    "expected_full_article": full,
                    "must_include_anchor": anchor,
                    "must_include_hooks": hooks,
                    "sliding_window_expected": {
                        "article_intact_in_top_chunk": False,
                        "half_hit": True,
                        "risk": doc["wrong_if_head_only"],
                        "symptom": (
                            "检索命中含关键词的前半段 chunk，但缺少切分锚点与后半段罚则/要件；"
                            "证据报告易出现条款不完整或援引邻近诱饵条款。"
                        ),
                    },
                    "parent_child_ideal": {
                        "article_intact_in_parent_context": True,
                        "must_include_anchor_in_context": True,
                        "symptom_resolved": (
                            "child 命中前半段关键词后回填 parent，生成上下文覆盖完整条款与切分锚点，"
                            "不再因半条上下文张冠李戴。"
                        ),
                    },
                }
            )
    return cases


def _colloquial(aid: str, hooks: list[str]) -> str:
    mapping = {
        "NV-18": "评论区发弹幕骂人、跟帖引战，平台要怎么管，依据哪条",
        "NV-14": "网暴账号要不要记入信用、拉黑名单，法律怎么规定",
        "PS-42": "网上公开骂人诽谤、散布隐私，治安管理怎么处罚",
        "CL-246": "网络侮辱诽谤什么情况才构成犯罪、要不要自己去告",
        "PI-10": "被人肉搜索曝光身份证电话，个保法能不能管",
        "CS-12": "网上造谣传谣扰乱秩序，网络安全法怎么说",
        "ECO-6": "发布色情淫秽内容，生态治理规定哪一条禁止",
        "IIS-15": "互联网信息服务不得制作传播哪些违法信息",
        "NVGO-insult": "网络谩骂诋毁披露隐私，是治安案件还是刑事案件",
        "SPC-500": "诽谤信息转发多少次、点击多少次算情节严重",
        "CC-1024": "名誉权被网络侮辱诽谤侵害，民法典怎么保护",
        "PLAT-ads": "评论区留微信号进群领福利算不算站外引流",
        "MIN-74": "对未成年人发性暗示或诱导内容，法律禁止什么",
    }
    return mapping.get(aid, " ".join(hooks) + " 适用哪条法律规定")


def _confusable(aid: str, hooks: list[str], law: str) -> str:
    mapping = {
        "NV-18": "跟帖评论里的网络暴力，是按第十七条视听节目管还是按评论管理条款",
        "NV-14": "网暴用户是限制功能就行，还是要列入黑名单禁止注册",
        "PS-42": "公然侮辱诽谤只罚五日以下吗，有没有情节较重的档",
        "CL-246": "网上骂人是直接抠刑法侮辱罪，还是先看治安处罚",
        "PI-10": "曝光个人信息是删帖就行，还是个保法禁止非法公开",
        "CS-12": "造谣是算不良信息，还是编造传播虚假信息扰乱秩序",
        "ECO-6": "色情内容是引用生态治理规定哪一项，不要只写不得违法",
        "IIS-15": "管理办法里不得制作传播，具体对应哪几项禁止内容",
        "NVGO-insult": "网络侮辱一定按刑事处理吗，不构成犯罪怎么办",
        "SPC-500": "情节严重是五百次点击还是五千次点击，转发怎么算",
        "CC-1024": "侵害名誉权是只引治安法，还是民法典也有依据",
        "PLAT-ads": "留微信号引流是诈骗罪还是平台站外引流规则",
        "MIN-74": "未成年人保护是只写不得危害，还是要列举性暗示等类型",
    }
    return mapping.get(aid, f"{law} {' '.join(hooks)} 容易和邻近条款搞混时如何正确引用")


def main():
    if not MANIFEST.exists():
        raise SystemExit("缺少 manifest.json，请先运行 build_adversarial_docs.py")
    cases = build_cases()
    payload = {
        "suite": "chunk_boundary_suite",
        "case_count": len(cases),
        "cases": cases,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"生成 {len(cases)} 条用例 → {OUT}")


if __name__ == "__main__":
    main()
