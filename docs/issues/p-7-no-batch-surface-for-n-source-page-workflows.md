---
id: P-7
type: known-issue
status: fixed
opened_at: 2026-05-28
category: performance
severity: SEV-2
slug: p-7-no-batch-surface-for-n-source-page-workflows
---

# no batch surface for N-source-page workflows

- **Symptom**: Each source page requires a separate `prepare` + orchestrator synthesis + `apply` round-trip. For vault-wide re-extraction of 100 pages, the operator pays 100 process spawns + 100 SQLite cold-opens.
- **Root cause**: v3.1 intentionally scopes to single-page UX; batching deferred for surface-area reasons.
- **Affected components**: `scripts/wiki_skills/wiki_extract_concepts.py` (prepare, apply).
- **Fix plan**: `prepare --batch <slugs.json>` + `apply --batch-candidates <combined.json>` — non-trivial schema validation + manifest aggregation work. Not on the v3.1 critical path.
- **Resolution (2026-06-01, TASK 015 R-015-4/5)**: both batch surfaces shipped. `prepare --batch <slugs.json>` (mutex with `--source-page`): one repo, `known_concepts` + drift swept once, per-slug `_recon_single` with per-entry error isolation → `{"batch": […]}`. `apply --batch-candidates <combined.json>` (mutex with `--candidates-file`/`--candidates-stdin`): one repo reused across all entries, per-entry `_apply_candidates_to_db`, `--ingest` dispatches once per entry on the shared repo, per-entry isolation → `{"batch": […]}`. Both `INVALID_BATCH_FILE` (exit 2) on malformed input. Tests: `test_prepare_batch_*`, `test_apply_batch_*`.
