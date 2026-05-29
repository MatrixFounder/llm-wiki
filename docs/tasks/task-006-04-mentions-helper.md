# Task 006-04: dedup the mentions_count UPDATE into one helper (F12c)

## Ledger id: F12c

## Goal
The correlated `UPDATE entities SET mentions_count = (SELECT COUNT(*) FROM
page_entity_refs …)` is hand-copied at 4 sites; a future index change could
silently desync them. Extract one private helper.

## Changes
### `scripts/wiki_index/sqlite_repository.py`
- Add `def _recompute_mentions(self, conn, vault_id, slug=None) -> None` issuing
  the correlated UPDATE on the caller's connection (optional `slug` to scope to
  one entity, as `merge_entities` does). Does NOT manage its own tx (caller owns it).
- Replace the inline UPDATE in `recompute_mentions` (full vault), `auto_promote_candidates`
  (inside its BEGIN), and `merge_entities` (slug-scoped, inside its BEGIN) with calls.
### `scripts/wiki_index/reindex.py`
- Step 3 calls `repo._recompute_mentions(conn, vault_id)` (or inline the same SQL via the helper) — keep behavior identical.

## Test cases
- Pure refactor: existing tests are the guard — `test_entity_resolution_dal.py`
  (recompute, auto_promote, merge mentions=union), `test_reindex_*`, durability
  suite must stay green. Add one direct unit test of `_recompute_mentions(slug=…)`
  scoping to a single entity.

## Acceptance
- [ ] One helper; all 4 sites call it; SQL byte-identical semantics.
- [ ] `pytest tests/` green (no behavior change); `mypy --strict` clean.

## Notes
Independent bead. Maintainability only — zero behavior change is the bar.
