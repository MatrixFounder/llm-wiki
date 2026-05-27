# Task 003-07a: DAL extension — `upsert_entity` write-path method

## Meta

- **Bead ID**: `task-003-07a-dal-upsert-entity`
- **Slug**: `dal-upsert-entity`
- **Maps to**: Issue **I-7.7a**; RTM row **R-37**.
- **Depends on**: task-003-00 (no other; clean DAL extension can run in parallel with 003-01 and 003-02).
- **Estimated time**: 0.75 day
- **Priority**: Critical (blocks 003-07b call site)

## Use Case Connection

- **UC-08 step 8 (DAL half)**: "After concept page written, `repo.upsert_entity(...)` called with `is_candidate=1`."
- **UC-08 alternative A1**: existing confirmed entity (`is_candidate=0`) → no downgrade (SQL-level `MIN()` guard).

## Task Goal

Extend the data-access layer with a new write-path method. Phase 3a shipped only `resolve_entity` (read-path stub) — this bead adds the write-path counterpart.

1. Add abstract method `upsert_entity(...)` to `IndexRepository` ABC (`scripts/wiki_index/repository.py`).
2. Implement in `SQLiteRepository` (`scripts/wiki_index/sqlite_repository.py`):
   - Atomic `INSERT … ON CONFLICT(vault_id, slug) DO UPDATE SET …` SQL.
   - **SQL-level downgrade guard**: `is_candidate = MIN(excluded.is_candidate, entities.is_candidate)` — once an entity is confirmed (`is_candidate=0`), it stays confirmed regardless of incoming value.
3. Add unit tests in `tests/test_sqlite_repository.py`.

## Stub-First Plan

**Phase 1 — Red tests on stub**:

1. Add to `IndexRepository` ABC:
   ```python
   @abstractmethod
   def upsert_entity(
       self,
       vault_id: str,
       slug: str,
       name: str,
       type: str,
       is_candidate: int,
       canonicalized_by: str,
       first_seen: str,
       last_updated: str,
   ) -> None:
       """Insert or update an entity row.

       Downgrade guard: if existing row has is_candidate=0 (confirmed),
       incoming is_candidate=1 does NOT overwrite. Enforced at SQL level
       via MIN(excluded.is_candidate, entities.is_candidate).
       """
       ...
   ```
2. Add stub to `SQLiteRepository`:
   ```python
   def upsert_entity(self, vault_id, slug, name, type, is_candidate,
                     canonicalized_by, first_seen, last_updated) -> None:
       raise NotImplementedError("task-003-07a phase 1 stub")
   ```
3. Add `tests/test_sqlite_repository.py` tests:
   - `test_upsert_entity_not_implemented` (Phase 1): asserts `NotImplementedError`.
   - `test_upsert_entity_inserts_new_row` (Phase 2): seeds nothing; calls upsert with `is_candidate=1`; assert row exists with `is_candidate=1`.
   - `test_upsert_entity_updates_existing_row` (Phase 2): seed row with `is_candidate=1`; call upsert with new `name`, `last_updated`; assert updated.
   - `test_upsert_entity_no_downgrade_from_confirmed` (Phase 2): seed row with `is_candidate=0`; call upsert with `is_candidate=1`; assert post-condition `is_candidate=0` (the SQL guard preserved it).
   - `test_upsert_entity_multi_vault_isolation` (Phase 2): upsert same slug into vault "A" and vault "B"; assert two distinct rows; verify by `SELECT count(*) FROM entities WHERE slug=?` → 2.
4. Run pytest — Red on Phase 1 (5 tests, 1 fails NotImplementedError + 4 skip).

**Phase 2 — Logic**:

1. Implement `upsert_entity` in `SQLiteRepository`:
   ```python
   def upsert_entity(
       self,
       vault_id: str,
       slug: str,
       name: str,
       type: str,
       is_candidate: int,
       canonicalized_by: str,
       first_seen: str,
       last_updated: str,
   ) -> None:
       sql = """
           INSERT INTO entities
               (vault_id, slug, name, type, is_candidate, canonicalized_by,
                first_seen, last_updated)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(vault_id, slug) DO UPDATE SET
               name = excluded.name,
               type = excluded.type,
               is_candidate = MIN(excluded.is_candidate, entities.is_candidate),
               canonicalized_by = excluded.canonicalized_by,
               last_updated = excluded.last_updated
       """
       with self._conn:  # autocommit via context manager
           self._conn.execute(sql, (
               vault_id, slug, name, type, is_candidate,
               canonicalized_by, first_seen, last_updated,
           ))
   ```
