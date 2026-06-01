---
id: R-X3-MF-SCAN
type: known-issue
status: open
opened_at: 2026-06-01
category: performance
severity: SEV-3
slug: r-x3-metadata-filter-unindexed-scan
---

# wiki-search metadata filter is an unindexed json_extract scan + filesort

- **Symptom**: The TASK 013 (R-X3-META-FILTER) metadata filter compiles to
  `AND json_extract(p.frontmatter_json, ?) = ?` over the **unindexed**
  `pages.frontmatter_json` TEXT column. The metadata-only path
  (`wiki-search --status open …` with no FTS query) is therefore a full row scan
  of the selected vault/type/project partition — one JSON parse per surviving row
  — followed by a filesort for `ORDER BY p.project, p.slug, p.vault_id` (no index
  covers that tuple for the non-FTS path), with `LIMIT` applied only AFTER the
  sort. (Surfaced by the TASK 013 `/vdd-multi` critic-performance pass.)
- **Root cause**: by design — `pages.frontmatter_json` is not FTS-projected and
  has no expression index (TASK 006 / P-5 deliberately dropped the speculative
  `idx_pages_vault_tags` JSON index as dead write-weight). The filter trades an
  index for zero-DDL simplicity.
- **Affected components**: `scripts/wiki_index/sqlite_repository.py::search_pages`
  (the non-FTS branch + the `json_extract` predicates on the FTS branch).
- **Scale / acceptability**: imperceptible at the current live dev-vault (~277
  pages — sub-millisecond) and fine through ~1k pages (low single-digit ms). The
  `vault_id`/`type`/`project` filters DO hit existing indexes and prune the scan
  first, so the effective N is the narrowed partition, not the global row count.
  The result set is bounded by `--limit` (default 20). The FTS path
  (`query` + `--where`) runs `json_extract` only on the already-small MATCH
  candidate set — a non-issue. This is **no worse than a plain
  `SELECT … WHERE … LIMIT`**.
- **Trigger (when to fix)**: a single-vault partition exceeds ~1k pages AND the
  metadata-only path (no FTS query) is used routinely — the same ~1k–10k cliff as
  P-1..P-4. Until then, deferred.
- **Fix options (deferred — pick only when a field proves hot)**:
  1. **Expression index** on the actually-hot frontmatter field(s), e.g.
     `CREATE INDEX idx_pages_status ON pages(vault_id, json_extract(frontmatter_json,'$.status'))`.
     Pure-additive; do NOT pre-add speculatively (P-5 lesson) — add only when a
     real field is measured hot.
  2. **Generated column + index** for the hot field (mirrors the
     `tag_from_frontmatter` fix-option-2 sketched in R-X3-META-FILTER), if the
     predicate is on a stable, frequently-filtered field.
  Both fold naturally into the consolidation that handles P-1..P-4.
- **Prevention**: documented here with a concrete trigger so it isn't
  rediscovered; the `LIMIT`-bounded result + index-pruned partition keep it cheap
  at present scale.
