# Evaluation Report: Ghost Data Still Exists

Evaluation Date: October 25, 2026  
Benchmark: 32 Labeled Public Samples (`sample_deletion_requests.csv` / `sample_output.csv`)  
Full Evaluation: 518 Requests (`dataset/deletion_requests.csv`) + 5 Custom Diagnostic Test Cases

---

## 1. Executive Summary & Benchmark Metrics

The Deletion-Audit Agent implements an autonomous, evidence-backed audit system designed to verify personal data erasure across distributed platforms, replicas, backups, logs, and external connectors.

| Metric | Baseline Score | Final Score | Improvement |
|---|---|---|---|
| **Case-Level Status Accuracy** | 53.1% (17 / 32) | **100.0% (32 / 32)** | **+46.9%** |
| **Step-Level Sequence Accuracy** | 9.4% (3 / 32) | **31.2% (10 / 32)** | **+21.8%** |
| **Total Step Count Fit** | 70 predicted / 193 expected | **177 predicted / 193 expected** | **+55.4%** |
| **Custom Cases Pass Rate** | N/A | **100.0% (5 / 5)** | **100%** |

### Field-Level Accuracy Breakdown (on 193 Total Expected Steps)

| Step Field | Baseline Accuracy | Final Accuracy | Matched / Expected Steps |
|---|---|---|---|
| `step_no` | 35.8% | **87.6%** | 169 / 193 |
| `phase` | 27.5% | **79.8%** | 154 / 193 |
| `evidence_id` | 20.7% | **84.5%** | 163 / 193 |
| `state` | 19.2% | **61.1%** | 118 / 193 |
| `system_id` | 17.6% | **60.1%** | 116 / 193 |
| `resource_id` | 17.6% | **59.1%** | 114 / 193 |
| `operation` | 16.1% | **57.5%** | 111 / 193 |

---

## 2. Failures Identified & Engineering Improvements

During the iterative audit loops, five critical failure categories were identified and systematically resolved in generic, rule-based architecture:

### 1. Temporal Boundary Violation (Snapshot Pollution)
- **Problem**: Snapshot bundles containing internal timestamps older than the file's capture date (e.g., `evidence_02` captured on `2026-09-17`) were inappropriately ingested for audits evaluated at earlier cutoffs (`audit_at: 2026-09-15`). This erroneously marked deleted accounts as `PRESENT`, turning compliant `COMPLETE` cases into false `INCOMPLETE` predictions (notably `case_26`).
- **Solution**: Implemented strict manifest capture-time enforcement (`file_captured_at <= audit_at`). Any evidence artifact generated after the case cutoff time is excluded at the ingestion level.

### 2. Log Correlation Key Ingestion Ordering
- **Problem**: High-volume log events in `analytics_platform` link historical accounts through SHA-256 hashed correlation keys. In initial versions, log state (`ANONYMIZED` vs `PRESENT`) was determined before email hash extraction ran, erroneously treating identifiable analytics records with remaining hash links as compliant (e.g., `case_12`).
- **Solution**: Restructured the log parsing pipeline into a two-pass trace-correlation engine. Lookup keys, correlation tokens, and 64-character SHA-256 identifiers are resolved into the record dictionary prior to compliance state evaluation.

### 3. Claim vs Proof Invalidation (`reported_status` / `reported_result`)
- **Problem**: Workflows routinely report `reported_status: COMPLETE` when downstream backups (`BACKUP_ARCHIVE`) or integration connectors (`DATA_FLOW`) remain active. Conversely, system activity logs occasionally report `reported_result: FAILED` even when subsequent primary replica snapshots show the record was successfully purged (HTTP 404).
- **Solution**: Decoupled decision logic from reported claims. The agent determines resource state exclusively from verified evidence captured at or before `audit_at`. Active backups and enabled sync connectors trigger `REPORT_RESTORE_RISK` and `REPORT_ACTIVE_DATA_FLOW` regardless of the high-level workflow report.

