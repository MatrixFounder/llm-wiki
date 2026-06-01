---
id: N-008-1
type: known-issue
status: documented
opened_at: 2026-05-29
category: uncategorized
slug: n-008-1-exit-6-for-a-fail-verdict-diverges-from-the-family-6-error-convention
---

# `exit 6` for a FAIL verdict diverges from the family `6=error` convention

- **Symptom/Note**: `wiki-verify-multi apply` returns **exit 6** on a FAIL verdict,
  but `6` is the wiki-CLI family's generic *error* code (`_common.emit`). A FAIL
  is a SUCCESS envelope (the verdict page IS filed; **no `error` key**).
- **Root cause**: operator decision D-008-3 — FAIL must be a non-zero machine
  signal, but every non-zero code reads as "error" somewhere in the family.
- **Resolution**: deliberate, documented divergence (adversarial-plan SEC-4).
  The `wiki-verify-multi` SKILL + `workflows/wiki-verify-multi.md` + `apply`'s
  inline contract require callers to **branch on the stdout `verdict` field**
  (not `$?==6`); `--fail-on=none` → exit 0. Off-by-default; the sole consumer
  today is the orchestrator-driven workflow.
