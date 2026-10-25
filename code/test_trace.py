import sys, os, csv, json
sys.path.insert(0, 'e:/OneMoreTime/hackerank/hackerrank-orchestrate-october26')
from code.identity import IdentityResolver
from code.evidence import EvidenceParser

dataset_dir = 'e:/OneMoreTime/hackerank/hackerrank-orchestrate-october26/dataset'
resolver = IdentityResolver(dataset_dir)
parser = EvidenceParser(dataset_dir)
parser.parse_all()

# Load sample requests
samples = {}
with open(os.path.join(dataset_dir, 'sample_deletion_requests.csv'), 'r', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        samples[row['case_id']] = row

# Load sample output
expected = {}
with open(os.path.join(dataset_dir, 'sample_output.csv'), 'r', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        expected[row['case_id']] = row

# Check case_05 (INCOMPLETE - account_005 still present)
case = samples.get('case_05')
if case:
    email = case['email']
    identity = resolver.resolve(email)
    print("=== case_05:", email, "===")
    if identity:
        print("User:", identity.user_id)
        resources = parser.get_evidence_for_user(identity, case['audit_at'])
        print("Resources found:", len(resources))
        for r in resources:
            print("  ", r.resource_id, "|", r.system_id, "|", r.state, "|", r.evidence_id, "| email=", r.email, "| ref=", r.customer_reference)
    exp = expected['case_05']
    print("Expected status:", exp["deletion_status"])
    exp_steps = json.loads(exp['steps_json'])
    print("Expected steps:", len(exp_steps))
    for s in exp_steps:
        print("  ", s["step_no"], s["phase"], s["operation"], s["system_id"], s["resource_id"], "evidence="+s["evidence_id"])

print()

# Check case_11 (INCOMPLETE - complex)
case = samples.get('case_11')
if case:
    email = case['email']
    identity = resolver.resolve(email)
    print("=== case_11:", email, "===")
    if identity:
        print("User:", identity.user_id, "all_emails:", identity.all_emails)
        resources = parser.get_evidence_for_user(identity, case['audit_at'])
        print("Resources found:", len(resources))
        by_rid = {}
        for r in resources:
            key = r.resource_id
            if key not in by_rid or r.captured_at > by_rid[key].captured_at:
                by_rid[key] = r
        for rid, r in sorted(by_rid.items()):
            print("  ", r.resource_id, "|", r.system_id, "|", r.state, "|", r.evidence_id, "|", r.data_category)
    exp = expected['case_11']
    print("Expected status:", exp["deletion_status"])
    exp_steps = json.loads(exp['steps_json'])
    print("Expected steps:", len(exp_steps))
    for s in exp_steps:
        print("  ", s["step_no"], s["phase"], s["operation"], s["system_id"], s["resource_id"], "evidence="+s["evidence_id"])

print()

# Check case_31 (COMPLETE - with tombstone)
case = samples.get('case_31')
if case:
    email = case['email']
    identity = resolver.resolve(email)
    print("=== case_31:", email, "===")
    if identity:
        print("User:", identity.user_id, "all_emails:", identity.all_emails)
        resources = parser.get_evidence_for_user(identity, case['audit_at'])
        print("Resources found:", len(resources))
        by_rid = {}
        for r in resources:
            key = r.resource_id
            if key not in by_rid or r.captured_at > by_rid[key].captured_at:
                by_rid[key] = r
        for rid, r in sorted(by_rid.items()):
            print("  ", r.resource_id, "|", r.system_id, "|", r.state, "|", r.evidence_id, "|", r.data_category)
    exp = expected['case_31']
    print("Expected status:", exp["deletion_status"])
    exp_steps = json.loads(exp['steps_json'])
    for s in exp_steps:
        print("  ", s["step_no"], s["phase"], s["operation"], s["system_id"], s["resource_id"], "evidence="+s["evidence_id"])
