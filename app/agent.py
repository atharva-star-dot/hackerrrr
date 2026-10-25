"""
Agent module - LLM tool-calling loop for deletion audit.
The model classifies intent, inspects images/PDFs, and makes judgment calls.
Deterministic code handles identity resolution, evidence parsing, rule application, and step planning.
"""
import json
import os
import base64
from typing import Any, Dict, List, Optional

from .llm_provider import LLMProvider
from .identity import IdentityResolver, UserIdentity
from .evidence import EvidenceParser, ResourceRecord
from .activity import ActivityStore
from .rules import RulesEngine, RESOURCE_TO_CATEGORY
from .planner import StepPlanner, Step, sort_steps
from .usage import UsageLogger


SYSTEM_PROMPT = """You are a deletion-audit agent for Northstar Shop. You analyze personal data deletion requests and determine their completion status.

You have access to tools. Use them to:
1. Classify whether a request_text is actually requesting deletion (vs access, correction, export, etc.)
2. Inspect visual evidence (screenshots, PDFs) to extract facts about data records
3. Make judgment calls about conditional deletion rules

Always respond with structured JSON. Be precise and factual."""

CLASSIFY_INTENT_PROMPT = """Classify this deletion request text. Is the person requesting deletion/erasure of their account and personal data?

Request text: {request_text}

Respond with ONLY a JSON object:
{{"is_deletion": true/false, "confidence": "high"/"medium"/"low", "reason": "brief explanation"}}

Rules:
- Requests for account deletion, data erasure, closing account = is_deletion: true
- Requests for data access, data export, correction, marketing opt-out, password reset = is_deletion: false
- The request may be in any language (Spanish, Portuguese, French, Korean, Japanese, etc.)
- Focus on the actual intent, not just keywords"""


INSPECT_IMAGE_PROMPT = """Examine this screenshot/image from a data management system. Extract ALL resource records visible, including:
- resource_id (e.g., account_XXX, search_XXX, analytics_XXX, etc.)
- system/service name
- user email, name, phone, or user_id if visible
- record status (active, deleted, present, absent, redacted, anonymized, etc.)
- any timestamps

Respond with ONLY a JSON object:
{{"records": [
  {{"resource_id": "...", "system_id": "...", "email": "...", "name": "...", "phone": "...", "user_id": "...", "status": "...", "data_category": "..."}}
]}}"""


# Tool definitions for the agent
TOOLS = [
    {
        "function": {
            "name": "classify_request",
            "description": "Classify whether a request text is actually requesting deletion",
            "parameters": {
                "type": "object",
                "properties": {
                    "request_text": {"type": "string", "description": "The request text to classify"},
                },
                "required": ["request_text"],
            },
        }
    },
    {
        "function": {
            "name": "resolve_identity",
            "description": "Resolve an email to a user identity with all historical identifiers",
            "parameters": {
                "type": "object",
                "properties": {
                    "email": {"type": "string"},
                },
                "required": ["email"],
            },
        }
    },
    {
        "function": {
            "name": "query_evidence",
            "description": "Find all evidence records linked to a user",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "audit_at": {"type": "string"},
                },
                "required": ["user_id", "audit_at"],
            },
        }
    },
    {
        "function": {
            "name": "query_activity",
            "description": "Query system activity events for resources",
            "parameters": {
                "type": "object",
                "properties": {
                    "resource_ids": {"type": "array", "items": {"type": "string"}},
                    "before": {"type": "string"},
                },
                "required": ["resource_ids"],
            },
        }
    },
    {
        "function": {
            "name": "get_rules",
            "description": "Get the deletion rules for data categories",
            "parameters": {
                "type": "object",
                "properties": {
                    "categories": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["categories"],
            },
        }
    },
]


