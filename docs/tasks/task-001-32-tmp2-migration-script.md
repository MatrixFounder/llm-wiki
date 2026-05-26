# Task 001-32: `tmp2/` migration script — flat → `_sources/<file>.md` [LOGIC IMPLEMENTATION]

## Use Case Connection
- UC-05 (existing 16-file corpus migration)
- R-13

## Task Goal
Provide `scripts/wiki_migrate_flat_to_folders.py` that converts legacy `tmp2/<filename>.md` to `tmp2/_sources/<filename>.md` (idempotent, `--dry-run` flag). After migration, operator runs `wiki-init --register-existing` then `wiki-reindex --full` to populate DB.

## Changes Description

### New Files
- `scripts/wiki_migrate_flat_to_folders.py`:
  - Argparse: `vault_path` (positional), `--dry-run`, `--target-subdir` (default `_sources`).
  - Walks `vault_path/*.md` (top-level only); for each file:
    - Validate path inside `vault_path` (task-001-12).
    - Compute target: `vault_path / target_subdir / <filename>`.
    - If target already exists AND file_hashes match → no-op (idempotent).
    - If target exists AND hashes differ → log warning, skip (operator-resolve).
    - Else: move (or copy in dry-run) and log.
  - Skip system files: `WIKI_SCHEMA.md`, `CLAUDE.md`, `log.md`, `index.md`.
  - Skip directories (already in subfolder).
  - Emit summary JSON: `{"moved": N, "skipped": K, "errors": [...]}`.
- `tests/test_migration_script.py`.

### Changes in Existing Files
None.

### Component Integration
- Standalone script — does NOT touch DB. Composes with task-001-30 reindex for end-to-end migration.

## Test Cases

### End-to-end Tests
1. **TC-E2E-01**: On synthetic `tmp2/` with 16 .md files → all moved into `tmp2/_sources/`. Re-run → no-op.
2. **TC-E2E-02**: `--dry-run` → reports what would happen but no FS changes.
3. **TC-E2E-03**: System files (`WIKI_SCHEMA.md`) skipped.

### Unit Tests
1. **TC-UNIT-01**: Idempotent: re-run on already-migrated vault → 0 moves.
2. **TC-UNIT-02**: Hash mismatch case → warning, no overwrite.
3. **TC-UNIT-03**: Path-traversal validation applies.

### Regression Tests
- N/A (standalone script).

## Acceptance Criteria
- [ ] Idempotent migration.
- [ ] `--dry-run` works.
- [ ] System files preserved.
- [ ] After migration, `wiki-reindex --full` produces 16 pages in DB (verified in task-001-33 e2e benchmark).

## Notes
- The legacy `tmp2/` layout had files at the top level; v2 wants them under `_sources/` per ADR-002 promotion-spec.
- Migration is one-shot; after this, all ingestion uses the new layout.
