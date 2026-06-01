---
id: Q-007-1
type: known-issue
status: open
opened_at: 2026-05-29
category: quality
severity: SEV-3
slug: q-007-1-wiki-query-apply-re-runs-the-full-retrieval-to-recompute-the-hash
---

# `wiki-query apply` re-runs the full retrieval to recompute the hash

- **Symptom**: `apply` re-runs the entire `prepare` retrieval (alias expansion +
  FTS + row hydration) solely to recompute `question_hash` for the
  `QUESTION_CHANGED` TOCTOU check — a second full FTS query per `apply`.
- **Root cause**: by design — re-retrieving is the TOCTOU mechanism (detects a
  corpus change between `prepare` and `apply`). Passing the hit set from
  `prepare` to `apply` instead would defeat the detection.
- **Affected**: `scripts/wiki_skills/wiki_query.py::apply` / `_retrieve`.
- **Fix plan**: acceptable — one extra bounded FTS query per filed answer. If a
  real vault shows latency, cache the retrieval signature. Pass at N=100.
