---
id: P-9
type: known-issue
status: open
opened_at: 2026-05-28
category: performance
severity: SEV-3
slug: p-9-missing-concept-files-o-n-stat-sweep-in-prepare
---

# missing_concept_files O(N) stat sweep in prepare

- **Symptom**: `prepare` iterates every known entity and stat-checks `_concepts/<slug>.md` for disk/DB drift. At ~100 entities ~10ms; at 10k entities approaches 1000ms (Karpathy-scale wiki).
- **Root cause**: Eager O(N) implementation chosen for v3.1 simplicity.
- **Affected components**: `scripts/wiki_skills/wiki_extract_concepts.py::prepare`.
- **Fix plan**: Add `--check-drift` flag (default off) for lazy mode, OR SQL-JOIN against a materialized manifest table maintained by `wiki-reindex`. Documented in TASK v3.1 Q16.
