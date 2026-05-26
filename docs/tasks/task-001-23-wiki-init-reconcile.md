# Task 001-23: `wiki-init --reconcile` flow [LOGIC IMPLEMENTATION]

## Use Case Connection
- UC-01 (handle VAULT_RENAMED case per ADR-002 §D8)

## Task Goal
Implement reconciliation when `WIKI_SCHEMA.md::vault_id` differs from the registered `vaults` row for the same `root_path`. Operator confirms (or rejects) the rename; on confirmation, calls `repo.rename_vault(old, new)` triggering schema CASCADE.

## Changes Description

### New Files
None.

### Changes in Existing Files

#### File: `scripts/wiki_skills/wiki_init.py`

**Function `reconcile(args) -> int`:**
- Resolve `vault_root`; parse `WIKI_SCHEMA.md::vault_id` as `new_vault_id`.
- Open repo; lookup existing row by `root_path` (helper `repo.get_vault_by_root_path(root_path)` — needs to be added to interface).
- If no row exists → exit 6 with `{"error": "VAULT_NOT_REGISTERED", "hint": "Run --register-existing first"}`.
- If `existing.vault_id == new_vault_id` → no-op, exit 0 with `{"action": "no-change"}`.
- Else (rename detected):
  - If `args.confirm` not set → print diff and exit 7 with `{"warning": "VAULT_RENAMED", "old_vault_id": ..., "new_vault_id": ..., "hint": "Re-run with --confirm to apply"}`.
  - Else: call `repo.rename_vault(old_vault_id, new_vault_id)`; emit `LogEvent(event_type='reclassify', subject=f'vault rename {old}→{new}', ...)`; exit 0 with `{"action": "renamed", "old_vault_id": ..., "new_vault_id": ...}`.

#### File: `scripts/wiki_index/repository.py`
- Add abstract method `def get_vault_by_root_path(self, root_path: Path) -> Vault | None: ...`.

#### File: `scripts/wiki_index/sqlite_repository.py`
- Implement: `SELECT ... FROM vaults WHERE root_path = ?` — relies on `root_path UNIQUE` index.

### Component Integration
- Hooked into `wiki-init` dispatcher; only run when explicitly invoked.
- Reclassify event emitted to log_events (R-28 event_type already in CHECK enum).

## Test Cases

### End-to-end Tests
1. **TC-E2E-01**: Rename: vault registered as `old-id`; WIKI_SCHEMA edited to `new-id`; reconcile without `--confirm` → exit 7, no DB mutation. With `--confirm` → exit 0, all pages now have `vault_id='new-id'` (CASCADE).

### Unit Tests
1. **TC-UNIT-01**: Reconcile on unregistered vault → `VAULT_NOT_REGISTERED`.
2. **TC-UNIT-02**: Reconcile with matching IDs → `no-change`.
3. **TC-UNIT-03**: Reclassify log_event written on confirmation.
4. **TC-UNIT-04**: CASCADE: after rename, `SELECT count(*) FROM pages WHERE vault_id=old` = 0 and `=new` > 0.

### Regression Tests
- task-001-22 register-existing still works.

## Acceptance Criteria
- [ ] All four UC-01 scenarios per ADR-002 §D1.1 + §D8 handled.
- [ ] `--confirm` gate prevents accidental rename.
- [ ] CASCADE works (schema-level, not Python).
- [ ] All TC tests pass.

## Notes
- The `--confirm` UX intentionally requires two passes — destructive rename should never be implicit.
- `event_type='reclassify'` is part of the CHECK enum in SCHEMA-v2.sql line ~80 — verify it's there (it is, per ADR-002 §D2).
