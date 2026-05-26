# Task 001-04: `SQLiteRepository` stub — all methods raise `NotImplementedError` [STUB CREATION]

## Use Case Connection
- All UCs (concrete backend stub for DAL)

## Task Goal
Provide a concrete `SQLiteRepository(IndexRepository)` whose every method raises `NotImplementedError`. The class can be instantiated (passes Python ABC check) so factory + downstream code can be wired without yet implementing SQL. Logic arrives in task-001-15 through task-001-19.

## Changes Description

### New Files
- `scripts/wiki_index/sqlite_repository.py`:
  - `class SQLiteRepository(IndexRepository):`
    - `def __init__(self, db_path: Path) -> None:` — stores `self.db_path = db_path`; does NOT yet open a connection in stub.
    - Every abstract method body: `raise NotImplementedError(f'{self.__class__.__name__}.<method> stub — see task-001-NN')` where NN matches the task that implements it.
- `tests/test_sqlite_repository_stub.py` — asserts instantiation works and every method raises `NotImplementedError`.

### Changes in Existing Files
None.

### Component Integration
- This stub is the concrete return value of `make_repo(config)` factory (task-001-05).
- Downstream skills (`wiki-init`, etc.) receive this instance and call methods; in Stage 1 they hit `NotImplementedError` — the E2E harness asserts this controlled-failure state.

## Test Cases

### End-to-end Tests
1. **TC-E2E-01**: Instantiate stub repo with a path.
   - Input Data: `SQLiteRepository(Path('/tmp/test.db'))`.
   - Expected Result: object created; `repo.db_path == Path('/tmp/test.db')`; no DB file opened yet.

### Unit Tests
1. **TC-UNIT-01**: Every abstract method raises `NotImplementedError`.
   - Tested entity: each of `register_vault`, `get_vault`, `list_vaults`, `upsert_page`, `get_page`, `delete_page`, `search_pages`, `upsert_refs`, `replace_refs`, `get_backlinks`, `find_orphan_links`, `find_pages_missing_in_index`, `check_drift`, `find_cross_vault_concept_duplicates`, `append_log_event`, `query_log_events`, `begin_batch_run`, `finish_batch_run`, `last_batch_run`, `rename_vault`.
   - Expected Result: each raises `NotImplementedError` with a message that includes the implementing task ID.

### Regression Tests
- task-001-03 smoke tests still pass.

## Acceptance Criteria
- [ ] `SQLiteRepository` instantiates without opening a DB.
- [ ] Every inherited abstract method raises `NotImplementedError`.
- [ ] `mypy --strict scripts/wiki_index/sqlite_repository.py` passes.
- [ ] `tests/test_sqlite_repository_stub.py` passes.

## Notes
- Connection management deferred to task-001-15 (vaults CRUD impl) — first method to need an actual SQLite handle.
- DO NOT add convenience methods not in the abstract base — keep the surface flat.
