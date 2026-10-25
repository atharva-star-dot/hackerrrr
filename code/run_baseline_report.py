import csv
import json
import os
import sys

repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, repo_root)

from code.agent import DeletionAuditAgent
from code.usage import UsageLogger

dataset_dir = os.path.join(repo_root, "dataset")
usage = UsageLogger()
agent = DeletionAuditAgent(dataset_dir, usage)

# Load sample requests
samples = []
with open(os.path.join(dataset_dir, "sample_deletion_requests.csv"), "r", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        samples.append(dict(row))

# Load sample output
expected = {}
with open(os.path.join(dataset_dir, "sample_output.csv"), "r", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        expected[row["case_id"]] = row

predictions = {}
for s in samples:
    predictions[s["case_id"]] = agent.process_case(s)

# Metrics calculation
total_cases = len(samples)
status_correct = 0

total_expected_steps = 0
total_predicted_steps = 0
step_exact_matches = 0
sequence_matches = 0

field_counts = {
    "step_no": 0, "phase": 0, "system_id": 0, "resource_id": 0,
    "operation": 0, "state": 0, "evidence_id": 0
}
total_compared_steps = 0

failure_categories = {
    "Missed Finding (Resource Missing)": [],
    "Wrong Status (INCOMPLETE vs COMPLETE)": [],
    "Extra/Missing Verification Steps": [],
    "Missing Audit Record / Account Verification": [],
    "Wrong Evidence ID Cited": []
}

for s in samples:
    cid = s["case_id"]
    exp_row = expected[cid]
    pred_row = predictions[cid]

    # Status check
    st_match = (exp_row["deletion_status"] == pred_row["deletion_status"])
    if st_match:
        status_correct += 1
    else:
        failure_categories["Wrong Status (INCOMPLETE vs COMPLETE)"].append({
            "case_id": cid, "expected": exp_row["deletion_status"], "got": pred_row["deletion_status"]
        })

    exp_steps = json.loads(exp_row["steps_json"])
    pred_steps = json.loads(pred_row["steps_json"])

    total_expected_steps += len(exp_steps)
    total_predicted_steps += len(pred_steps)

    # Exact step match
    if exp_steps == pred_steps:
        step_exact_matches += 1

    # Sequence match (sequence of phase + operation + state)
    exp_seq = [(x["phase"], x["operation"], x["state"]) for x in exp_steps]
    pred_seq = [(x["phase"], x["operation"], x["state"]) for x in pred_steps]
    if exp_seq == pred_seq:
        sequence_matches += 1

    # Field level check for aligned steps (by index)
    min_len = min(len(exp_steps), len(pred_steps))
    total_compared_steps += max(len(exp_steps), len(pred_steps))
    for i in range(min_len):
        e = exp_steps[i]
        p = pred_steps[i]
        for f in field_counts:
            if e.get(f) == p.get(f):
                field_counts[f] += 1

    # Classify failure
    exp_rids = set(x["resource_id"] for x in exp_steps if x["phase"] == "FINDING")
    pred_rids = set(x["resource_id"] for x in pred_steps if x["phase"] == "FINDING")
    if exp_rids != pred_rids:
        failure_categories["Missed Finding (Resource Missing)"].append({
            "case_id": cid, "expected_findings": list(exp_rids), "got_findings": list(pred_rids)
        })

    exp_v_rids = set(x["resource_id"] for x in exp_steps if x["phase"] == "VERIFICATION")
    pred_v_rids = set(x["resource_id"] for x in pred_steps if x["phase"] == "VERIFICATION")
    if exp_v_rids != pred_v_rids:
        failure_categories["Extra/Missing Verification Steps"].append({
            "case_id": cid, "expected_verifications": list(exp_v_rids), "got_verifications": list(pred_v_rids)
        })

status_acc = status_correct / total_cases
step_acc = step_exact_matches / total_cases
seq_acc = sequence_matches / total_cases

print("=== BASELINE EVALUATION REPORT (32 SAMPLES) ===")
print(f"Case-Level Status Accuracy: {status_acc:.1%} ({status_correct}/{total_cases})")
print(f"Step-Level Exact Match Accuracy: {step_acc:.1%} ({step_exact_matches}/{total_cases})")
print(f"Sequence Accuracy: {seq_acc:.1%} ({sequence_matches}/{total_cases})")
print("\nField-Level Accuracy (across aligned steps):")
for f, cnt in field_counts.items():
    denom = max(total_expected_steps, 1)
    print(f"  - {f}: {cnt/denom:.1%} ({cnt}/{total_expected_steps})")

print("\nTop Failure Categories:")
for cat, items in failure_categories.items():
    print(f"  Category: {cat} ({len(items)} cases)")
    for ex in items[:2]:
        print(f"    Example: {ex}")

# Write markdown report
report_path = os.path.join(repo_root, "evaluation", "baseline_report.md")
with open(report_path, "w", encoding="utf-8") as f:
    f.write(f"# Baseline Evaluation Report (32 Labeled Samples)\n\n")
    f.write(f"Evaluated on: 2026-10-25\n\n")
    f.write(f"## 1. Summary Metrics\n\n")
    f.write(f"| Metric | Score | Matches / Total |\n")
    f.write(f"|---|---|---|\n")
    f.write(f"| **Case-Level Status Accuracy** | **{status_acc:.1%}** | {status_correct} / {total_cases} |\n")
    f.write(f"| **Step-Level Exact Match** | **{step_acc:.1%}** | {step_exact_matches} / {total_cases} |\n")
    f.write(f"| **Sequence Accuracy** | **{seq_acc:.1%}** | {sequence_matches} / {total_cases} |\n")
    f.write(f"| Total Expected Steps | {total_expected_steps} | - |\n")
    f.write(f"| Total Predicted Steps | {total_predicted_steps} | - |\n\n")

    f.write(f"## 2. Field-Level Accuracy\n\n")
    f.write(f"| Field | Accuracy | Matched / Expected Steps |\n")
    f.write(f"|---|---|---|\n")
    for fld, cnt in field_counts.items():
        f.write(f"| `{fld}` | {cnt/total_expected_steps:.1%} | {cnt} / {total_expected_steps} |\n")

    f.write(f"\n## 3. Top 5 Failure Categories & Examples\n\n")
    for cat, items in failure_categories.items():
        f.write(f"### {cat} ({len(items)} cases)\n\n")
        if not items:
            f.write(f"No failures observed in this category.\n\n")
            continue
        for ex in items[:2]:
            f.write(f"- **Case `{ex.get('case_id')}`**:\n")
            for k, v in ex.items():
                if k != 'case_id':
                    f.write(f"  - `{k}`: `{v}`\n")
        f.write(f"\n")

print(f"\nSaved report to {report_path}")
