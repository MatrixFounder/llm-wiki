# Task 005-02: reindex reads `is_candidate` from frontmatter (R-4.1)

## Use Case Connection
- UC-14 (durability round-trip — candidate stays candidate)

## Task Goal
Close the read-side round-trip gap: `reindex_full` currently registers entities with `INSERT OR IGNORE (… no is_candidate col)` → schema default `0` (confirmed), silently confirming every candidate on a full rebuild. Make it **read** `is_candidate` from the entity-page frontmatter; an absent key ⇒ confirmed (`0`) for back-compat with pre-005 vaults.

## Changes Description

### Changes in Existing Files
#### File: `scripts/wiki_index/reindex.py`
- In `reindex_full` entity-registration block (~lines 243-274), extend the `INSERT` to include `is_candidate`, sourced from `updated_fm.get("is_candidate")`:
  - Normalize: truthy YAML `true`/`True`/`1` ⇒ `1`; missing/`false`/`0` ⇒ `0`.
  - Keep `INSERT OR IGNORE` semantics for the existing-row case (reindex_full wipes first per ADR-002 §D8, so this is effectively insert).
- Add a small helper `def _coerce_is_candidate(fm: dict) -> int` (module-private) with a docstring referencing R-4.1.

## Test Cases
### E2E Tests (`tests/test_reindex.py`)
1. **TC-E2E-01:** scaffold a vault with `_concepts/foo.md` frontmatter `is_candidate: true` → `reindex_full` → `entities` row `is_candidate == 1`. *(RED on current default-0 behavior.)*
2. **TC-E2E-02:** `_concepts/bar.md` with **no** `is_candidate` key → row `is_candidate == 0` (back-compat).
3. **TC-E2E-03:** `is_candidate: false` → row `is_candidate == 0`.
### Unit Tests
1. **TC-UNIT-01:** `_coerce_is_candidate` truth table over `True/"true"/1/False/"false"/0/None/absent`.
### Regression
- `pytest tests/test_reindex.py tests/` green.

## Acceptance Criteria
- [ ] `reindex_full` reads `is_candidate` from frontmatter; absent ⇒ 0.
- [ ] A candidate page survives `reindex --full` as `is_candidate=1`.
- [ ] Existing reindex tests still pass; `mypy --strict` clean.

## Notes
Phase-1 stub = record current default-0 behavior so the RED test fails first; Phase-2 = read the flag. Pairs with 005-14 (extract-concepts regression) and is exercised end-to-end by 005-16.
