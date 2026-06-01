---
id: L-V3.2
type: known-issue
status: fixed
opened_at: 2026-05-28
category: logic
slug: l-v3-2-check-idempotency-missing-defensive-null-check
---

# check_idempotency missing defensive NULL check

- **Symptom**: `check_idempotency` compared `row["value"] == current_hash`. If a corrupt row existed with `value=NULL`, comparison was `False` (the right behavior) but no documentation surfaced the implicit reliance on the DB CHECK constraint.
- **Root cause**: `source_state.value` is `TEXT NOT NULL` per schema, so this case shouldn't arise. Implicit reliance on DB constraint.
- **Affected components**: `scripts/wiki_skills/wiki_extract_concepts.py::check_idempotency`.
- **Resolution**: Added explicit `if row is None or row["value"] is None: return False` with docstring referencing L-V3.2. Regression test `test_check_idempotency_handles_null_row_value` mocks the cursor to simulate a NULL row and asserts the False return.
