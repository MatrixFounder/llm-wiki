# Task 006-05: wiki-lint frontmatter-alias scan from the DB (P-10 + F12b)

## Ledger ids: P-10, F12b

## Goal
`lint._scan_frontmatter_alias_collisions` calls `frontmatter.load()` on every
`_concepts`/`_entities` file (a 2nd O(N) YAML sweep on top of `check_drift`) and
silently swallows parse errors. The aliases are already in `pages.frontmatter_json`
(concept pages are upserted into `pages`) — read them from the DB instead.

## Changes
### `scripts/wiki_index/lint.py`
- Rewrite `_scan_frontmatter_alias_collisions` (or fold into `run_all_checks`) to
  query `pages.frontmatter_json` for `_concepts`/`_entities`-tier rows and extract
  `$.aliases` via SQL `json_extract` / `json_each` (no `frontmatter.load`, no file I/O).
- Detect the same "surface claimed by ≥2 entity pages" condition; emit `kind="frontmatter"`.
- F12b: a row whose `frontmatter_json` is unparseable/missing-aliases is handled
  explicitly (not silently skipped) — e.g. ignored-with-note or surfaced.
- The function may now take `repo`/`conn` instead of `vault_root` (no file walk).

## Pre-flight (Risk R-2 / m-2)
- Verify `aliases` actually lands in `pages.frontmatter_json` for concept/entity
  rows (reindex passes `updated_fm`). If a concept page's aliases are NOT in
  `frontmatter_json`, KEEP the file-scan and flag — do not silently lose detection.

## Test cases (extend `tests/test_wiki_lint_alias_collision.py`)
1. Equivalence: the existing frontmatter-collision test (two pages claim "Dup")
   still reports `kind="frontmatter"` — now sourced from the DB.
2. No `frontmatter.load` / no file read remains in the scan path (assert via the
   reads being DB-only, e.g. it works with the vault dir removed but DB intact).
3. cross_slug / cross_name unchanged.

## Acceptance
- [ ] Frontmatter alias collisions detected from `pages.frontmatter_json`; zero file re-parse.
- [ ] F12b: malformed/missing handled explicitly, not swallowed.
- [ ] dogfood collision findings identical; `pytest`/`mypy --strict` green.

## Notes
Depends on 006-01 (v4 schema). The DB-sourced scan removes the double-sweep (P-10) AND the swallowed-parse (F12b) in one change.
