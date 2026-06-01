---
id: P-8
type: known-issue
status: open
opened_at: 2026-05-28
category: performance
severity: SEV-2
slug: p-8-wal-pragma-setup-cost-compounded-across-the-two-process-workflow
---

# WAL PRAGMA setup cost compounded across the two-process workflow

- **Symptom**: The v3.1 two-pass (`prepare` then `apply`) opens **up to 4** fresh SQLite connections per source page when `--ingest` is set (prepare + apply + `_manifest_consumer.append_log_event` + per-written-entry `upsert_main`), each paying the WAL/journal/synchronous PRAGMA setup cost (~5ms each). v2 paid it once per invocation. At 1000 source pages with `--ingest`, that's ~20s pure overhead.
- **Root cause**: Process-boundary teardown between prepare and apply discards the connection; the in-process `_manifest_consumer` path still loops over `manifest["written"]` calling `wiki_index_upsert.main(argv)` which opens its own connection per page.
- **Affected components**: `scripts/wiki_index/sqlite_repository.py` (PRAGMA setup), `scripts/wiki_skills/wiki_extract_concepts.py` (process boundary), `scripts/wiki_skills/_manifest_consumer.py` (per-entry `make_repo` + `upsert_main` argparse-in-loop — see H-PERF-3 below).
- **Severity history**: bumped from SEV-3 to SEV-2 by vdd-multi 2026-05-28 (critic-performance) after counting the in-process indexer's per-row connection cycles, not just the prepare+apply boundary.
- **Fix plan**: (a) PRAGMA caching via connection pool; (b) in-process orchestration mode that batches multiple source pages through one prepare+apply cycle; (c) refactor `wiki_index_upsert` to expose a programmatic entry-point taking `(parsed_args, open_repo)` so the manifest-consumer loop reuses one connection. Out of scope for v3.1; track as H-PERF-1+3 follow-up.
