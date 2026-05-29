# Task 008-04: verify-state DAL — `check_verify_state` / `record_verify_state`

## Use Case Connection
- UC-24: Idempotent re-verify (`is_unchanged` short-circuit).

## Task Goal
Add two thin `IndexRepository` methods that read/write per-verification idempotency state in the **generic `source_state` table** (`source_kind='verification'`), so `wiki-verify-multi prepare` can short-circuit an unchanged re-verify and `apply` can record the verified state. No new table, no DDL. Skills call these methods — **never raw SQL via `repo._connect()`** (NFR-2). Modelled exactly on TASK 007's `check_query_state`/`record_query_state`.

## Changes Description

### Changes in Existing Files

#### File: `scripts/wiki_index/repository.py` (ABC)
- Add abstractmethod `check_verify_state(self, vault_id: str, verification_slug: str) -> str | None`
  - Returns the recorded `verify_hash` for `(vault_id, source_kind='verification', scope=verification_slug, key='verify_hash')`, or `None` if absent.
- Add abstractmethod `record_verify_state(self, vault_id: str, verification_slug: str, verify_hash: str) -> None`
  - UPSERTs the row (`INSERT … ON CONFLICT(vault_id, source_kind, scope, key) DO UPDATE SET value=…, updated_at=…`).

#### File: `scripts/wiki_index/sqlite_repository.py`
- Implement both. Parameterized statements only. `scope = verification_slug`, `key = "verify_hash"`, `source_kind = "verification"`, `value = verify_hash`, `updated_at = datetime.now(timezone.utc).isoformat()`. Defensive NULL guard in `check_verify_state` (corrupt `value=NULL` → treat as absent), mirroring `check_query_state` (L-V3.2).

### Component Integration
`prepare` (008-05) calls `check_verify_state` to set `is_unchanged`; `apply` (008-07) calls `record_verify_state` at the end of a successful file-write + index. The `value` (verify_hash) semantics — `sha256(answer_hash ‖ ordered examined project/slug set)` (Q-008-b) — are computed by the skill (008-05), not the DAL; the DAL just stores the string. Coexists with `source_kind='query'` (TASK 007) and `'extract-concepts'` (TASK 003) in the same table — different `source_kind`, no interaction.

## Test Cases

### Unit Tests
1. **TC-UNIT-01:** `record_verify_state(v, "vq1", "abc")` then `check_verify_state(v, "vq1") == "abc"`.
2. **TC-UNIT-02:** `check_verify_state(v, "missing") is None`.
3. **TC-UNIT-03:** second `record_verify_state(v, "vq1", "def")` updates (UPSERT) → `== "def"` (one row, not two).
4. **TC-UNIT-04:** multi-vault isolation — `record_verify_state(v1, "vq1", "x")` does not affect `check_verify_state(v2, "vq1")` (→ `None`).
5. **TC-UNIT-05 (defensive):** a hand-inserted `value=NULL` row → `check_verify_state` returns `None` (not a crash).
6. **TC-UNIT-06 (source_kind isolation):** a `source_kind='query'` row with the same `scope` does not satisfy `check_verify_state` (→ `None`).

### Regression Tests
- `SQLiteRepository` remains instantiable (both abstractmethods implemented in the same bead — green-throughout); existing `source_state` usage by `wiki-query` (`source_kind='query'`) + `wiki-extract-concepts` (`'extract-concepts'`) is unaffected.

## Acceptance Criteria
- [ ] Both ABC abstractmethods + `SQLiteRepository` impls land together (class always instantiable).
- [ ] Round-trip + update + multi-vault isolation + NULL guard + source_kind-isolation tests green.
- [ ] No raw `source_state` SQL in any skill (the methods are the only access path).
- [ ] `mypy --strict scripts/` clean.

## Notes
Stub-First: Phase-1 abstractmethod + `SQLiteRepository` stub (`return None` / `pass`) + RED tests; Phase-2 the parameterized SELECT / UPSERT. Independent of 008-01/02/03 (the `source_state` table already exists) — parallel-safe at start. A near-verbatim copy of TASK 007's 007-03 with `query`→`verification`.
