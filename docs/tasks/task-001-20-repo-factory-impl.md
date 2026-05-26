# Task 001-20: Factory `make_repo(config)` real impl + iCloud-rejection enforcement [LOGIC IMPLEMENTATION]

## Use Case Connection
- UC-01 (init)
- All UCs

## Task Goal
Replace `make_repo` stub with the real impl: validates DB path is not in iCloud (`validate_db_path` from task-001-14), resolves platform default path (or `config.db_path` override), opens `SQLiteRepository` against it, and returns. Also enforces `vault_id` presence + format at runtime per ADR-002 §D1.1.

## Changes Description

### New Files
None.

### Changes in Existing Files

#### File: `scripts/wiki_index/factory.py`

**Function `make_repo(config: dict) -> IndexRepository`:**
- Extract `vault_id = config.get('vault_id')`; if None or doesn't match pattern → raise `ConfigValidationError('vault_id REQUIRED')` (matches ADR-002 §D1.1).
- Determine DB path:
  - If `config.get('db_path')` provided → use it.
  - Else → `_resolve_db_path(vault_id, sys.platform)`.
- Call `validate_db_path(db_path)` — raises `ICloudRejectionError` if inside iCloud.
- Ensure parent dir exists.
- If DB file does not exist → apply `sql/wiki-index-v2.sql` (open conn, `executescript`, close).
- Return `SQLiteRepository(db_path)`.

**Function `apply_schema_if_missing(db_path: Path) -> None`:**
- If `db_path.exists()` AND `db_path.stat().st_size > 0` → no-op.
- Else: read `sql/wiki-index-v2.sql` (use `importlib.resources` or relative path), open SQLite connection, `conn.executescript(schema_sql)`, commit, close.

### Component Integration
- This is the gate between config and repo — every skill goes through here.
- iCloud-rejection enforcement is mandatory at this layer (defense in depth alongside the `--db-path` validation in `wiki-init`).

## Test Cases

### End-to-end Tests
1. **TC-E2E-01**: First call on a fresh DB path applies schema; subsequent calls don't re-apply.
2. **TC-E2E-02**: Config with iCloud `db_path` → `ICloudRejectionError`.
3. **TC-E2E-03**: Config without `vault_id` → `ConfigValidationError`.
4. **TC-E2E-04**: Valid config returns usable `SQLiteRepository`; `repo.list_vaults()` works.

### Unit Tests
1. **TC-UNIT-01**: `apply_schema_if_missing` idempotent (run twice, schema unchanged).
2. **TC-UNIT-02**: Invalid `vault_id` format (e.g., `1bad`) → `ConfigValidationError` BEFORE any DB I/O.

### Regression Tests
- task-001-05 stub tests adjusted to reflect new behavior.
- E2E harness asserts that factory returns repo capable of `register_vault` (round-trip).

## Acceptance Criteria
- [ ] All functions per spec.
- [ ] Schema-apply is idempotent.
- [ ] iCloud-rejection enforced.
- [ ] `vault_id` validation enforced at factory level (matches schema CHECK).
- [ ] All TC tests pass.

## Notes
- The `vault_id` presence/format check here is the SECOND line of defense (first is config schema validation in task-001-13; third is the SQLite CHECK constraint). Defense in depth per ADR-002 §D1.1.
- `apply_schema_if_missing` uses `executescript` which auto-commits — wrap in try/except to clean up on failure.
- The `--db-path` override path (UC-01 A3) is plumbed through `config['db_path']`.
