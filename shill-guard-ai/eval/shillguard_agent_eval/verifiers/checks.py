"""任务结果断言（E1/E2/E3）。"""
from __future__ import annotations

from typing import Any


def _text_of(result: Any) -> str:
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        parts = []
        for key in ("evidenceDetail", "evidence_detail", "judgment", "content"):
            val = result.get(key)
            if val:
                parts.append(str(val))
        return "\n".join(parts) if parts else str(result)
    return str(result)


def keywords_hit(text: str, keywords: list[str], *, match_all: bool = False) -> tuple[bool, list[str]]:
    if not keywords:
        return True, []
    hits = [kw for kw in keywords if kw in text]
    if match_all:
        ok = len(hits) == len(keywords)
    else:
        ok = len(hits) > 0
    return ok, hits


def verify_task_result(task: dict, outcome: dict) -> dict:
    """返回 {passed, reasons, detail}。"""
    suite = task.get("suite", "e1")
    expect = task.get("expect") or {}
    reasons: list[str] = []
    passed = True

    if suite in ("e1", "e2"):
        tool = outcome.get("tool") or task.get("tool")
        if tool:
            reasons.append(f"tool={tool}")

        if "error" in outcome:
            return {
                "passed": False,
                "reasons": [f"error: {outcome['error']}"],
                "detail": outcome,
            }

        # RAG / 文本类
        if "keywords_any" in expect:
            text = _text_of(outcome.get("result"))
            ok, hits = keywords_hit(text, expect["keywords_any"])
            if not ok:
                passed = False
                reasons.append(f"missing keywords_any: {expect['keywords_any']}")
            else:
                reasons.append(f"keywords hit: {hits}")

        if "rag_keywords_any" in expect:
            rag_text = _text_of(outcome.get("rag_result", ""))
            ok, hits = keywords_hit(rag_text, expect["rag_keywords_any"])
            if not ok:
                passed = False
                reasons.append(f"rag missing: {expect['rag_keywords_any']}")
            else:
                reasons.append(f"rag hit: {hits}")

        # moderate / detect dict
        result = outcome.get("result")
        if isinstance(result, dict):
            score = result.get("anomalyScore", result.get("anomaly_score"))
            if score is not None:
                score = float(score)
                if "score_min" in expect and score < expect["score_min"]:
                    passed = False
                    reasons.append(f"score {score} < min {expect['score_min']}")
                if "score_max" in expect and score > expect["score_max"]:
                    passed = False
                    reasons.append(f"score {score} > max {expect['score_max']}")
                if passed and "score_min" in expect:
                    reasons.append(f"score={score:.3f} in range")

            action = result.get("action")
            if "action" in expect:
                if action != expect["action"]:
                    passed = False
                    reasons.append(f"action {action} != expected {expect['action']}")
                else:
                    reasons.append(f"action={action}")

            if "evidence_keywords_any" in expect:
                ev_text = _text_of(result.get("evidenceDetail", result.get("evidence_detail", "")))
                ok, hits = keywords_hit(ev_text, expect["evidence_keywords_any"])
                if not ok:
                    passed = False
                    reasons.append(f"evidence missing: {expect['evidence_keywords_any']}")
                else:
                    reasons.append(f"evidence hit: {hits}")

    elif suite == "e3":
        cascade = outcome.get("cascade") or {}
        if "error" in cascade:
            return {"passed": False, "reasons": [cascade["error"]], "detail": cascade}

        checks = [
            ("verdict", "expected_verdict"),
            ("tier", "expected_tier"),
        ]
        for actual_key, expect_key in checks:
            exp = task.get(expect_key) or cascade.get(expect_key)
            act = cascade.get(actual_key)
            if exp is not None and act != exp:
                passed = False
                reasons.append(f"{actual_key} {act} != {exp}")

        exp_score = task.get("expected_score")
        if exp_score is None:
            exp_score = cascade.get("expected_score")
        act_score = cascade.get("score")
        if exp_score is not None and act_score is not None:
            if abs(float(act_score) - float(exp_score)) > 0.01:
                passed = False
                reasons.append(f"score {act_score} != {exp_score}")

        if passed and not reasons:
            reasons.append(
                f"verdict={cascade.get('verdict')} tier={cascade.get('tier')} score={cascade.get('score')}"
            )

    return {"passed": passed, "reasons": reasons, "detail": outcome}
