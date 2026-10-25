# Decision Logic: Northstar Shop Deletion Audit

## 1. Request Intent Classification

Before investigating records, `request_text` is evaluated to determine whether the subject genuinely authorized deletion:
- **Deletion Requests**: Requests to erase personal data, delete account, purge customer information, right to be forgotten (GDPR Art. 17). Status: Proceed to audit (`COMPLETE` or `INCOMPLETE`).
- **Non-Deletion Requests**: Requests for data access (GDPR Art. 15), data portability / export (Art. 20), rectification (Art. 16), marketing opt-outs, or general inquiries.
  - Action: Output `deletion_status = NOT_APPLICABLE` and `steps_json = []`.
  - Multilingual support covers English, Spanish, Portuguese, French, Korean, and Japanese.
  - Cross-referenced with `CLASSIFY_REQUEST` events in `system_activity.csv`.

---

## 2. Policy Rule Application Matrix (`deletion_rules.csv`)

| Rule ID | Category | Condition | Required Action | Remediation Op (if non-compliant) | Target State | Verification Op | Verification State |
|---|---|---|---|---|---|---|---|
| rule_01 | USER_PROFILE | Always | DELETE | DELETE_RECORD | ABSENT | VERIFY_RECORD_ABSENT | ABSENT |
| rule_02 | SECONDARY_IDENTIFIER | Always | DELETE | DELETE_RECORD | ABSENT | VERIFY_RECORD_ABSENT | ABSENT |
| rule_03 | SEARCH_INDEX_ENTRY | Always | DELETE | DELETE_RECORD | ABSENT | VERIFY_RECORD_ABSENT | ABSENT |
| rule_04 | CACHE_ENTRY | Always | DELETE | DELETE_RECORD | ABSENT | VERIFY_RECORD_ABSENT | ABSENT |
| rule_05 | SUPPORT_MESSAGE | Shared context | REDACT | REDACT_RECORD | REDACTED | VERIFY_RECORD_REDACTED | REDACTED |
| rule_06 | SUPPORT_ATTACHMENT | Subject only | DELETE | DELETE_RECORD | ABSENT | VERIFY_RECORD_ABSENT | ABSENT |
| rule_07 | ANALYTICS_PROFILE | Attributable | ANONYMIZE | ANONYMIZE_RECORD | ANONYMIZED | VERIFY_RECORD_ANONYMIZED | ANONYMIZED |
| rule_08 | PRODUCT_TELEMETRY | Attributable | ANONYMIZE | ANONYMIZE_RECORD | ANONYMIZED | VERIFY_RECORD_ANONYMIZED | ANONYMIZED |
| rule_09 | USER_EXPORT | Always | DELETE | DELETE_RECORD | ABSENT | VERIFY_RECORD_ABSENT | ABSENT |
| rule_10 | MARKETING_PROFILE | Always | DELETE | DELETE_RECORD | ABSENT | VERIFY_RECORD_ABSENT | ABSENT |
| rule_11 | EMAIL_DELIVERY_LOG | Contains email | REDACT | REDACT_RECORD | REDACTED | VERIFY_RECORD_REDACTED | REDACTED |
| rule_12 | SECURITY_AUDIT_LOG | Within retention | RETAIN | (None) | PRESENT | VERIFY_RECORD_PRESENT | PRESENT |
| rule_13 | LEGAL_HOLD_RECORD | Active hold | RETAIN | (None) | PRESENT | VERIFY_RECORD_PRESENT | PRESENT |
| rule_14 | BACKUP_ARCHIVE | Blockable | RETAIN | BLOCK_RESTORE | BLOCKED | VERIFY_RESTORE_BLOCKED | BLOCKED |
| rule_15 | ACCOUNT_TOMBSTONE | Tombstone | REDACT | REDACT_RECORD | REDACTED | VERIFY_RECORD_REDACTED | REDACTED |

Additionally:
- **DATA_FLOW**: If active sync/connector exists, it must be disabled:
  - Finding: `REPORT_ACTIVE_DATA_FLOW` (`ACTIVE`)
  - Remediation: `DISABLE_DATA_FLOW` (`DISABLED`)
  - Verification: `VERIFY_DATA_FLOW_DISABLED` (`DISABLED`)
- **BACKUP_ARCHIVE**: If restore is not blocked:
  - Finding: `REPORT_RESTORE_RISK` (`ACTIVE`)
  - Remediation: `BLOCK_RESTORE` (`BLOCKED`)
  - Verification: `VERIFY_RESTORE_BLOCKED` (`BLOCKED`)

---

## 3. Overall Deletion Status Determination

1. **`NOT_APPLICABLE`**: `request_text` does not authorize deletion. `steps_json = []`.
2. **`COMPLETE`**:
   - Every identified resource matches its required policy state at `audit_at`.
   - No active recreation flows exist (`DATA_FLOW` disabled, `BACKUP` restore blocked).
   - `steps_json` contains **only** `VERIFICATION` steps proving the compliant state at `audit_at`.
   - Each verification step cites the grounded `evidence_id` proving that state.
3. **`INCOMPLETE`**:
   - One or more resources violate policy (e.g. `USER_PROFILE` still `PRESENT`, `ANALYTICS_PROFILE` still attributable, active `DATA_FLOW`, unblocked `BACKUP`).
   - `steps_json` contains:
     1. `FINDING` steps citing participant-visible evidence.
     2. Ordered `REMEDIATION` steps (empty `evidence_id`).
     3. Post-remediation `VERIFICATION` steps (empty `evidence_id`).

---

## 4. Ordering Contract

Within `steps_json`, steps are strictly ordered by:
1. **Phase**: `FINDING` (0) -> `REMEDIATION` (1) -> `VERIFICATION` (2)
2. **Operation**:
   - `FINDING`: `REPORT_REMAINING_RECORD` -> `REPORT_EXPOSED_PII` -> `REPORT_ACTIVE_DATA_FLOW` -> `REPORT_RESTORE_RISK`
   - `REMEDIATION`: `DISABLE_DATA_FLOW` -> `BLOCK_RESTORE` -> `DELETE_RECORD` -> `REDACT_RECORD` -> `ANONYMIZE_RECORD`
   - `VERIFICATION`: `VERIFY_RECORD_ABSENT` -> `VERIFY_RECORD_PRESENT` -> `VERIFY_RECORD_REDACTED` -> `VERIFY_RECORD_ANONYMIZED` -> `VERIFY_DATA_FLOW_DISABLED` -> `VERIFY_RESTORE_BLOCKED`
3. **System ID**: Ascending alphabetical (e.g., `account_service` < `search_service`).
4. **Resource ID**: Ascending alphabetical / numerical.