2. Unskip Phase-2 tests; run pytest — Green.

## Changes Description

### New Files

- None.

### Changes in Existing Files

#### File: `scripts/wiki_index/repository.py`

- Add `upsert_entity(...)` abstract method to the `IndexRepository` ABC (with full type annotations + docstring explaining the downgrade guard).

#### File: `scripts/wiki_index/sqlite_repository.py`

- Add `upsert_entity(...)` concrete implementation with the SQL above.

#### File: `tests/test_sqlite_repository.py`

- Add 5 new tests (1 Phase-1 + 4 Phase-2).

### Component Integration

- Consumed by 003-07b (`upsert_extracted_entity` call site in `wiki_extract_concepts.py`).
- The signature is the contract — both ABC and SQLiteRepository must match exactly. Future repositories (e.g., a future PostgresRepository) must implement the same signature with equivalent downgrade-guard semantics.

## Files Touched (explicit list)

- `scripts/wiki_index/repository.py` (modified — add ABC method)
- `scripts/wiki_index/sqlite_repository.py` (modified — add concrete impl)
- `tests/test_sqlite_repository.py` (modified — add 5 tests)

## Test Surface

- **New**: 5 unit tests:
  - `test_upsert_entity_not_implemented` (Phase 1, deletes after Phase 2 lands)
  - `test_upsert_entity_inserts_new_row`
  - `test_upsert_entity_updates_existing_row`
  - `test_upsert_entity_no_downgrade_from_confirmed` (CRITICAL — the SQL-guard regression test)
  - `test_upsert_entity_multi_vault_isolation`

## Acceptance Criteria

- [ ] **R-37(a)**: `repo.upsert_entity(...)` callable from skill layer with `is_candidate=1` default.
- [ ] **R-37(b)**: existing `is_candidate=0` entity → NO downgrade when called with `is_candidate=1` (SQL-level guard via `MIN()`).
- [ ] **R-37(c)**: `canonicalized_by` field set by caller — written as-is.
- [ ] **R-37(d)**: `first_seen` and `last_updated` written as-is.
- [ ] ABC + concrete signatures match (verified via `inspect.signature` parity test if desired — optional).
- [ ] Multi-vault isolation: same slug in two vaults → two rows (verified by `test_upsert_entity_multi_vault_isolation`).
- [ ] All 5 unit tests pass.
- [ ] `mypy --strict scripts/wiki_index/` clean.
- [ ] Full sweep `pytest tests/ -q` still green.

## Verification

```bash
pytest tests/test_sqlite_repository.py -v -k "upsert_entity"
pytest tests/ -q
mypy --strict scripts/wiki_index/
```

## Rollback

Revert both `repository.py` and `sqlite_repository.py`; remove the 5 new tests. 003-07b will fail until restored.

## Notes

- **SQL guard rationale**: putting the downgrade check at the SQL level (not just in Python) means even a misconfigured caller cannot demote a confirmed entity. R-3 only writes candidates; R-4 (future) will write confirmed (`is_candidate=0`). The guard ensures the future flow can't accidentally regress on a re-run of R-3.
- The `ON CONFLICT(vault_id, slug)` clause assumes the existing `entities` table has a `UNIQUE(vault_id, slug)` constraint. Verify by reading `docs/SCHEMA-v2.sql` (Phase 3a shipped this).
- `with self._conn:` provides autocommit; on exception the transaction is rolled back. This matches the pattern used by other `SQLiteRepository` write methods (e.g., `upsert_page`, `replace_refs`).
- The downgrade-guard test (`test_upsert_entity_no_downgrade_from_confirmed`) is the most important assertion in this bead. Reviewers should specifically scan for it.
