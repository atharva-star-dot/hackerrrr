"""
Validator module - validates output.csv against the contract.
"""
import csv
import json
import os
from typing import Dict, List, Optional, Set, Tuple

ALLOWED_OPERATIONS = {
    "FINDING": {
        "REPORT_REMAINING_RECORD": "PRESENT",
        "REPORT_EXPOSED_PII": "PRESENT",
        "REPORT_ACTIVE_DATA_FLOW": "ACTIVE",
        "REPORT_RESTORE_RISK": "ACTIVE",
    },
    "REMEDIATION": {
        "DISABLE_DATA_FLOW": "DISABLED",
        "BLOCK_RESTORE": "BLOCKED",
        "DELETE_RECORD": "ABSENT",
        "REDACT_RECORD": "REDACTED",
        "ANONYMIZE_RECORD": "ANONYMIZED",
    },
    "VERIFICATION": {
        "VERIFY_RECORD_ABSENT": "ABSENT",
        "VERIFY_RECORD_PRESENT": "PRESENT",
        "VERIFY_RECORD_REDACTED": "REDACTED",
        "VERIFY_RECORD_ANONYMIZED": "ANONYMIZED",
        "VERIFY_DATA_FLOW_DISABLED": "DISABLED",
        "VERIFY_RESTORE_BLOCKED": "BLOCKED",
    },
}


def validate_output(output_path: str, expected_count: int = 518) -> List[str]:
    """Validate output.csv and return list of errors."""
    errors = []

    if not os.path.exists(output_path):
        return ["Output file does not exist"]

    try:
        with open(output_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
    except Exception as e:
        return [f"Failed to read CSV: {e}"]

    # Check column names
    if not rows:
        return ["No data rows"]

    expected_cols = {"case_id", "deletion_status", "steps_json"}
    actual_cols = set(rows[0].keys())
    if actual_cols != expected_cols:
        errors.append(f"Wrong columns: expected {expected_cols}, got {actual_cols}")

    # Check row count
    if len(rows) != expected_count:
        errors.append(f"Expected {expected_count} rows, got {len(rows)}")

    # Check each row
    case_ids = set()
    for i, row in enumerate(rows):
        case_id = row.get("case_id", "")
        status = row.get("deletion_status", "")
        steps_json_str = row.get("steps_json", "")

        # Unique case_id
        if case_id in case_ids:
            errors.append(f"Row {i+1}: Duplicate case_id {case_id}")
        case_ids.add(case_id)

        # Valid status
        if status not in ("COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"):
            errors.append(f"Row {i+1} ({case_id}): Invalid status '{status}'")

        # Parse steps_json
        try:
            steps = json.loads(steps_json_str)
        except json.JSONDecodeError as e:
            errors.append(f"Row {i+1} ({case_id}): Invalid JSON: {e}")
            continue

        if not isinstance(steps, list):
            errors.append(f"Row {i+1} ({case_id}): steps_json must be a JSON array")
            continue

        # NOT_APPLICABLE must have empty array
        if status == "NOT_APPLICABLE":
            if steps:
                errors.append(f"Row {i+1} ({case_id}): NOT_APPLICABLE must have empty steps_json")
            continue

        # Check step numbering
        for j, step in enumerate(steps):
            expected_no = j + 1
            if step.get("step_no") != expected_no:
                errors.append(f"Row {i+1} ({case_id}): step_no should be {expected_no}, got {step.get('step_no')}")

            phase = step.get("phase", "")
            operation = step.get("operation", "")
            state = step.get("state", "")
            evidence_id = step.get("evidence_id", "")

            # Valid phase
            if phase not in ALLOWED_OPERATIONS:
                errors.append(f"Row {i+1} ({case_id}): Invalid phase '{phase}'")
                continue

            # Valid operation for phase
            allowed_ops = ALLOWED_OPERATIONS[phase]
            if operation not in allowed_ops:
                errors.append(f"Row {i+1} ({case_id}): Operation '{operation}' not allowed in phase '{phase}'")
                continue

            # Valid state for operation
            expected_state = allowed_ops[operation]
            if state != expected_state:
                errors.append(f"Row {i+1} ({case_id}): State should be '{expected_state}' for {operation}, got '{state}'")

            # COMPLETE cases: all steps must be VERIFICATION with evidence_id
            if status == "COMPLETE":
                if phase != "VERIFICATION":
                    errors.append(f"Row {i+1} ({case_id}): COMPLETE case has non-VERIFICATION step")
                if not evidence_id:
                    errors.append(f"Row {i+1} ({case_id}): COMPLETE VERIFICATION step missing evidence_id")

            # INCOMPLETE: REMEDIATION and VERIFICATION should have empty evidence_id
            if status == "INCOMPLETE":
                if phase in ("REMEDIATION", "VERIFICATION") and evidence_id:
                    errors.append(f"Row {i+1} ({case_id}): INCOMPLETE {phase} step should have empty evidence_id")
                if phase == "FINDING" and not evidence_id:
                    errors.append(f"Row {i+1} ({case_id}): FINDING step should have evidence_id")

        # Check phase ordering
        phases = [s["phase"] for s in steps]
        phase_order = {"FINDING": 0, "REMEDIATION": 1, "VERIFICATION": 2}
        for j in range(1, len(phases)):
            if phase_order.get(phases[j], 99) < phase_order.get(phases[j-1], 99):
                errors.append(f"Row {i+1} ({case_id}): Phases out of order: {phases[j-1]} before {phases[j]}")
                break

    return errors


def validate_against_samples(output_path: str, sample_output_path: str) -> dict:
    """Compare output against sample outputs and return accuracy metrics."""
    # Load sample outputs
    samples = {}
    with open(sample_output_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            samples[row["case_id"]] = row

    # Load our outputs
    ours = {}
    with open(output_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ours[row["case_id"]] = row

    results = {
        "total": len(samples),
        "status_correct": 0,
        "status_wrong": [],
        "step_exact_match": 0,
        "step_mismatches": [],
    }

    for case_id, sample in samples.items():
        our_row = ours.get(case_id)
        if not our_row:
            results["status_wrong"].append({"case_id": case_id, "expected": sample["deletion_status"], "got": "MISSING"})
            continue

        # Status accuracy
        if our_row["deletion_status"] == sample["deletion_status"]:
            results["status_correct"] += 1
        else:
            results["status_wrong"].append({
                "case_id": case_id,
                "expected": sample["deletion_status"],
                "got": our_row["deletion_status"],
            })

        # Step-level comparison
        try:
            expected_steps = json.loads(sample["steps_json"])
            our_steps = json.loads(our_row["steps_json"])

            if expected_steps == our_steps:
                results["step_exact_match"] += 1
            else:
                results["step_mismatches"].append({
                    "case_id": case_id,
                    "expected_count": len(expected_steps),
                    "got_count": len(our_steps),
                    "expected": expected_steps,
                    "got": our_steps,
                })
        except json.JSONDecodeError:
            results["step_mismatches"].append({
                "case_id": case_id,
                "error": "JSON parse error",
            })

    results["status_accuracy"] = results["status_correct"] / results["total"] if results["total"] else 0
    results["step_accuracy"] = results["step_exact_match"] / results["total"] if results["total"] else 0

    return results
