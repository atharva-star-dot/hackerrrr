import os
import json

cases_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "evaluation", "custom_cases")
os.makedirs(cases_dir, exist_ok=True)

cases = [
    {
        "id": "custom_01",
        "title": "Stale Snapshot Temporal Boundary",
        "description": "Snapshot captured on 2026-09-17 shows account PRESENT, but audit_at is 2026-09-15 where evidence_92 shows account ABSENT (404).",
        "request": {
            "case_id": "case_custom_01",
            "email": "almeida.mariana@gmail.com",
            "requested_at": "2026-08-30T12:00:00Z",
            "reported_status": "COMPLETE",
            "reported_at": "2026-09-02T12:00:00Z",
            "audit_at": "2026-09-15T12:00:00Z",
            "request_text": "Please confirm my account is deleted."
        },
        "expected_status": "COMPLETE",
        "test_rule": "Must ignore evidence_02 captured after audit_at (2026-09-17)."
    },
    {
        "id": "custom_02",
        "title": "Failed Workflow Claim but Evidenced Absent",
        "description": "System activity reports reported_result=FAILED for account deletion, but evidence_92 HTTP 404 proves profile is absent.",
        "request": {
            "case_id": "case_custom_02",
            "email": "almeida.mariana@gmail.com",
            "requested_at": "2026-08-30T12:00:00Z",
            "reported_status": "NOT_STARTED",
            "reported_at": "2026-09-02T12:00:00Z",
            "audit_at": "2026-09-15T12:00:00Z",
            "request_text": "I saw an error deleting my profile. Is it gone?"
        },
        "expected_status": "COMPLETE",
        "test_rule": "Status at audit_at comes from evidence, not reported_result."
    },
    {
        "id": "custom_03",
        "title": "Active Sync Recreating Deleted Data",
        "description": "Data flow integration is enabled and can replicate deleted user profile back into replica.",
        "request": {
            "case_id": "case_custom_03",
            "email": "leila.haddad@yahoo.com",
            "requested_at": "2026-08-25T10:00:00Z",
            "reported_status": "COMPLETE",
            "reported_at": "2026-08-27T10:00:00Z",
            "audit_at": "2026-09-02T23:30:00Z",
            "request_text": "Please delete all my records completely."
        },
        "expected_status": "INCOMPLETE",
        "test_rule": "Active data flow requires DISABLE_DATA_FLOW before dependent records."
    },
    {
        "id": "custom_04",
        "title": "Historical-Only Email Identification",
        "description": "Request submitted with old email address changed in user_audit_log 3 months prior.",
        "request": {
            "case_id": "case_custom_04",
            "email": "minjun.kim90@gmail.com",
            "requested_at": "2026-08-24T12:00:00Z",
            "reported_status": "COMPLETE",
            "reported_at": "2026-08-25T12:00:00Z",
            "audit_at": "2026-09-15T12:00:00Z",
            "request_text": "Delete my account tied to this email."
        },
        "expected_status": "INCOMPLETE",
        "test_rule": "Must resolve historical email to user_12 and find tied resources."
    },
    {
        "id": "custom_05",
        "title": "Non-English Non-Deletion Request",
        "description": "German request asking for data export and to keep the account active.",
        "request": {
            "case_id": "case_custom_05",
            "email": "clara.schmidt@web.de",
            "requested_at": "2026-09-01T10:00:00Z",
            "reported_status": "NOT_STARTED",
            "reported_at": "2026-09-01T10:00:00Z",
            "audit_at": "2026-09-05T10:00:00Z",
            "request_text": "Bitte senden Sie mir eine Kopie meiner Daten im portablen Format. Schließen Sie mein Konto nicht, ich möchte es weiterhin aktiv nutzen."
        },
        "expected_status": "NOT_APPLICABLE",
        "test_rule": "Non-deletion requests must return NOT_APPLICABLE with empty steps."
    }
]

for c in cases:
    path = os.path.join(cases_dir, f"{c['id']}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(c, f, indent=2)
    print(f"Wrote {path}")
