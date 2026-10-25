import csv
import json
import os

repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
dataset_dir = os.path.join(repo_root, "dataset")

samples = {}
with open(os.path.join(dataset_dir, "sample_deletion_requests.csv"), "r", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        samples[row["case_id"]] = row

expected = {}
with open(os.path.join(dataset_dir, "sample_output.csv"), "r", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        expected[row["case_id"]] = row

print(f"Total sample cases: {len(samples)}")
status_counts = {}
for cid, exp in expected.items():
    st = exp["deletion_status"]
    status_counts[st] = status_counts.get(st, 0) + 1
print("Status counts:", status_counts)

for cid in sorted(samples.keys(), key=lambda x: int(x.split("_")[1])):
    req = samples[cid]
    exp = expected[cid]
    steps = json.loads(exp["steps_json"])
    findings = [s for s in steps if s["phase"] == "FINDING"]
    remeds = [s for s in steps if s["phase"] == "REMEDIATION"]
    verifs = [s for s in steps if s["phase"] == "VERIFICATION"]
    r_ids = [s["resource_id"] for s in steps]
    ev_ids = list(set([s["evidence_id"] for s in steps if s["evidence_id"]]))
    print(f"{cid}: rep={req['reported_status']:<18} exp={exp['deletion_status']:<14} steps={len(steps)} (F:{len(findings)} R:{len(remeds)} V:{len(verifs)}) ev={ev_ids} res={r_ids}")
