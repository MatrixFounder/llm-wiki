# Task 001-15: `SQLiteRepository` vaults CRUD impl + CASCADE on rename [LOGIC IMPLEMENTATION]

## Use Case Connection
- UC-01 (init registers vault row)
- All UCs (every query is partitioned by vault_id)

## Task Goal
Implement `register_vault`, `get_vault`, `list_vaults`, `rename_vault` on `SQLiteRepository`. Establishes connection management (lazy connect on first method call), pragmas (WAL, foreign_keys=ON), and the row factory pattern used by all subsequent methods.

## Changes Description

### New Files
None.

### Changes in Existing Files

#### File: `scripts/wiki_index/sqlite_repository.py`

**Class `SQLiteRepository`:**

- Add `_conn: sqlite3.Connection | None = None` instance attribute (lazy).
- Add `def _connect(self) -> sqlite3.Connection:` — lazy-opens connection, applies pragmas:
  - `PRAGMA journal_mode = WAL;`
  - `PRAGMA synchronous = NORMAL;`
  - `PRAGMA foreign_keys = ON;`
  - `PRAGMA temp_store = MEMORY;`
  - `PRAGMA mmap_size = 268435456;`
  - Returns cached `self._conn` on subsequent calls.
- Add `def close(self) -> None:` — closes connection if open.
- Add `def __enter__(self) / __exit__(self, ...)` — context manager support.

**Implement abstract methods:**

- `register_vault(self, vault: Vault) -> None`:
  - `INSERT INTO vaults (vault_id, name, root_path, schema_version, registered_at, config_json, notes) VALUES (?, ?, ?, ?, ?, ?, ?)` with `vault.config_json` serialized via `json.dumps`.
  - On `IntegrityError` (vault_id PK collision OR root_path UNIQUE) → re-raise as `VaultRegistrationError` with details.

- `get_vault(self, vault_id: str) -> Vault | None`:
  - `SELECT vault_id, name, root_path, schema_version, registered_at, config_json, notes FROM vaults WHERE vault_id = ?`.
  - Deserialize `config_json` via `json.loads` (handle NULL → None).
  - Return `Vault(...)` or `None`.

- `list_vaults(self) -> list[Vault]`:
  - `SELECT ... FROM vaults WHERE vault_id != '_global_' ORDER BY vault_id`.
  - The `'_global_'` sentinel (M-7) excluded from normal listings.

- `rename_vault(self, old_vault_id: str, new_vault_id: str) -> None`:
  - `UPDATE vaults SET vault_id = ? WHERE vault_id = ?` — schema-level `ON UPDATE CASCADE` propagates to pages/entities/etc.
  - Wrap in `BEGIN IMMEDIATE`.
  - Raise if `old_vault_id` does not exist.

- Add `VaultRegistrationError(RuntimeError)` exception class.

### Component Integration
- The `_connect` pattern becomes the foundation for every subsequent method (16, 17, 18, 19).
- E2E harness (task-001-11) updated: `register_vault(...)` no longer raises `NotImplementedError` — instead asserts the row is in DB.

## Test Cases

### End-to-end Tests
1. **TC-E2E-01**: Register a vault, then `get_vault(vault_id)` returns the same row.
2. **TC-E2E-02**: `list_vaults()` excludes `'_global_'` sentinel.
3. **TC-E2E-03**: Rename vault: insert pages with old vault_id → rename → pages now have new vault_id (CASCADE).

### Unit Tests
1. **TC-UNIT-01**: Duplicate `vault_id` insert → `VaultRegistrationError`.
2. **TC-UNIT-02**: Duplicate `root_path` insert → `VaultRegistrationError`.
3. **TC-UNIT-03**: `_connect` is idempotent (same connection returned).
4. **TC-UNIT-04**: WAL mode active: `PRAGMA journal_mode` returns `wal`.
5. **TC-UNIT-05**: Foreign keys ON: orphan FK insert fails.

### Regression Tests
- All Stage 1 tests still pass.
- E2E harness reflects new behavior.

## Acceptance Criteria
- [ ] All four methods implemented per spec.
- [ ] `mypy --strict` passes.
- [ ] All TC tests pass.
- [ ] Pragmas verified at connection open.
- [ ] M-1 (vault_id CHECK) tested via integration (insert malformed `vault_id` → `IntegrityError`).

## Notes
- Connection is per-`SQLiteRepository` instance; multi-instance use is fine because SQLite WAL allows multi-reader + single-writer with `BEGIN IMMEDIATE`.
- `'_global_'` sentinel (M-7): used by `batch_runs` for cross-vault operations (reindex --all-vaults). Excluded from `list_vaults()` to avoid leaking implementation detail.
- ADR-002 §D1.1 `vault_id` format CHECK is enforced at INSERT — Python doesn't need to re-validate (defence in depth: schema is source of truth).
