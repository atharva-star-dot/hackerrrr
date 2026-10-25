import os
import json
import sys

repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, repo_root)

from code.agent import DeletionAuditAgent
from code.usage import UsageLogger

cases_dir = os.path.join(repo_root, "evaluation", "custom_cases")
agent = DeletionAuditAgent("dataset", UsageLogger())

total = 0
passed = 0
print("=== EVALUATING 5 CUSTOM TEST CASES ===")
for fn in sorted(os.listdir(cases_dir)):
    if fn.endswith(".json"):
        with open(os.path.join(cases_dir, fn), encoding="utf-8") as f:
            c = json.load(f)
        res = agent.process_case(c["request"])
        ok = res["deletion_status"] == c["expected_status"]
        total += 1
        if ok:
            passed += 1
        status_label = "PASS" if ok else "FAIL"
        print(f"[{status_label}] {c['id']} - {c['title']}: expected {c['expected_status']}, got {res['deletion_status']}")

print(f"\nCustom cases score: {passed}/{total} ({passed/total:.1%})")
