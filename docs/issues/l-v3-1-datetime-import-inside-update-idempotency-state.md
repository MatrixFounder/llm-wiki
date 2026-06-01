---
id: L-V3.1
type: known-issue
status: fixed
opened_at: 2026-05-28
category: logic
slug: l-v3-1-datetime-import-inside-update-idempotency-state
---

# datetime import inside update_idempotency_state

- **Symptom**: `scripts/wiki_skills/wiki_extract_concepts.py::update_idempotency_state` did `from datetime import datetime as _dt, timezone as _tz` inside the function body instead of at module top.
- **Root cause**: Style inconsistency carried over from an earlier draft; worked correctly because Python caches modules in `sys.modules`.
- **Affected components**: `scripts/wiki_skills/wiki_extract_concepts.py`.
- **Resolution**: Hoisted to module top with the other stdlib imports. `update_idempotency_state` now uses `datetime.now(timezone.utc).isoformat()` directly. No behavior change. No new test (cosmetic).
