---
id: P-1
type: known-issue
status: open
opened_at: 2026-05-26
category: performance
slug: p-1-reindex-full-per-page-transactions
---

# reindex_full per-page transactions

- **Symptom**: `reindex_full` calls `repo.upsert_page` + `repo.replace_refs` once per page; each opens its own `BEGIN IMMEDIATE`/`COMMIT`. At 10k pages → ~20k commits + FTS5 trigger work per commit. Projected ~60–120 s; tight against the 3-min SLO.
- **Root cause**: `upsert_page` invariant that it owns its own transaction (M-4 contract) prevents trivial wrapping in an outer BEGIN.
- **Affected components**: `scripts/wiki_index/reindex.py:reindex_full`, `scripts/wiki_index/sqlite_repository.py:upsert_page`.
- **Fix plan**: Introduce `repo.bulk_upsert_pages(iter[Page])` with executemany inside one tx; defer FTS5 maintenance (drop+rebuild triggers + bulk INSERT into pages_fts at end). Acceptable only when `enforce_slos` testing at N=10k is wired into CI.
