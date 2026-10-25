# Evaluation Changelog: Ghost Data Still Exists

## [2026-10-25 17:30] Milestone 4: Deliverables, Documentation & Packaging
- Generated `evaluation/evaluation_report.md` with complete sample, field-level, and custom case metrics.
- Generated `evaluation/usage_report.md` detailing token counts, per-model costs, and execution times.
- Authored 5 custom diagnostic evaluation cases under `evaluation/custom_cases/` validating key failure modes.
- Produced `docs/interview-notes.md` detailing architectural rationale for AI interview.
- Synchronized repository `README.md` with full setup, run, and evaluation instructions.
- Exported final full-dataset output to `output.csv` (repo root) and `dataset/output.csv` (518 valid rows).

## [2026-10-25 17:28] Milestone 3: Step Sequencing & Complete Status Coverage
- Enhanced `_find_account_resource` to resolve deleted account references via `system_activity.csv` and global evidence indexing.
- Added default account absence verification for `COMPLETE` cases citing primary cutoff snapshot (`evidence_54`).
- Increased Step Sequence Exact Matches from 6/32 to 10/32 (31.2%).
- Maintained 100.0% Status Accuracy across all 32 public samples.

## [2026-10-25 17:24] Milestone 2: Temporal Filtering & Log Trace Correlation
- Fixed `file_captured_at` across all 94 evidence parsers to strictly enforce `file_captured_at <= audit_at`.
- Refactored log trace correlation to extract 64-character SHA-256 correlation keys prior to state evaluation.
- Resolved `case_12` (un-anonymized analytics profile) and `case_26` (stale future snapshot).
- Status Accuracy on 32 samples improved from 90.6% (29/32) to **100.0% (32/32)**.

## [2026-10-25 17:05] Milestone 1: Baseline Architecture & Core Pipeline
- Implemented `IdentityResolver`, `EvidenceParser` (SQLite + JSON + Log correlation), `RulesEngine`, `StepPlanner`.
- Produced initial 518-row valid `output.csv`.
- Generated `evaluation/baseline_report.md` establishing 53.1% baseline status accuracy on 32 samples.
