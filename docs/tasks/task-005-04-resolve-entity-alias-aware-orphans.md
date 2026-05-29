# Task 005-04: `resolve_entity` + alias-aware `find_orphan_links` (R-4.5, incl. R-4.5d)

## Use Case Connection
- UC-12 (alias resolution feeds search), UC-15 (merged-away slug not orphaned)

## Task Goal
Implement the Epic-7 read path. Promote `IndexRepository.resolve_entity` from its `NotImplementedError` stub to: resolve a canonical slug **or** an alias surface string → its `Entity` (confirmed or candidate); `None` on no match. Make `find_orphan_links` **alias-aware** (R-4.5d): a `page_entity_refs` target that matches a registered alias resolves to its entity and is **not** reported as an orphan.

## Changes Description

### Changes in Existing Files
#### File: `scripts/wiki_index/repository.py` (ABC)
- `resolve_entity` is already declared (currently `raise NotImplementedError`). Keep the signature `def resolve_entity(self, vault_id: str, slug: str) -> Entity | None`. Update docstring: now resolves slug **or alias**.

#### File: `scripts/wiki_index/sqlite_repository.py`
- Implement `resolve_entity`: (1) try `entities` by `(vault_id, slug)`; (2) on miss, resolve `slug` as an `entity_aliases.alias` → its `entity_slug` → fetch entity; (3) `None` on both misses. Hydrate `Entity.aliases` via `idx_aliases_entity`.
- `find_orphan_links` (~line 473): add a `LEFT JOIN entity_aliases a ON a.vault_id = r.vault_id AND a.alias = r.entity_slug` and extend the `WHERE … IS NULL` guard so a ref whose target is a known alias is not orphan.

## Test Cases
### Unit Tests (`tests/test_sqlite_repository.py`)
1. **TC-UNIT-01:** `resolve_entity(v, "hermes-agent")` → the Entity (by slug).
2. **TC-UNIT-02:** `resolve_entity(v, "Hermes")` where `"Hermes"` is an alias → the canonical `hermes-agent` Entity.
3. **TC-UNIT-03:** `resolve_entity(v, "nope")` → `None` (no raise).
4. **TC-UNIT-04:** a `page_entity_refs` row targeting alias `"Hermes"` → **not** in `find_orphan_links` output; a ref targeting a truly-unknown slug → still listed.
### Regression
- Existing orphan-link tests still pass (refs to real entities/pages unaffected).

## Acceptance Criteria
- [ ] `resolve_entity` resolves by slug and by alias; `None` on miss (no exception).
- [ ] `find_orphan_links` treats alias targets as resolved.
- [ ] Epic-7 `NotImplementedError` stub retired.
- [ ] `mypy --strict` clean; regression green.

## Notes
Phase-1: keep `resolve_entity` returning `None` + RED tests; Phase-2: implement. Depends on 005-01 (entity_aliases v3). Consumed by 005-07 (expand), 005-08 (merge), 005-12 (search).
