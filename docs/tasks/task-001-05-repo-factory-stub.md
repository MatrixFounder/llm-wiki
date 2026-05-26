# Task 001-05: Factory `make_repo(config)` stub + iCloud-rejection placeholder [STUB CREATION]

## Use Case Connection
- UC-01 (init creates repo)
- All UCs (every skill calls `make_repo` to obtain repo handle)

## Task Goal
Provide a factory `make_repo(config: WikiConfig) -> IndexRepository` that currently returns a `SQLiteRepository` constructed with a hardcoded test path. Includes a stub `_is_icloud_path(p: Path) -> bool` that always returns `False` — real detection arrives in task-001-14. Establishes the factory call-site so downstream skill code compiles.

## Changes Description

### New Files
- `scripts/wiki_index/factory.py`:
  - `def make_repo(config: dict) -> IndexRepository:` — for stub, ignores `config` and returns `SQLiteRepository(Path('/tmp/wiki-stub.db'))`.
  - `def _is_icloud_path(p: Path) -> bool: return False  # STUB — task-001-14 implements regex`.
  - `def _resolve_db_path(vault_id: str, platform: str) -> Path:` — returns hardcoded `Path(f'/tmp/wiki-{vault_id}.db')` (stub).
  - `class ICloudRejectionError(RuntimeError): pass`
- `tests/test_factory_stub.py` — assert `make_repo({})` returns a `SQLiteRepository` instance with hardcoded path.

### Changes in Existing Files
None.

### Component Integration
- `make_repo` is the sole public entry to the DAL — skills MUST go through it (no direct `SQLiteRepository(...)` from skill code).
- The factory is the future enforcement point for the iCloud-rejection contract (R-03).

## Test Cases

### End-to-end Tests
1. **TC-E2E-01**: Factory returns a usable repo handle.
   - Input Data: `make_repo({'vault_id': 'test'})`.
   - Expected Result: returns `SQLiteRepository` instance; `isinstance(repo, IndexRepository)`.

### Unit Tests
1. **TC-UNIT-01**: `_is_icloud_path` stub always returns `False`.
   - Input Data: any `Path` (including one containing `Mobile Documents/iCloud~`).
   - Expected Result: `False` (stub behavior — real impl is task-001-14).
2. **TC-UNIT-02**: `_resolve_db_path` returns deterministic stub path.

### Regression Tests
- task-001-04 stub tests still pass.

## Acceptance Criteria
- [ ] `make_repo` returns `SQLiteRepository` instance.
- [ ] Stub functions documented with the implementing task ID.
- [ ] `tests/test_factory_stub.py` passes.

## Notes
- The factory will become the enforcement point for ADR-002 §D1.1 vault_id validation at runtime — wired in task-001-20.
- `ICloudRejectionError` class shape is final (no change in task-001-14); only `_is_icloud_path` body changes.
