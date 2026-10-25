# Project Assumptions & Configuration

## 1. Model Selection & Pricing

- **Provider**: Google Gemini (sole configured provider per user instruction)
- **Model Choice**: `gemini-2.5-flash-lite`
  - Validated via `client.models.list()` using `GEMINI_API_KEY` from `.env.local`
  - Supports vision, multilingual text classification, and function calling
- **Pricing Source**: Google Cloud Vertex AI / Gemini API Official Pricing (October 2026)
  - Input tokens: \$0.075 per 1,000,000 tokens (\$0.000000075 / token)
  - Output tokens: \$0.30 per 1,000,000 tokens (\$0.00000030 / token)
- **Fallback / Alternative Model**: `gemini-2.5-flash` (\$0.15 / \$0.60 per 1M tokens)

---

## 2. Intent Classification Assumptions

- Requests for account deletion, erasure, closing, removal, or "right to be forgotten" in any language are processed as valid deletion requests (`COMPLETE` or `INCOMPLETE`).
- Requests for data access, downloading account archives/invoices, correction/rectification of name/phone, marketing-only unsubscribe, or explicitly requesting to keep the account active are classified as `NOT_APPLICABLE` with `steps_json = []`.
- Confirmed that exactly 10 cases (`case_533` to `case_542`) in `dataset/deletion_requests.csv` are non-deletion requests, perfectly aligning with the 10 `CLASSIFY_REQUEST` events in `dataset/system_activity.csv`.

---

## 3. Evidence & Verification Rules

- In `sample_output.csv`, `COMPLETE` cases cite the primary verification evidence file captured at or before `audit_at` (e.g. `evidence_92` for the 2026-09-15 cohort, `evidence_03` for the 2026-10-01 handover, `evidence_54` for early cases).
- In `INCOMPLETE` cases, findings cite the participant-visible evidence where the violation or active risk was observed, while proposed remediation and post-remediation verification steps carry an empty string for `evidence_id`.
- Accounts whose profile was successfully deleted but whose security audit record was preserved per policy are verified with `VERIFY_RECORD_ABSENT` (account) and `VERIFY_RECORD_PRESENT` (audit record).
