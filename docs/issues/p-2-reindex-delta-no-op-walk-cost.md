---
id: P-2
type: known-issue
status: open
opened_at: 2026-05-26
category: performance
slug: p-2-reindex-delta-no-op-walk-cost
---

# reindex_delta no-op walk cost

- **Symptom**: `reindex_delta` calls `discover_pages` (rglob over `_sources/_concepts/_entities` × root + course tier) + `path.stat()` on every page + `SELECT slug, project FROM pages` + set membership. No-op delta at 10k pages risks blowing the 2 s SLO.
- **Root cause**: `Path.rglob` allocates Path objects per entry; `stat()` invoked on every discovered file even if unmodified.
- **Affected components**: `scripts/wiki_index/reindex.py:reindex_delta`, `discover_pages`.
- **Fix plan**: Replace `Path.rglob` with `os.scandir`; persist mtime/size to avoid re-stat; pull `last_modified` from `pages` table for comparison. Profile after.
