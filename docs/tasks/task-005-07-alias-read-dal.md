# Task 005-07: alias-read DAL — expand + collisions (R-5.5, R-5.6)

## Use Case Connection
- UC-12 (search expansion), UC-13 (lint collision)

## Task Goal
Add the two alias-read DAL methods: query expansion (for `wiki-search`) and collision detection (for `wiki-lint`), plus the `AliasCollision` model.

## Changes Description

### New Files
- (none — model added to existing `models.py`)

### Changes in Existing Files
#### File: `scripts/wiki_index/models.py`
- Add `@dataclass(frozen=True) class AliasCollision`: `vault_id: str`, `alias: str`, `slugs: list[str]`, `kind: str` (`"in_table"` | `"cross_slug"` | `"cross_name"` | `"frontmatter"`).

#### File: `scripts/wiki_index/repository.py` (ABC) + `scripts/wiki_index/sqlite_repository.py`
- `expand_query_aliases(self, vault_id: str, term: str) -> list[str]` — resolve `term` (via `resolve_entity`) → return `[canonical_name] + sibling_aliases` (bounded to the matched entity's own alias set; **no transitive expansion**, Q4 default). Empty list if `term` matches no entity/alias.
- `find_alias_collisions(self, vault_id: str) -> list[AliasCollision]` — (a) **in-table**: `GROUP BY alias HAVING COUNT(DISTINCT entity_slug) > 1` (only reachable on legacy/pre-migration rows); (b) **cross-table**: an `alias` equal to a *different* entity's `slug` or `name`. (Frontmatter-scan collisions are produced by the Lint Layer in 005-13, which reads files.)

## Test Cases
### Unit Tests (`tests/test_sqlite_repository.py`)
1. **TC-UNIT-01:** entity `hermes-agent` name "Hermes Agent" + aliases `["Hermes","HMS"]`; `expand_query_aliases(v,"Hermes")` → `{"Hermes Agent","Hermes","HMS"}` (set-equal).
2. **TC-UNIT-02:** `expand_query_aliases(v,"unknown")` → `[]`.
3. **TC-UNIT-03:** cross-table: alias `"foo"` equals another entity's slug `foo` → one `AliasCollision(kind="cross_slug")`.
4. **TC-UNIT-04:** in-table (insert via raw SQL bypassing the CLI to simulate a legacy/pre-migration DB) same alias → 2 slugs → `AliasCollision(kind="in_table")`.
### Regression
- `pytest tests/` green.

## Acceptance Criteria
- [ ] `expand_query_aliases` returns canonical name + sibling aliases, bounded; `[]` on miss.
- [ ] `find_alias_collisions` detects in-table + cross-slug + cross-name.
- [ ] `AliasCollision` model added + typed.
- [ ] `mypy --strict` clean; regression green.

## Notes
Phase-1: stubs (`[]`) + RED tests; Phase-2: logic. Depends on 005-01 + 005-04 (`resolve_entity`). Consumed by 005-12 (search) + 005-13 (lint).
