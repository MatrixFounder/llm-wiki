# Task 005-05: candidate-lifecycle DAL (R-4.2, R-4.3, R-4.4)

## Use Case Connection
- UC-09 (confirm), UC-10 (auto-promote)

## Task Goal
Add the DAL methods behind `wiki-confirm`: an **explicit** confirm/undo setter that **bypasses** the `MIN()` downgrade-guard (operator intent is authoritative), a candidate lister, a set-based mention recompute, and the threshold auto-promoter.

## Changes Description

### Changes in Existing Files
#### File: `scripts/wiki_index/repository.py` (ABC) + `scripts/wiki_index/sqlite_repository.py`
Add abstractmethod + `SQLiteRepository` implementation (land together — green-throughout):
- `set_entity_candidate(self, vault_id: str, slug: str, is_candidate: int) -> bool` — direct `UPDATE entities SET is_candidate=?, last_updated=?, canonicalized_by='human' WHERE vault_id=? AND slug=?`. **No MIN() guard** (unlike `upsert_entity`). Returns `True` if a row changed (for idempotent `changed:false`).
- `list_candidates(self, vault_id: str) -> list[Entity]` — `WHERE is_candidate=1` (uses `idx_entities_candidate`).
- `recompute_mentions(self, vault_id: str) -> None` — the existing set-based `UPDATE entities SET mentions_count = (SELECT COUNT(*) FROM page_entity_refs …)` (identical to reindex Step 3), extracted as a reusable method.
- `auto_promote_candidates(self, vault_id: str, threshold: int) -> list[str]` — call `recompute_mentions` first, then `UPDATE … SET is_candidate=0 WHERE is_candidate=1 AND mentions_count >= ?`; return promoted slugs.

## Test Cases
### Unit Tests (`tests/test_sqlite_repository.py`)
1. **TC-UNIT-01:** `set_entity_candidate(v, slug, 0)` on a candidate → row `is_candidate==0`, returns `True`; re-run → returns `False` (idempotent).
2. **TC-UNIT-02:** `set_entity_candidate(v, slug, 1)` on a confirmed entity → row flips to `1` (proves **MIN() guard bypassed**, unlike `upsert_entity`).
3. **TC-UNIT-03:** `list_candidates` returns only `is_candidate=1` rows.
4. **TC-UNIT-04:** seed refs so two candidates have 3 and 1 mentions; `auto_promote_candidates(v, 3)` → promotes only the 3-mention one; returns `["that-slug"]`; mention count was freshly recomputed (mutate refs then call → reflects new count).
### Regression
- `upsert_entity` MIN()-guard test still passes (re-extraction still cannot demote).

## Acceptance Criteria
- [ ] `set_entity_candidate` flips both directions, bypassing MIN(); idempotent return.
- [ ] `auto_promote_candidates` recomputes mentions first, promotes `>= threshold`, returns slugs.
- [ ] `upsert_entity` downgrade-guard regression intact.
- [ ] `mypy --strict` clean; regression green.

## Notes
Phase-1: stubs (raise/`[]`/no-op) + RED tests; Phase-2: logic. The `>=` boundary is binding (UC-10 AC). Consumed by 005-09 (wiki-confirm) and 005-08 (merge reuses `recompute_mentions`).
