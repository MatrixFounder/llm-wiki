# Task 005-06: alias-write DAL — add/remove/list (R-5.1, R-5.2)

## Use Case Connection
- UC-11 (register / manage an alias)

## Task Goal
Add the Class B mirror writes behind `wiki-alias`: register, drop, and list aliases. `add_alias` must hard-fail on a PK `(vault_id, alias)` collision so the caller can map it to `ALIAS_COLLISION`.

## Changes Description

### Changes in Existing Files
#### File: `scripts/wiki_index/repository.py` (ABC) + `scripts/wiki_index/sqlite_repository.py`
Add abstractmethod + `SQLiteRepository` impl (land together):
- `add_alias(self, vault_id: str, alias: str, entity_slug: str, alias_type: str = "spelling_variant") -> None` — parameterized `INSERT INTO entity_aliases`. On PK collision where the existing row points at a **different** `entity_slug`, raise `AliasCollisionError` (new, in `sqlite_repository` or a shared errors module); a same-slug duplicate is a no-op (idempotent — caller reports `unchanged`).
- `remove_alias(self, vault_id: str, alias: str) -> bool` — `DELETE`; returns `True` if a row was removed.
- `list_aliases(self, vault_id: str, entity_slug: str) -> list[str]` — `SELECT alias … WHERE entity_slug=?` (uses `idx_aliases_entity`).

## Test Cases
### Unit Tests (`tests/test_sqlite_repository.py`)
1. **TC-UNIT-01:** `add_alias(v, "Hermes", "hermes-agent")` → row present; `list_aliases(v, "hermes-agent")` contains `"Hermes"`.
2. **TC-UNIT-02:** re-add the same `(alias, slug)` → no error, no duplicate (idempotent).
3. **TC-UNIT-03:** `add_alias(v, "Hermes", "hermes-bus")` after TC-01 → raises `AliasCollisionError` (different target).
4. **TC-UNIT-04:** `remove_alias(v, "Hermes")` → `True`; second call → `False`.
### Regression
- `pytest tests/` green.

## Acceptance Criteria
- [ ] `add_alias` writes the mirror; collision-with-different-slug raises; same-slug is idempotent.
- [ ] `remove_alias`/`list_aliases` behave per tests.
- [ ] `mypy --strict` clean; regression green.

## Notes
Phase-1: stubs + RED tests; Phase-2: logic. Depends on 005-01 (v3 PK). The Class A frontmatter `aliases:` mutation lives in the CLI (005-10), not here (DAL = Class B mirror only).
