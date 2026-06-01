---
id: L-008-2
type: known-issue
status: documented
opened_at: 2026-05-29
category: logic
slug: l-008-2-verify-hash-keys-on-the-cited-source-set-not-source-content
---

# verify_hash keys on the cited-source SET, not source content

- **Symptom**: `wiki-verify-multi`'s `verify_hash = sha256(answer_hash ‖ ordered
  examined project/slug)` re-triggers a re-verify when the answer body changes or
  the cited-source *set* changes (add/remove a cite), but NOT when a cited source
  is rewritten **in place** (same slug, new body). `prepare` reports
  `is_unchanged=true` even though the grounding evidence shifted.
- **Root cause**: parity with TASK 007's `question_hash` (keys on the retrieved
  slug set, not content) — a deliberate idempotency-vs-cost trade-off.
- **Affected**: `scripts/wiki_skills/wiki_verify_multi.py::_verify_hash`.
- **Fix plan**: if a real "re-verify on source rewrite" need appears, fold each
  examined source's `pages.file_hash` into `verify_hash`. Deferred — the operator
  can `--force` a re-verify; the answer-body + cite-set anchors cover the common
  cases. (vdd-multi L-5.)

---
