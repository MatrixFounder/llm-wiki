---
id: Q17
type: known-issue
status: documented
opened_at: 2026-05-28
category: quality
slug: q17-source-not-found-vs-invalid-source-path-info-disclosure-oracle
---

# SOURCE_NOT_FOUND vs INVALID_SOURCE_PATH info-disclosure oracle

- **Symptom**: `prepare` differentiates `SOURCE_NOT_FOUND` (file does not exist) from `INVALID_SOURCE_PATH` (absolute path passed) from `INVALID_SOURCE_SLUG` (dotted filename). An attacker probing the vault could use the envelope shape to fingerprint which path classes get which response.
- **Root cause**: Distinct envelopes chosen for operator UX clarity over information-hiding.
- **Affected components**: `scripts/wiki_skills/wiki_extract_concepts.py::prepare`.
- **Fix plan**: Collapse to a single `INVALID_SOURCE` envelope. Defer until multi-tenant scenarios emerge — current scope is operator-trusted; the differentiation is materially helpful for debugging.

---
