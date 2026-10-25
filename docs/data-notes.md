# Data Notes: Northstar Shop Deletion Audit

## 1. Overview of Data Sources

| File | Rows | Description |
|---|---|---|
| `deletion_requests.csv` | 518 | Primary evaluation dataset. Cases `case_33` to `case_550`. |
| `sample_deletion_requests.csv` | 32 | Labeled training/specification dataset. Cases `case_01` to `case_32`. |
| `sample_output.csv` | 32 | Reference outputs demonstrating exact status decisions, step ordering, and evidence citations. |
| `user_identities.csv` | 850 | Identity snapshot containing `user_id`, `name`, `email`, `phone`, `email_hash`, `updated_at`. |
| `user_audit_log.csv` | 306 | Historical modifications to identity fields (`email`, `phone`, `email_hash`, `name`). 100 requests use historical emails. |
| `system_activity.csv` | 4,011 | Global event stream (721 FAILED, 376 PARTIAL). Event types include `DELETE_RECORD`, `REDACT_RECORD`, `ANONYMIZE_RECORD`, `SYNC_RECORD`, `RESTORE_BACKUP`, `LINK_RESOURCE_IDENTITY`, `CLASSIFY_REQUEST`. |
| `deletion_rules.csv` | 15 | Policy rules specifying data categories, conditions, and actions (`DELETE`, `REDACT`, `ANONYMIZE`, `RETAIN`). |
| `evidence_files.csv` | 94 | Manifest of evidence files under `evidence/`. |

---

## 2. Evidence Formats and Linkage

1. **SQL Snapshots (`.sql`)**:
   - Primary and replica database dumps (failover, regional, reporting).
   - Format: SQLite-compatible `CREATE TABLE` and `INSERT INTO`.
   - Links: Direct `user_id`, `email`, `phone`, `full_name`.
   - State indicators: `account_status = 'DELETED'` vs `'ACTIVE'`.

2. **JSON Export Bundles (`.json`)**:
   - `service_resource_export_*.json`: Service point-in-time exports. Contains `profile_lookups` (status 404 = `ABSENT`, 200 = `PRESENT`), analytics profiles, and connectors.
   - `customer_data_snapshot_bundle_*.json`: Multi-collection snapshots (`customer_profiles`, `deleted_customer_references` / tombstones, `security_audit_events`).
   - Links: `subject_reference` (`user_XX`), `customer_reference`, `customer_email`, `email`.

3. **Log Files (`.log`)**:
   - Key-value formatted access and trace logs.
   - Lookups with `http_status=404` or `rows=0` prove `ABSENT`.
   - Search queries with `result=hit` prove `PRESENT`, `result=miss` prove `ABSENT`.
   - Connector logs indicate `enabled=true/false` (`ACTIVE`/`DISABLED`).
   - Backup logs indicate `restore_allowed=true/false` (`ACTIVE`/`BLOCKED`).

4. **Shift Handover Records (`customer_account_handover_20261001.txt`)**:
   - Delimited text: `TIMESTAMP | SYSTEM | RESOURCE_ID | CATEGORY | STATUS | IDENTIFIER`.
   - Directly records `NOT_FOUND` (`ABSENT`), `FOUND` (`PRESENT`), `IDENTIFIABLE` (`PRESENT`), `ANONYMIZED`, `REDACTED`, `ACTIVE`, `DISABLED`, `BLOCKED`.

5. **Screenshots & Documents (`.png`, `.pdf`)**:
   - Business artifacts capturing admin consoles, ticket views, audit ledgers, exports, and storage.
   - Linked to users via explicit `LINK_RESOURCE_IDENTITY` events in `system_activity.csv` (12 verified events).

---

## 3. Critical Temporal and Identity Rules

- **Temporal Boundary (`audit_at`)**: Only evidence and activity with `event_time <= audit_at` or `captured_at <= audit_at` may be used. Subsequent snapshots or activities must be ignored.
- **Claims vs Proof**: `reported_status` in `deletion_requests.csv` and `reported_result` in `system_activity.csv` are claims. For example, in `case_05`, reported status is `COMPLETE`, but `evidence_54` proves `account_005` is still `PRESENT` in `customer_profiles_failover_replica`.
- **Replication Drift & Recreation**: Synchronization (`SYNC_RECORD`) and restore (`RESTORE_BACKUP`) events can recreate deleted records. State must be verified at `audit_at`.
- **Identity Chaining**: 20 emails are mixed-case (case-insensitive normalization required). 100 emails exist solely in `user_audit_log.csv` as historical addresses.
