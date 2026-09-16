# -*- coding: utf-8 -*-
import json
with open(r"d:\Projects\shill-guard-ai\loadtest\golden_set.json", encoding="utf-8") as f:
    data = json.load(f)
cats = {}
for d in data:
    c = d.get("category","?")
    cats[c] = cats.get(c, 0) + 1
print("category 分布:", cats)
print("total:", len(data))
# 看有没有 expected_verdict 包含 auto_mute 的
vio_ids = [d["id"] for d in data if "auto_mute" in d.get("expected_verdict", []) or d.get("expected_action") in ("auto_mute","manual_review")]
print(f"expected_action 违规类 (auto_mute/manual_review): {len(vio_ids)}")
normal_ids = [d["id"] for d in data if d.get("expected_action") == "none"]
print(f"expected_action 正常类 (none): {len(normal_ids)}")
