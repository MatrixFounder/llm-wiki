---
id: H-PERF-3
type: known-issue
status: fixed
opened_at: 2026-05-28
category: security
severity: SEV-2
slug: h-perf-3-index-from-manifest-argparse-in-loop
---

# index_from_manifest argparse-in-loop

- **Symptom**: For each of up to 25 written concept pages per source, `_manifest_consumer.index_from_manifest` calls `wiki_index_upsert.main(argv)` which **re-parses argparse**, opens fresh `make_repo`, runs PRAGMA sweep, parses frontmatter, writes, closes — all per row. At 25 candidates × 1000 source pages = 25,000 argparse calls + connection cycles.
- **Root cause**: Subprocess-style invocation pattern reused in-process for "compatibility"; the supposedly-fast in-process path still does subprocess-shaped per-row work.
- **Affected components**: `scripts/wiki_skills/_manifest_consumer.py:91-139`, `scripts/wiki_skills/wiki_index_upsert.py` (only exposes `main(argv)`).
- **Fix plan**: Expose `wiki_index_upsert._upsert_one(parsed_args, repo)` as the programmatic entry point. Loop calls that, not `main(argv)`. Eliminates ~30-60s wall-clock per 1000 pages.
- **Resolution (2026-06-01, TASK 015 R-015-1/2)**: added `wiki_index_upsert.upsert_one(vault_id, src, vault_root, repo) → dict` (no argparse, caller-owned repo, returns envelope with private `_exit_code`; `main()` delegates). `index_from_manifest` now imports `upsert_one` at module load, opens ONE repo before the `written[]` loop (or reuses a caller-passed `repo`), and calls `upsert_one` per row — no per-row argparse/connection/PRAGMA cycle. `apply --ingest` threads its open repo through `dispatch_to_indexer(..., repo=repo)` so the whole invocation is one connection (vdd-multi CRITICAL fix). **Residual**: per-row `BEGIN IMMEDIATE`/COMMIT remain (SQLite forbids nesting; single-outer-transaction batching deferred — would need batch-mode upsert methods). Tests: `test_index_from_manifest_single_connection`, `test_upsert_one_no_argparse`, `test_dispatch_to_indexer_forwards_repo`.
