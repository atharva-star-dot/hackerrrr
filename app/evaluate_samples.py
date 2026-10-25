import csv
import json
import os
import sys

repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, repo_root)

from code.agent import DeletionAuditAgent
from code.usage import UsageLogger
from code.validator import validate_against_samples

dataset_dir = os.path.join(repo_root, "dataset")
usage = UsageLogger()

print("Initializing agent...")
agent = DeletionAuditAgent(dataset_dir, usage)

# Load sample requests
samples = []
with open(os.path.join(dataset_dir, "sample_deletion_requests.csv"), "r", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        samples.append(dict(row))

print(f"Running agent on {len(samples)} samples...")
results = []
for s in samples:
    res = agent.process_case(s)
    results.append(res)

# Write to temp output
out_path = os.path.join(repo_root, "evaluation", "sample_test_output.csv")
with open(out_path, "w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["case_id", "deletion_status", "steps_json"])
    writer.writeheader()
    for r in results:
        writer.writerow(r)

print(f"Wrote results to {out_path}")

# Evaluate
sample_out = os.path.join(dataset_dir, "sample_output.csv")
metrics = validate_against_samples(out_path, sample_out)

print("\n=== EVALUATION RESULTS ON 32 SAMPLES ===")
print(f"Status accuracy: {metrics['status_accuracy']:.1%} ({metrics['status_correct']}/{metrics['total']})")
print(f"Step exact matches: {metrics['step_exact_match']}/{metrics['total']}")

if metrics["status_wrong"]:
    print("\nStatus mismatches:")
    for m in metrics["status_wrong"]:
        print(f"  {m['case_id']}: expected {m['expected']}, got {m['got']}")

if metrics["step_mismatches"]:
    print(f"\nStep mismatches: {len(metrics['step_mismatches'])}")
    for m in metrics["step_mismatches"][:5]:
        print(f"  {m['case_id']}: expected {m.get('expected_count')} steps, got {m.get('got_count')} steps")
