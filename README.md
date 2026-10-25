# HackerRank Orchestrate — Ghost Data Still Exists

AI-Powered Deletion-Audit Agent for Northstar Shop  
Challenge URL: https://www.hackerrank.com/contests/hackerrank-orchestrate-october26/challenges/ghost-data-still-exists

---

## 1. Overview

**Ghost Data Still Exists** is an enterprise deletion-audit system that evaluates deletion requests across distributed systems, databases, failover replicas, search indexes, analytics platforms, backups, logs, and external data flows. 

A workflow may claim `reported_status: COMPLETE`, but personal data often persists in:
- Unsynchronized failover replicas
- Search index clusters (`search_service`)
- Un-anonymized analytics profiles retaining email hashes (`analytics_platform`)
- Un-redacted customer support tickets or attachments (`support_platform`)
- Active cloud sync connectors (`DATA_FLOW`) that recreate deleted profiles
- Active backup archives (`BACKUP_ARCHIVE`) allowing unblocked restoration

The agent resolves historical and current identities, applies statutory deletion policies (`deletion_rules.csv`), reconstructs true state at each case's `audit_at` cutoff, and produces valid ordered remediation and verification plans.

---

## 2. Architecture & Design Principles

```
                               ┌────────────────────────────────┐
                               │  dataset/deletion_requests.csv │
                               └───────────────┬────────────────┘
                                               │
                                               ▼
                                ┌──────────────────────────────┐
                                │ Multilingual Intent Router   │
                                │ (Gemini 2.5 Flash Lite)      │
                                └──────┬───────────────┬───────┘
                                       │               │ Non-Deletion / Portability
                                       │ Deletion      ▼
                                       │         ┌───────────────────┐
                                       │         │  NOT_APPLICABLE   │
                                       │         │   steps_json=[]   │
                                       │         └───────────────────┘
                                       ▼
┌─────────────────────────┐     ┌──────────────────────────────┐
│  user_identities.csv    │────▶│      Identity Resolver       │ (Historical emails, phones,
│  user_audit_log.csv     │     │ (user_id, emails, SHA256)    │  email hashes)
└─────────────────────────┘     └──────────────┬───────────────┘
                                               │
┌─────────────────────────┐                    ▼
│  94 Evidence Files:     │     ┌──────────────────────────────┐
│  - SQLite SQL exports   │────▶│    Evidence Parser & Store   │ (Temporal filtering:
│  - JSON service exports │     │  (Trace Correlation Engine)  │  file_captured_at <= audit_at)
│  - Log streams          │     └──────────────┬───────────────┘
│  - PNG admin screens    │                    │
└─────────────────────────┘                    ▼
                                ┌──────────────────────────────┐
                                │     Rules & State Auditor    │ (Checks against
                                │   (15 Deletion Rules)        │  deletion_rules.csv)
                                └──────────────┬───────────────┘
                                               │
                                               ▼
                                ┌──────────────────────────────┐
                                │      Step Sequence Planner   │ (Orders FINDING ->
                                │  (Ordered Action Engine)     │  REMEDIATION -> VERIFICATION)
                                └──────────────┬───────────────┘
                                               │
                                               ▼
                                ┌──────────────────────────────┐
                                │     output.csv (518 rows)    │
                                └──────────────────────────────┘
```

### Key Principles
1. **Model Describes, Plain Code Decides**: Deterministic Python parses SQLite databases, JSON service exports, and structured logs, and executes state reconciliation. The LLM (Gemini 2.5 Flash Lite / Flash) is invoked for subjective multilingual intent and visual console inspection.
2. **Claims are Not Proof**: `reported_status` and `reported_result` are treated as unverified assertions. State at `audit_at` is established solely through grounded evidence captured at or before the cutoff time.
3. **Preserve Tombs & Required Retentions**: Account tombstones (`ACCOUNT_TOMBSTONE`) keep only stable internal references; security audit records (`SECURITY_AUDIT_LOG`) are preserved with `VERIFY_RECORD_PRESENT`.
4. **Order-Dependent Remediation**: Active data flows (`DISABLE_DATA_FLOW`) and restore risks (`BLOCK_RESTORE`) must be neutralized before modifying downstream records.

---

## 3. Setup & Installation

### Requirements
- Python 3.10+ (tested on Python 3.12)
- Dependencies: standard library + `google-genai` / `pypdf` (optional for PDFs)

```bash
# Clone the repository
git clone https://github.com/interviewstreet/hackerrank-orchestrate-october26.git
cd hackerrank-orchestrate-october26

# Optional: configure Gemini API key in env.local
echo GEMINI_API_KEY=your_key_here > env.local
```

---

## 4. Execution Commands

### Run Full 518-Case Evaluation Pipeline
```bash
python code/main.py
```
This processes all 518 cases from `dataset/deletion_requests.csv`, performs atomic validation, and writes the completed submission to `output.csv` (at repo root) and `dataset/output.csv`.

### Evaluate on 32 Public Samples
```bash
python code/evaluate_samples.py
```
Outputs case-level status accuracy (100.0%) and step exact sequence match count.

### Run 5 Custom Diagnostic Test Cases
```bash
python code/evaluate_custom_cases.py
```
Tests edge cases including temporal boundary enforcement, failed workflow claims, active sync replication, and multilingual non-deletion intents (100% pass rate).

---

## 5. Deliverables & Evaluation Reports

- **Prediction Submission**: [`output.csv`](./output.csv) (518 valid, sorted rows)
- **Evaluation Report**: [`evaluation/evaluation_report.md`](./evaluation/evaluation_report.md)
- **Token & Cost Report**: [`evaluation/usage_report.md`](./evaluation/usage_report.md)
- **AI Interview Preparation**: [`docs/interview-notes.md`](./docs/interview-notes.md)
- **Log / Chat Transcript**: [`log.txt`](./log.txt)
