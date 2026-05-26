# Task 001-22: `wiki-init --register-existing` flow [LOGIC IMPLEMENTATION]

## Use Case Connection
- UC-01 (register existing vault, e.g., `trade-agents/`)

## Task Goal
Implement `--register-existing --vault <path>` mode: walk up to find vault root, parse existing `WIKI_SCHEMA.md`, fail-fast on missing/invalid `vault_id` (per ADR-002 §D1.1), and register vault row. If schema-spec promotion-spec two-tier layout detected (per [PLAN.md §1 prereq](../PLAN.md)) — note in registration but defer per-tier indexing to `wiki-reindex --full`.

## Changes Description

### New Files
None.

### Changes in Existing Files

#### File: `scripts/wiki_skills/wiki_init.py`

**Function `register_existing(args) -> int`:**
- Resolve `vault_root = Path(args.vault).resolve(strict=True)`.
- `assert_no_symlink_escape(vault_root)` (task-001-12).
- Check `<vault>/WIKI_SCHEMA.md` exists; else exit 6 with `{"error": "MISSING_WIKI_SCHEMA", "expected_path": "<vault>/WIKI_SCHEMA.md", "hint": "Run wiki-ingest init"}`.
- Parse frontmatter via `python-frontmatter`.
- Extract `vault_id`; if missing → exit 6 with:
  ```json
  {"error": "MISSING_VAULT_ID",
   "suggested_vault_id": "<slug-from-folder-basename>",
   "hint": "Add vault_id: <slug> to WIKI_SCHEMA.md frontmatter"}
  ```
- Validate format; if invalid → exit 6 with `{"error": "INVALID_VAULT_ID", "received": <value>, "pattern": "^[a-z][a-z0-9-]{1,30}[a-z0-9]$"}`.
- Detect two-tier layout: walk `vault_root/Lessons/*/WIKI_SCHEMA.md`. If any course-local WIKI_SCHEMA.md exists → set `is_two_tier=True` in `vault.config_json`.
- Open repo via `make_repo({'vault_id': vault_id, ...})`.
- Check existing vault row:
  - If `repo.get_vault(vault_id) is None` → call `repo.register_vault(...)`.
  - If exists AND `root_path` matches → re-use (idempotent).
  - If exists AND `root_path` differs → exit 6 with `{"error": "VAULT_ID_COLLISION", "existing_root_path": ..., "new_root_path": ...}`.
- Print JSON: `{"action": "registered" | "already-registered", "vault_id": ..., "is_two_tier": bool, "db_path": ...}`.
- Return 0.

### Component Integration
- Used by `trade-agents/` operator: `wiki-init --register-existing --vault /Users/sergey/.../trade-agents`.
- After this returns, operator typically follows with `wiki-reindex --full --vault trade-agents` (task-001-30).

## Test Cases

### End-to-end Tests
1. **TC-E2E-01**: Register `multi_vault` fixture's `vault-alpha`:
   - Args: `wiki-init --register-existing --vault tests/fixtures/multi-vault/vault-alpha`.
   - Expected: exit 0; `{"action": "registered", "vault_id": "vault-alpha"}`; `repo.get_vault('vault-alpha')` returns row.
2. **TC-E2E-02**: Register vault without `vault_id` in WIKI_SCHEMA.md → exit 6, `MISSING_VAULT_ID` error, `suggested_vault_id` matches folder basename.
3. **TC-E2E-03**: Re-register same vault → `"already-registered"`, idempotent.

### Unit Tests
1. **TC-UNIT-01**: Missing WIKI_SCHEMA.md → `MISSING_WIKI_SCHEMA`.
2. **TC-UNIT-02**: Invalid `vault_id` format → `INVALID_VAULT_ID`.
3. **TC-UNIT-03**: Different root_path with same vault_id → `VAULT_ID_COLLISION`.
4. **TC-UNIT-04**: Two-tier detection: fixture with `vault-alpha/Lessons/X/WIKI_SCHEMA.md` → `is_two_tier=True`.

### Regression Tests
- task-001-21 scaffold-new still works.

## Acceptance Criteria
- [ ] All ADR-002 §D1.1 fail-fast scenarios handled (MISSING_WIKI_SCHEMA, MISSING_VAULT_ID, INVALID_VAULT_ID, VAULT_ID_COLLISION).
- [ ] Two-tier layout detected and stored in `config_json`.
- [ ] Idempotent: re-register no-op.
- [ ] All TC tests pass.

## Notes
- Exit code 6 is reserved for `wiki-init` config errors (avoids confusion with argparse exit 2 and generic 1).
- The `suggested_vault_id` is derived as `kebab(folder_basename)` per ADR-002 §D1.1 — operator-friendly UX, not auto-applied.
- `assert_no_symlink_escape` defends against malicious symlinked vault roots.
