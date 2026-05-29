# Task 005-08: `merge_entities` DAL + `MergeReport` model (R-4.7)

## Use Case Connection
- UC-15 (merge a duplicate entity into the canonical one)

## Task Goal
Add the single-transaction Class B mirror for a duplicate fold: re-point refs (PK-dedup), re-point/skip aliases, register redirect aliases, delete the `from` entity row, recompute `into.mentions_count`. The CLI (005-11) does the Class A mutations first and calls this.

## Changes Description

### Changes in Existing Files
#### File: `scripts/wiki_index/models.py`
- Add `@dataclass(frozen=True) class MergeReport`: `refs_repointed: int`, `aliases_absorbed: int`, `aliases_skipped: list[str]`.

#### File: `scripts/wiki_index/repository.py` (ABC) + `scripts/wiki_index/sqlite_repository.py`
- `merge_entities(self, vault_id: str, from_slug: str, into_slug: str) -> MergeReport` — in **one transaction** (`with conn:`):
  1. Re-point `page_entity_refs`: for each `from` ref, if `(page, into, ref_type)` already exists keep the higher `trust_level` and drop the `from` ref; else `UPDATE entity_slug = into`. (Implement as `INSERT OR IGNORE`-into-temp + dedup, or delete-conflicting-then-update — set-based, no per-row Python loop where avoidable.)
  2. Re-point `entity_aliases`: `UPDATE … SET entity_slug = into WHERE entity_slug = from`; on PK collision (alias already on `into`/another) skip + record in `aliases_skipped`.
  3. Register redirect aliases: `add`-style insert of `from_slug` + `from`'s `name` as aliases of `into` with `alias_type='former_name'` (skip if colliding).
  4. `DELETE FROM entities WHERE vault_id=? AND slug=from`.
  5. `recompute_mentions(vault_id)` (reuse 005-05).
  - Return `MergeReport`. Caller pre-validates existence + `from != into`.

## Test Cases
### Unit Tests (`tests/test_sqlite_repository.py`)
1. **TC-UNIT-01:** refs of `from` re-pointed to `into`; `refs_repointed` counts them.
2. **TC-UNIT-02:** a page with both a `from` ref and an `into` ref of the same `ref_type` → deduped to one, higher `trust_level` kept.
3. **TC-UNIT-03:** `from`'s aliases moved to `into`; `from_slug` + `from`-name registered as `former_name` aliases of `into`.
4. **TC-UNIT-04:** a `from` alias that already maps to a third entity → recorded in `aliases_skipped`, merge still completes.
5. **TC-UNIT-05:** `entities` row for `from` deleted; `into.mentions_count` == de-duplicated union count.
### Regression
- `pytest tests/` green; FK/CASCADE behavior unaffected for unrelated rows.

## Acceptance Criteria
- [ ] All five effects happen atomically in one transaction.
- [ ] PK-dedup keeps higher trust; alias collisions reported not silently dropped.
- [ ] `from` row removed; `into.mentions_count` = union; `MergeReport` accurate.
- [ ] `mypy --strict` clean; regression green.

## Notes
Phase-1: stub returns empty `MergeReport` + RED tests; Phase-2: logic. Depends on 005-04 (resolve), 005-05 (recompute_mentions), 005-06 (alias write). The durable redirect is the registered `former_name` aliases (C-7); reindex canonicalization (005-03/AM-3) keeps it durable across rebuilds.