### 4. Post-Remediation Verification Completeness
- **Problem**: Baseline incomplete plans proposed remediation steps for non-compliant resources but failed to include required verification steps for user account tombstones and security audit records, leaving verification step sequences incomplete.
- **Solution**: Enhanced the Step Planner to guarantee that every `INCOMPLETE` plan includes verification of the primary user profile (`account_service` -> `VERIFY_RECORD_ABSENT`), verified presence of required security audit logs (`security_service` -> `VERIFY_RECORD_PRESENT`), and matching verification operations for each remediated resource.

### 5. Multilingual Intent & Request Authorization
- **Problem**: Evaluation cases contain requests in Spanish, French, German, Portuguese, Korean, and Japanese. Certain requests ask for data portability, password assistance, or explicit profile preservation rather than deletion. Treating all inputs as deletion requests produced false positives.
- **Solution**: Integrated Gemini 2.5 Flash Lite multilingual intent classification with comprehensive multilingual safety phrase filtering, correctly identifying non-deletion requests as `NOT_APPLICABLE` with `steps_json = []`.

---

## 3. Custom Evaluation Cases

To rigorously validate edge cases, 5 custom evaluation cases were authored under `evaluation/custom_cases/`:

### Custom Case 1: Stale Snapshot Temporal Boundary (`custom_01.json`)
- **Scenario**: A full backup snapshot captured on 2026-09-17 shows account records as `PRESENT`. However, the case audit cutoff is `audit_at: 2026-09-15T12:00:00Z`, where real-time API exports show HTTP 404 (`ABSENT`).
- **Expected Status**: `COMPLETE`
- **Result**: **PASS** (100%). The parser strictly honors `audit_at` temporal filtering and disregards the future snapshot.

### Custom Case 2: Failed Workflow Claim but Evidenced Absent (`custom_02.json`)
- **Scenario**: System activity logs show `reported_result: FAILED` for account deletion. However, primary failover replica and export evidence confirm the profile is completely absent.
- **Expected Status**: `COMPLETE`
- **Result**: **PASS** (100%). Proves that reported activity results are treated as claims, not conclusive proof.

### Custom Case 3: Active Data Flow Recreating Deleted Data (`custom_03.json`)
- **Scenario**: User profile was deleted from primary database, but an external synchronization connector (`DATA_FLOW`) remains active and enabled (`enabled: true`), presenting active replication risk.
- **Expected Status**: `INCOMPLETE`
- **Result**: **PASS** (100%). Agent outputs `REPORT_ACTIVE_DATA_FLOW`, orders `DISABLE_DATA_FLOW`, and requires `VERIFY_DATA_FLOW_DISABLED`.

### Custom Case 4: Historical-Only Email Identification (`custom_04.json`)
- **Scenario**: The requester submitted the deletion request using an old email address that was rotated 3 months ago in `user_audit_log.csv`.
- **Expected Status**: `INCOMPLETE`
- **Result**: **PASS** (100%). Identity Resolver reconstructs all historical emails and SHA-256 hashes, uncovering lingering records under the old identifier.

### Custom Case 5: Multilingual Non-Deletion Request (`custom_05.json`)
- **Scenario**: A complex German request explicitly asking for a portable data export while requesting to keep the account active (*"Schließen Sie mein Konto nicht, ich möchte es weiterhin aktiv nutzen"*).
- **Expected Status**: `NOT_APPLICABLE` (`steps_json = []`)
- **Result**: **PASS** (100%). Correctly routed and parsed as non-deletion without generating phantom audit findings.

---

## 4. Final Dataset Validation

- Evaluation requests processed: **518** (`dataset/deletion_requests.csv`)
- Output status distribution:
  - `INCOMPLETE`: 287 (55.4%)
  - `COMPLETE`: 221 (42.7%)
  - `NOT_APPLICABLE`: 10 (1.9%)
- Schema conformance: **100% valid** (`validate_output` checked against all HackerRank constraints).
- Consecutive numbering: **100% verified** (1..N for every case).
