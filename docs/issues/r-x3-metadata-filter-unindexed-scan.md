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
- **TASK 033 note (list-membership branch)**: the `--where`/`--tag` predicate now
  also matches a LIST member via `OR EXISTS (SELECT 1 FROM json_each(frontmatter_json,
  ?) WHERE value = ?)` (TASK 033 / Q-033-1). This stacks a second per-row JSON parse
  on the scalar-miss branch (OR short-circuits on a scalar hit) — same unindexed scan
  class, bounded by per-page array length. **Neither fix-option above helps the
  membership branch**: an expression index on `json_extract(…,'$.field')` accelerates
  only the scalar `=` branch. The natural remedy for `tags`-membership is the FTS-tags
  projection (`pages_fts` already indexes `json_extract(…,'$.tags')`) or a normalized
  tag table — fold that in when this residual is addressed.
- **TASK 034 note (`--as-of` temporal branch)**: `wiki-search --as-of` adds
  `COALESCE(substr(json_extract(frontmatter_json,'$.valid_from'),1,10), p.date)` +
  `substr(json_extract(…,'$.valid_to'),1,10)` predicates (scalar `json_extract`, plus a
  correlated `NOT EXISTS` successor-walk that IS index-backed via `idx_refs_page` + the
  `pages` PK). The two `valid_from`/`valid_to` reads are the **same unindexed scalar-
  `json_extract` scan class** as the original `--where =` branch — and, unlike the TASK
  033 `json_each` membership branch, they **ARE** a co-beneficiary of fix-option 1/2: a
  generated `valid_from`/`valid_to` STORED column + index would accelerate the temporal
  filter in the same stroke as the hot `--where` field. Bounded by `--limit` + the
  vault/type/project partition prune; imperceptible at present scale (perf-critic
  `/vdd-multi` pass: LOW, no new regression). Fold into the same consolidation.
