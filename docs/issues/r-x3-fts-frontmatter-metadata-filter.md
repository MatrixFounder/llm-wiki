---
id: R-X3-META-FILTER
type: known-issue
status: open
opened_at: 2026-06-01
category: ux
severity: SEV-3
slug: r-x3-fts-frontmatter-metadata-filter
---

# wiki-search can't filter by frontmatter metadata (status / severity / category)

- **Symptom**: After the R-X3 KNOWN_ISSUES migration, per-issue `docs/issues/*.md`
  files carry structured frontmatter (`status`, `severity`, `category`), but
  `wiki-search "status open"` / `wiki-search "SEV-2"` cannot filter by those
  values. `pages_fts` indexes only `title`, `tldr`, `body_excerpt`, and `tags`
  (`vault_id`/`slug`/`project` are `UNINDEXED`) — `pages.frontmatter_json` is
  stored but NOT projected into FTS. So a bare term like `open` matches the WORD
  "open" anywhere in bodies, not the `status:` field, and `severity` is
  unreachable via FTS. (Surfaced by the R-X3 dogfood — another agent expected
  `status:open` filtering and got body-text noise instead.)
- **Root cause**: by design, FTS5 indexes searchable *content* (title/body/tags),
  not arbitrary structured frontmatter fields. The tag-route already makes the
  *type* (`known-issue`) filterable via `--types`; per-issue `status`/`severity`
  are not tags. This is **pre-existing wiki-search behaviour**, newly relevant
  because R-X3 created status/severity-bearing per-issue files. NOT a TASK-012
  regression and NOT a correctness bug — the data is intact in
  `pages.frontmatter_json`.
- **Affected components**: `sql/wiki-index-v2.sql` (`pages_fts` columns),
  `scripts/wiki_skills/wiki_search.py` (no structured frontmatter filter flag).
- **Workaround (today)**: direct SQL —
  `SELECT slug FROM pages WHERE vault_id=? AND json_extract(frontmatter_json,'$.status')='open'`;
  or read the rendered `docs/KNOWN_ISSUES.md` ledger, which groups by `category`
  and shows `status`/`severity` inline per issue.
- **Fix options (deferred — enhancement, pick when status-filtering is a real
  pain)**:
  1. **Structured filter flag** — add `wiki-search --where 'status=open'` /
     `--status open` that compiles to a `json_extract(frontmatter_json,'$.<field>')`
     predicate (no schema change; reuses the existing column). Cleanest — keeps
     metadata as filters, not full-text.
  2. **`tag_from_frontmatter` layout option** — a per-layout config list (e.g.
     `[status, severity]`) that copies those frontmatter VALUES into `pages.tags`
     (which IS FTS-indexed), so `--types`/tag-match can filter them. Touches
     `normalize_frontmatter` + the layout schema; mind the FTS5-hyphen in values
     like `SEV-2` (the DF-1 query-sanitiser already covers the CLI path).
- **Prevention**: documented here; the rendered ledger keeps `status`/`severity`
  human-visible regardless.
