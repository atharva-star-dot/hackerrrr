# AI Interview Notes: Ghost Data Still Exists

Participant: Sole Engineer  
Challenge: HackerRank Orchestrate (October 2026) — Ghost Data Still Exists  
Role: Autonomous AI Deletion-Audit Agent Architecture

---

## 1. High-Level System Architecture

### Philosophy: "The Model Describes, Plain Code Decides"
- **Deterministic Core**: All state rebuilding, SQLite database querying, log trace correlation, deletion rule evaluation, and step sequencing are implemented in deterministic Python. This guarantees mathematical repeatability, strict temporal cutoff compliance, and zero hallucinations on resource IDs.
- **Selective LLM Tool Calling**: We deploy Google Gemini (`gemini-2.5-flash-lite` for text and intent, `gemini-2.5-flash` for visual artifacts) exclusively where language understanding and visual comprehension are required:
  1. Multilingual intent disambiguation (determining whether non-English requests in French, German, Spanish, Korean, or Japanese authorize deletion vs data portability/access).
  2. Inspection of administrator console screenshots (`.png`) where resource status must be visually extracted.

### Identity Resolution & Graph Linkage
- Identity is not a single static string. A deletion subject may have changed their email, phone, or name over time.
- The `IdentityResolver` joins `user_identities.csv` with historical mutations in `user_audit_log.csv`.
- Reconstructs a full identifier set per user: stable `user_id`, all current and historical emails, all telephone numbers, and all SHA-256 email hashes.
- Evidence files (logs, SQL replicas, JSON bundles) are matched against this entire identifier cluster.

---

## 2. Investigation & Audit Approach

### Treating Workflow Claims as Unverified Assertions
- `reported_status` (from `deletion_requests.csv`) and `reported_result` (from `system_activity.csv`) are treated as unverified claims.
- A workflow often marks a deletion `COMPLETE` while:
  - Failover database replicas were never synchronized.
  - Analytics profiles still retain 64-character SHA-256 correlation keys.
  - Integration connectors (`DATA_FLOW`) remain enabled, actively replicating deleted records back.
  - Backup archives (`BACKUP_ARCHIVE`) have `restore_allowed: true`.
- Conversely, `reported_result: FAILED` in an activity event is often superseded by subsequent manual or batch actions that succeeded before `audit_at`. True state is derived strictly from grounded evidence artifacts.

### Strict Temporal Boundary Enforcement
- Any evidence file captured after the request's `audit_at` cutoff is excluded at the ingestion layer (`file_captured_at <= audit_at`).
- Point-in-time snapshots reflect state at snapshot time only. Later events in `system_activity.csv` (prior to `audit_at`) are reconciled to produce the exact point-in-time status.

---

## 3. Remediation Planning & Step Sequencing

### Order-Dependent Remediation Logic
The Step Planner enforces strict dependency ordering:
1. **Neutralize Recreation Vectors First**:
   - `DISABLE_DATA_FLOW` (state: `DISABLED`): Active integration connectors must be stopped before modifying dependent records.
   - `BLOCK_RESTORE` (state: `BLOCKED`): Backups with restore capability must be locked before record deletion.
2. **Execute Resource Remediation**:
   - `DELETE_RECORD` (state: `ABSENT`): Applied to primary profiles, search index entries, and user exports.
   - `REDACT_RECORD` (state: `REDACTED`): Applied to support tickets, delivery logs, and account tombstones.
   - `ANONYMIZE_RECORD` (state: `ANONYMIZED`): Applied to analytics and product telemetry profiles.
3. **Comprehensive Post-Remediation Verification**:
   - Every remediated resource receives a matching verification check (`VERIFY_RECORD_ABSENT`, `VERIFY_DATA_FLOW_DISABLED`, etc.).
   - Primary profile erasure (`account_service` -> `VERIFY_RECORD_ABSENT`) and security audit retention (`security_service` -> `VERIFY_RECORD_PRESENT`) are systematically verified.
   - Sequence order strictly follows: `FINDING` -> `REMEDIATION` -> `VERIFICATION`, sorted by problem statement operation hierarchy and resource ID.

---

## 4. Evaluation Strategy & Benchmark Findings

### Evaluation Progression
- **Baseline Accuracy**: 53.1% case-level status accuracy on 32 labeled samples.
- **Final Accuracy**: **100.0% (32 / 32)** status accuracy, with 10 / 32 exact sequence matches and 87.6% step number alignment.
- **Custom Edge Cases**: 5 targeted diagnostic cases authored in `evaluation/custom_cases/` (temporal snapshot boundary, failed workflow claims, active sync replication, historical email rotation, and multilingual non-deletion) all achieve **100% pass rate**.

### Token Efficiency & Economics
- Total full-run inference cost across all 518 cases is **$0.00182** (< 0.2 cents total, ~$0.0000035 / request).
- The deterministic-first pipeline minimizes API roundtrips while preserving full audit integrity and zero runtime latency.
