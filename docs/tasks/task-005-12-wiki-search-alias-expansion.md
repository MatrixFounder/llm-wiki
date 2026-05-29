# Task 005-12: `wiki-search` alias expansion, default on (R-5.5)

## Use Case Connection
- UC-12 (search with alias expansion)

## Task Goal
Make `wiki-search` expand a query through registered aliases **by default** (OR-expand the FTS MATCH with the matched entity's canonical name + sibling aliases), with `--no-expand-aliases` restoring byte-identical current behavior.

## Changes Description

### Changes in Existing Files
#### File: `scripts/wiki_skills/wiki_search.py`
- Add `--no-expand-aliases` flag (default = expansion ON).
- Before building the FTS query, call `repo.expand_query_aliases(vault_id, term)`; OR the returned surfaces into the MATCH expression (each quoted/escaped via the existing FTS-escaping). Empty expansion ⇒ plain query (no-op). Respect `--vaults` scoping.
#### File: `scripts/wiki_index/sqlite_repository.py`
- `search_pages` stays the FTS executor; expansion happens at the CLI/query-build layer (OR-terms passed in), so BM25 ordering math is unchanged beyond the added OR terms.

## Test Cases
### E2E (`tests/test_wiki_search.py`)
1. **TC-E2E-01:** `hermes-agent` has aliases `["Hermes Framework"]`; a page mentions only "Hermes Framework". `wiki-search V "Hermes"` (default) → that page is returned. *(RED before expansion.)*
2. **TC-E2E-02:** `wiki-search V "Hermes" --no-expand-aliases` → that page is **not** returned (byte-identical to pre-005 output for the same fixture).
3. **TC-E2E-03:** a term matching no alias → identical result set with and without the flag (expansion no-op).
### Regression
- Existing `test_wiki_search` cases (no aliases in fixture) pass unchanged under default-on.

## Acceptance Criteria
- [ ] Default expands via `expand_query_aliases`; `--no-expand-aliases` byte-identical to today.
- [ ] Expansion respects `--vaults`; no-op when term matches no alias.
- [ ] `mypy --strict` clean; regression green.

## Notes
Phase-1: flag parsed, default path == current behavior + RED expansion test; Phase-2: wire `expand_query_aliases`. Depends on 005-07. Risk R-3 (output change) mitigated by the byte-identical opt-out + no-op-on-no-alias.
