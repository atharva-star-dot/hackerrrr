"""
Planner module - generates findings, remediation, and verification steps.
Also handles data flow and backup/restore-specific logic.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple
from .rules import RulesEngine, ACTION_TO_OPERATION
from .evidence import ResourceRecord


@dataclass
class Step:
    step_no: int
    phase: str  # FINDING, REMEDIATION, VERIFICATION
    system_id: str
    resource_id: str
    operation: str
    state: str
    evidence_id: str


# Ordering maps for sorting steps
PHASE_ORDER = {"FINDING": 0, "REMEDIATION": 1, "VERIFICATION": 2}

FINDING_OP_ORDER = {
    "REPORT_REMAINING_RECORD": 0,
    "REPORT_EXPOSED_PII": 1,
    "REPORT_ACTIVE_DATA_FLOW": 2,
    "REPORT_RESTORE_RISK": 3,
}

REMEDIATION_OP_ORDER = {
    "DISABLE_DATA_FLOW": 0,
    "BLOCK_RESTORE": 1,
    "DELETE_RECORD": 2,
    "REDACT_RECORD": 3,
    "ANONYMIZE_RECORD": 4,
}

VERIFICATION_OP_ORDER = {
    "VERIFY_RECORD_ABSENT": 0,
    "VERIFY_RECORD_PRESENT": 1,
    "VERIFY_RECORD_REDACTED": 2,
    "VERIFY_RECORD_ANONYMIZED": 3,
    "VERIFY_DATA_FLOW_DISABLED": 4,
    "VERIFY_RESTORE_BLOCKED": 5,
}


def sort_steps(steps: List[Step]) -> List[Step]:
    """Sort steps according to the required ordering."""

    def step_sort_key(s: Step):
        phase_idx = PHASE_ORDER.get(s.phase, 99)
        if s.phase == "FINDING":
            op_idx = FINDING_OP_ORDER.get(s.operation, 99)
        elif s.phase == "REMEDIATION":
            op_idx = REMEDIATION_OP_ORDER.get(s.operation, 99)
        else:
            op_idx = VERIFICATION_OP_ORDER.get(s.operation, 99)
        return (phase_idx, op_idx, s.system_id, s.resource_id)

    sorted_steps = sorted(steps, key=step_sort_key)
    # Renumber
    for i, step in enumerate(sorted_steps):
        step.step_no = i + 1
    return sorted_steps


def get_finding_operation(required_action: str, current_state: str, data_category: str) -> Tuple[str, str]:
    """Get the finding operation and state for a non-compliant resource."""
    if data_category in ("DATA_FLOW",):
        return "REPORT_ACTIVE_DATA_FLOW", "ACTIVE"
    if data_category in ("BACKUP_ARCHIVE",):
        return "REPORT_RESTORE_RISK", "ACTIVE"

    if required_action in ("REDACT", "ANONYMIZE"):
        # PII still exposed
        return "REPORT_EXPOSED_PII", "PRESENT"
    # DELETE or others
    return "REPORT_REMAINING_RECORD", "PRESENT"


def get_remediation_operation(required_action: str, data_category: str) -> Tuple[Optional[str], Optional[str]]:
    """Get the remediation operation and target state."""
    if data_category == "DATA_FLOW":
        return "DISABLE_DATA_FLOW", "DISABLED"
    if data_category == "BACKUP_ARCHIVE":
        return "BLOCK_RESTORE", "BLOCKED"

    ops = ACTION_TO_OPERATION.get(required_action, {})
    return ops.get("remediation"), ops.get("remediation_state")


def get_verification_operation(required_action: str, data_category: str, is_retained: bool = False) -> Tuple[str, str]:
    """Get the verification operation and state."""
    if data_category == "DATA_FLOW":
        return "VERIFY_DATA_FLOW_DISABLED", "DISABLED"
    if data_category == "BACKUP_ARCHIVE":
        return "VERIFY_RESTORE_BLOCKED", "BLOCKED"
    if is_retained or required_action == "RETAIN":
        return "VERIFY_RECORD_PRESENT", "PRESENT"

    ops = ACTION_TO_OPERATION.get(required_action, {})
    return ops.get("verification", "VERIFY_RECORD_ABSENT"), ops.get("verification_state", "ABSENT")


class StepPlanner:
    """Generates ordered steps for a deletion audit case."""

    def __init__(self, rules_engine: RulesEngine):
        self.rules = rules_engine

    def plan_complete(self, compliant_resources: List[dict], evidence_id: str) -> List[Step]:
        """Plan verification-only steps for a COMPLETE case."""
        steps = []
        for res in compliant_resources:
            resource_id = res["resource_id"]
            system_id = res["system_id"]
            data_category = res["data_category"]
            required_action = res["required_action"]

            ver_op, ver_state = get_verification_operation(required_action, data_category, required_action == "RETAIN")
            steps.append(Step(
                step_no=0,
                phase="VERIFICATION",
                system_id=system_id,
                resource_id=resource_id,
                operation=ver_op,
                state=ver_state,
                evidence_id=evidence_id,
            ))

        return sort_steps(steps)

    def plan_incomplete(self, non_compliant: List[dict], compliant_for_verify: List[dict]) -> List[Step]:
        """Plan finding + remediation + verification steps for an INCOMPLETE case."""
        steps = []

        # FINDING steps for non-compliant resources
        for res in non_compliant:
            resource_id = res["resource_id"]
            system_id = res["system_id"]
            data_category = res["data_category"]
            required_action = res["required_action"]
            evidence_id = res.get("evidence_id", "")

            finding_op, finding_state = get_finding_operation(required_action, res.get("current_state", "PRESENT"), data_category)
            steps.append(Step(
                step_no=0,
                phase="FINDING",
                system_id=system_id,
                resource_id=resource_id,
                operation=finding_op,
                state=finding_state,
                evidence_id=evidence_id,
            ))

        # REMEDIATION steps for non-compliant resources
        for res in non_compliant:
            resource_id = res["resource_id"]
            system_id = res["system_id"]
            data_category = res["data_category"]
            required_action = res["required_action"]

            rem_op, rem_state = get_remediation_operation(required_action, data_category)
            if rem_op:
                steps.append(Step(
                    step_no=0,
                    phase="REMEDIATION",
                    system_id=system_id,
                    resource_id=resource_id,
                    operation=rem_op,
                    state=rem_state,
                    evidence_id="",
                ))

        # VERIFICATION steps for non-compliant resources (after remediation)
        for res in non_compliant:
            resource_id = res["resource_id"]
            system_id = res["system_id"]
            data_category = res["data_category"]
            required_action = res["required_action"]

            ver_op, ver_state = get_verification_operation(required_action, data_category)
            steps.append(Step(
                step_no=0,
                phase="VERIFICATION",
                system_id=system_id,
                resource_id=resource_id,
                operation=ver_op,
                state=ver_state,
                evidence_id="",
            ))

        # VERIFICATION steps for compliant resources that need verification (retained records, etc.)
        for res in compliant_for_verify:
            resource_id = res["resource_id"]
            system_id = res["system_id"]
            data_category = res["data_category"]
            required_action = res["required_action"]

            ver_op, ver_state = get_verification_operation(required_action, data_category, required_action == "RETAIN")
            steps.append(Step(
                step_no=0,
                phase="VERIFICATION",
                system_id=system_id,
                resource_id=resource_id,
                operation=ver_op,
                state=ver_state,
                evidence_id="",
            ))

        return sort_steps(steps)