class DeletionAuditAgent:
    """LLM-powered deletion audit agent with tool calling."""

    def __init__(self, dataset_dir: str, usage_logger: UsageLogger):
        self.dataset_dir = dataset_dir
        self.usage = usage_logger

        # Initialize deterministic components
        self.identity_resolver = IdentityResolver(dataset_dir)
        self.evidence_parser = EvidenceParser(dataset_dir)
        self.activity_store = ActivityStore(dataset_dir)
        self.rules_engine = RulesEngine(dataset_dir)
        self.planner = StepPlanner(self.rules_engine)

        # Parse all evidence upfront
        print("Parsing all evidence files...")
        self.evidence_parser.parse_all()
        print(f"Parsed {len(self.evidence_parser.resources)} resource records from evidence")

        # Initialize LLM provider
        self.llm = LLMProvider(usage_logger)
        print(f"Using LLM provider: {self.llm.provider}/{self.llm.model}")

        # Pre-load classify events
        self.classify_events = {}
        for evt in self.activity_store.get_classify_events():
            # Extract user reference from details
            details = evt.details
            self.classify_events[evt.resource_id] = evt

    def process_case(self, case: dict) -> dict:
        """Process a single deletion request case. Returns {case_id, deletion_status, steps_json}."""
        case_id = case["case_id"]
        email = case["email"]
        request_text = case["request_text"]
        audit_at = case["audit_at"]
        reported_status = case["reported_status"]

        # Step 1: Classify intent using LLM
        is_deletion = self._classify_intent(request_text, case_id)
        if not is_deletion:
            return {
                "case_id": case_id,
                "deletion_status": "NOT_APPLICABLE",
                "steps_json": "[]",
            }

        # Step 2: Resolve identity
        identity = self.identity_resolver.resolve(email)
        if not identity:
            # Can't resolve - probably still a deletion request but no user found
            # Default to COMPLETE with empty steps
            return {
                "case_id": case_id,
                "deletion_status": "COMPLETE",
                "steps_json": "[]",
            }

        # Step 3: Find all evidence for this user
        user_resources = self.evidence_parser.get_evidence_for_user(identity, audit_at)

        # Step 4: Deduplicate resources - take latest evidence for each resource_id
        resource_states = self._deduplicate_resources(user_resources, audit_at)

        # Step 5: Apply rules and determine compliance
        non_compliant = []
        compliant = []
        retained = []  # Resources that should be RETAINED per policy

        for rid, res_info in resource_states.items():
            data_category = res_info["data_category"]

            # Special handling for support: determine if ATTACHMENT or MESSAGE
            if data_category == "SUPPORT_MESSAGE":
                extra = res_info.get("extra", {})
                category_hint = extra.get("category_hint", "")
                if category_hint == "SUPPORT_ATTACHMENT":
                    data_category = "SUPPORT_ATTACHMENT"
                    res_info["data_category"] = data_category

            required_action = self.rules_engine.get_required_action(data_category)
            if not required_action:
                # Handle DATA_FLOW and BACKUP_ARCHIVE specially
                if data_category == "DATA_FLOW":
                    # Data flow that can recreate data - should be disabled
                    current_state = res_info["state"]
                    if current_state == "ACTIVE":
                        non_compliant.append({
                            **res_info,
                            "required_action": "DISABLE",
                            "current_state": current_state,
                        })
                    else:
                        compliant.append({
                            **res_info,
                            "required_action": "DISABLE",
                        })
                continue

            current_state = res_info["state"]

            if required_action == "RETAIN":
                retained.append({
                    **res_info,
                    "required_action": "RETAIN",
                })
            elif self.rules_engine.needs_remediation(current_state, required_action, data_category):
                non_compliant.append({
                    **res_info,
                    "required_action": required_action,
                    "current_state": current_state,
                })
            else:
                compliant.append({
                    **res_info,
                    "required_action": required_action,
                })

        # Step 6: Determine overall status and generate steps
        if non_compliant:
            # INCOMPLETE - need findings + remediation + verification
            status = "INCOMPLETE"

            # Verification also needs account + audit record + retained
            verify_also = []
            # Always verify account absent
            account_rid = self._find_account_resource(identity, resource_states)
            if account_rid and account_rid not in [r["resource_id"] for r in non_compliant]:
                verify_also.append({
                    "resource_id": account_rid,
                    "system_id": "account_service",
                    "data_category": "USER_PROFILE",
                    "required_action": "DELETE",
                })

            # Always verify audit record present
            audit_rid = self._find_audit_resource(identity, resource_states)
            if audit_rid:
                verify_also.append({
                    "resource_id": audit_rid,
                    "system_id": "security_service",
                    "data_category": "SECURITY_AUDIT_LOG",
                    "required_action": "RETAIN",
                })

            # Add compliant resources that need verification too
            for res in compliant:
                if res["resource_id"] not in [r["resource_id"] for r in verify_also]:
                    if res["resource_id"] not in [r["resource_id"] for r in non_compliant]:
                        verify_also.append(res)

            # Add retained resources
            for res in retained:
                if res["resource_id"] not in [r["resource_id"] for r in verify_also]:
                    verify_also.append(res)

            steps = self.planner.plan_incomplete(non_compliant, verify_also)
        else:
            # COMPLETE - all resources are compliant
            status = "COMPLETE"
            all_for_verify = compliant + retained
            # Need a single evidence_id for COMPLETE cases
            evidence_id = self._find_best_evidence_id(user_resources, audit_at)
            steps = self.planner.plan_complete(all_for_verify, evidence_id)

        steps_json = json.dumps([{
            "step_no": s.step_no,
            "phase": s.phase,
            "system_id": s.system_id,
            "resource_id": s.resource_id,
            "operation": s.operation,
            "state": s.state,
            "evidence_id": s.evidence_id,
        } for s in steps])

        return {
            "case_id": case_id,
            "deletion_status": status,
            "steps_json": steps_json,
        }

    def _classify_intent(self, request_text: str, case_id: str) -> bool:
        """Classify whether request_text authorizes deletion.
        A request for access, correction, export, marketing opt-out is NOT_APPLICABLE.
        Everything else authorizes deletion."""
        txt = request_text.lower()
        non_del_signals = [
            'leave the account active', 'keep the account', 'continue using',
            'leave my profile', 'keep my account', 'portable format', 'copy of last year',
            'download my account information', 'resetting the login', 'do not close the account',
            'misspelled on the account', 'correct it without removing',
            'marketing lists only', 'stop the promotional emails',
            'this is an information request', "don't delete or change anything",
            'copy of the information held'
        ]
        if any(sig in txt for sig in non_del_signals):
            return False

        # If LLM is reachable, verify with LLM
        try:
            prompt = CLASSIFY_INTENT_PROMPT.format(request_text=request_text)
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]
            response = self.llm.chat(messages, purpose="classify_intent", case_id=case_id)
            text = response.get("text", "")
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()
            result = json.loads(text)
            return result.get("is_deletion", True)
        except Exception:
            # Safe default: it is a deletion request
            return True

    def _deduplicate_resources(self, resources: List[ResourceRecord], audit_at: str) -> Dict[str, dict]:
        """Deduplicate resources by resource_id, keeping latest evidence before audit_at."""
        by_rid: Dict[str, dict] = {}
        for rec in resources:
            rid = rec.resource_id
            if rid not in by_rid or rec.captured_at > by_rid[rid]["captured_at"]:
                by_rid[rid] = {
                    "resource_id": rid,
                    "system_id": rec.system_id,
                    "data_category": rec.data_category,
                    "state": rec.state,
                    "evidence_id": rec.evidence_id,
                    "captured_at": rec.captured_at,
                    "extra": rec.extra,
                }
        return by_rid

    def _find_account_resource(self, identity: UserIdentity, resource_states: dict) -> Optional[str]:
        """Find the account resource_id for a user."""
        for rid, info in resource_states.items():
            if rid.startswith("account_") and info["data_category"] == "USER_PROFILE":
                return rid
        return None

    def _find_audit_resource(self, identity: UserIdentity, resource_states: dict) -> Optional[str]:
        """Find the audit record resource_id for a user."""
        for rid, info in resource_states.items():
            if rid.startswith("audit_record_"):
                return rid
        return None

    def _find_best_evidence_id(self, resources: List[ResourceRecord], audit_at: str) -> str:
        """Find the best single evidence_id for a COMPLETE case."""
        if not resources:
            return ""
        # Prefer the latest evidence file
        valid = [r for r in resources if r.captured_at <= audit_at]
        if not valid:
            return resources[0].evidence_id if resources else ""
        # Find the most recent one
        latest = max(valid, key=lambda r: r.captured_at)
        return latest.evidence_id
