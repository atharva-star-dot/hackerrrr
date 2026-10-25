"""
Deletion rules module - reads deletion_rules.csv and evaluates conditions.
"""
import csv
import os
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class DeletionRule:
    rule_id: str
    data_category: str
    condition: str
    required_action: str  # DELETE, REDACT, ANONYMIZE, RETAIN


# Maps data_category to required_action and the operation to use
ACTION_TO_OPERATION = {
    "DELETE": {
        "remediation": "DELETE_RECORD",
        "remediation_state": "ABSENT",
        "verification": "VERIFY_RECORD_ABSENT",
        "verification_state": "ABSENT",
    },
    "REDACT": {
        "remediation": "REDACT_RECORD",
        "remediation_state": "REDACTED",
        "verification": "VERIFY_RECORD_REDACTED",
        "verification_state": "REDACTED",
    },
    "ANONYMIZE": {
        "remediation": "ANONYMIZE_RECORD",
        "remediation_state": "ANONYMIZED",
        "verification": "VERIFY_RECORD_ANONYMIZED",
        "verification_state": "ANONYMIZED",
    },
    "RETAIN": {
        "remediation": None,  # No remediation needed
        "remediation_state": None,
        "verification": "VERIFY_RECORD_PRESENT",
        "verification_state": "PRESENT",
    },
}

# Resource prefix to data_category mapping
RESOURCE_TO_CATEGORY = {
    "account_": "USER_PROFILE",
    "search_": "SEARCH_INDEX_ENTRY",
    "analytics_": "ANALYTICS_PROFILE",
    "support_": "SUPPORT_MESSAGE",  # default; SUPPORT_ATTACHMENT determined by context
    "export_": "USER_EXPORT",
    "cache_": "CACHE_ENTRY",
    "audit_record_": "SECURITY_AUDIT_LOG",
    "email_delivery_": "EMAIL_DELIVERY_LOG",
    "data_flow_": "DATA_FLOW",
    "backup_": "BACKUP_ARCHIVE",
    "tombstone_": "ACCOUNT_TOMBSTONE",
    "marketing_": "MARKETING_PROFILE",
    "legal_hold_": "LEGAL_HOLD_RECORD",
    "object_": "USER_EXPORT",
}


class RulesEngine:
    """Loads and applies deletion rules."""

    def __init__(self, dataset_dir: str):
        self.rules: Dict[str, DeletionRule] = {}
        self.rules_by_category: Dict[str, DeletionRule] = {}
        self._load(dataset_dir)

    def _load(self, dataset_dir: str):
        path = os.path.join(dataset_dir, "deletion_rules.csv")
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rule = DeletionRule(
                    rule_id=row["rule_id"],
                    data_category=row["data_category"],
                    condition=row["condition"],
                    required_action=row["required_action"],
                )
                self.rules[rule.rule_id] = rule
                self.rules_by_category[rule.data_category] = rule

    def get_required_action(self, data_category: str) -> Optional[str]:
        """Get the required action for a data category."""
        rule = self.rules_by_category.get(data_category)
        if rule:
            return rule.required_action
        return None

    def get_rule(self, data_category: str) -> Optional[DeletionRule]:
        """Get the rule for a data category."""
        return self.rules_by_category.get(data_category)

    def get_category_for_resource(self, resource_id: str, category_hint: str = "") -> str:
        """Get the data category for a resource_id."""
        if category_hint and category_hint in self.rules_by_category:
            return category_hint
        for prefix, cat in RESOURCE_TO_CATEGORY.items():
            if resource_id.startswith(prefix):
                return cat
        return "UNKNOWN"

    def get_operation_info(self, action: str) -> dict:
        """Get operation details for a required action."""
        return ACTION_TO_OPERATION.get(action, {})

    def needs_remediation(self, current_state: str, required_action: str, data_category: str) -> bool:
        """Check if a resource needs remediation based on current state vs required action."""
        if required_action == "DELETE":
            return current_state not in ("ABSENT",)
        elif required_action == "REDACT":
            return current_state not in ("REDACTED",)
        elif required_action == "ANONYMIZE":
            return current_state not in ("ANONYMIZED",)
        elif required_action == "RETAIN":
            return False  # Retain = no change needed
        return False

    def is_compliant(self, current_state: str, required_action: str) -> bool:
        """Check if current state is compliant with required action."""
        if required_action == "DELETE":
            return current_state == "ABSENT"
        elif required_action == "REDACT":
            return current_state == "REDACTED"
        elif required_action == "ANONYMIZE":
            return current_state == "ANONYMIZED"
        elif required_action == "RETAIN":
            return current_state == "PRESENT"
        return False
