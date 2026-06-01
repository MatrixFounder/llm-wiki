# task-013-03 — Close R-X3-META-FILTER + re-render ledger + docs

**Parent:** TASK 013. **Depends on:** 013-01 + 013-02. **RTM:** R-MF-11, R-MF-9 (final).

## Goal
Flip the issue closed, regenerate the Class-B ledger so it reflects the new
status, and document the feature. Verify the PW-Q drift guard stays green.

## Steps
1. **Close the Class-A issue** — edit
   `docs/issues/r-x3-fts-frontmatter-metadata-filter.md`:
   - frontmatter `status: open → fixed`.
   - Append a **Resolution** note: shipped fix-option 1 in TASK 013
     (`wiki-search --where 'field=value'` + `--status`/`--severity` sugar →
     parameterized `json_extract` predicate; zero DDL; query-less path).
   - Update the Workaround section to point at the real flag.
2. **Re-render the ledger** — `wiki-index-render --auto-indexes` (against
   `.wiki/index.db` for this dev-vault) so `docs/KNOWN_ISSUES.md` shows
   R-X3-META-FILTER as `fixed`. Confirm rebuildable byte-identical modulo
   GENERATED-AT.
   - NOTE: the live `.wiki/index.db` must be reindexed first
     (`wiki-reindex --full --db-path .wiki/index.db` or upsert the edited issue)
     so the render reads the new status.
3. **Lint** — `wiki-lint` must report no `auto-generated-drift` (PW-Q): the
   on-disk ledger == the freshly-rendered one.
4. **Docs**:
   - `README.md` — document `wiki-search --where 'field=value'` + `--status`/
     `--severity` (and the query-less listing form) in the search section /
     command table.
   - `scripts/wiki_skills/.AGENTS.md` — `wiki_search.py` gains the metadata filter.
   - `scripts/wiki_index/.AGENTS.md` — `search_pages` `where_fields` + non-FTS path.
   - `docs/ROADMAP.md` — mark **R-X3-META-FILTER ✅ DONE 2026-06-01 (TASK 013)**;
     update the R-X2 operator-follow-up #2 note (no longer a gap).
5. **Final regression** — full `pytest -q` green + `mypy --strict scripts/` clean.

## Acceptance
- ✅ Issue `status: fixed`; ledger re-rendered showing it under `ux`/fixed.
- ✅ `wiki-lint` no drift (R-MF-11).
- ✅ Live dogfood (PLAN §Verification 2): `wiki-search --status open --severity
  SEV-2 --vaults obsidian-llm-wiki --db-path .wiki/index.db` returns the open
  SEV-2 set (5 issues). (No `--types known-issue` — it's a tag, not a pages.type.)
- ✅ All existing tests pass; mypy strict clean (R-MF-9 final).

## Files
- `docs/issues/r-x3-fts-frontmatter-metadata-filter.md`
- `docs/KNOWN_ISSUES.md` (auto-rendered — do not hand-edit)
- `README.md`, `scripts/wiki_skills/.AGENTS.md`, `scripts/wiki_index/.AGENTS.md`,
  `docs/ROADMAP.md`
