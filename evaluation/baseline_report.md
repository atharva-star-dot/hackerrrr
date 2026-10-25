# Baseline Evaluation Report (32 Labeled Samples)

Evaluated on: 2026-10-25

## 1. Summary Metrics

| Metric | Score | Matches / Total |
|---|---|---|
| **Case-Level Status Accuracy** | **53.1%** | 17 / 32 |
| **Step-Level Exact Match** | **9.4%** | 3 / 32 |
| **Sequence Accuracy** | **9.4%** | 3 / 32 |
| Total Expected Steps | 193 | - |
| Total Predicted Steps | 70 | - |

## 2. Field-Level Accuracy

| Field | Accuracy | Matched / Expected Steps |
|---|---|---|
| `step_no` | 35.8% | 69 / 193 |
| `phase` | 27.5% | 53 / 193 |
| `system_id` | 17.6% | 34 / 193 |
| `resource_id` | 17.6% | 34 / 193 |
| `operation` | 16.1% | 31 / 193 |
| `state` | 19.2% | 37 / 193 |
| `evidence_id` | 20.7% | 40 / 193 |

## 3. Top 5 Failure Categories & Examples

### Missed Finding (Resource Missing) (18 cases)

- **Case `case_07`**:
  - `expected_findings`: `['support_001']`
  - `got_findings`: `[]`
- **Case `case_08`**:
  - `expected_findings`: `['export_001']`
  - `got_findings`: `[]`

### Wrong Status (INCOMPLETE vs COMPLETE) (15 cases)

- **Case `case_07`**:
  - `expected`: `INCOMPLETE`
  - `got`: `COMPLETE`
- **Case `case_08`**:
  - `expected`: `INCOMPLETE`
  - `got`: `COMPLETE`

### Extra/Missing Verification Steps (28 cases)

- **Case `case_01`**:
  - `expected_verifications`: `['account_001']`
  - `got_verifications`: `[]`
- **Case `case_02`**:
  - `expected_verifications`: `['account_002']`
  - `got_verifications`: `[]`

### Missing Audit Record / Account Verification (0 cases)

No failures observed in this category.

### Wrong Evidence ID Cited (0 cases)

No failures observed in this category.

