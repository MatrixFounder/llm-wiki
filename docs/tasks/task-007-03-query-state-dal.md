# Task 007-03: query-state DAL — `check_query_state` / `record_query_state`

## Use Case Connection
- UC-17: Idempotent re-run (`is_unchanged` short-circuit).

## Task Goal
Add two thin `IndexRepository` methods that read/write per-query idempotency state in the **generic `source_state` table** (`source_kind='query'`), so `wiki-query prepare` can short-circuit an unchanged re-query and `apply` can record the answered state. No new table, no DDL. Skills call these methods — **never raw SQL via `repo._connect()`** (NFR-2; this is the cleaner path the H-PERF-3 lesson prescribes).

## Changes Description

### Changes in Existing Files

#### File: `scripts/wiki_index/repository.py` (ABC)
- Add abstractmethod `check_query_state(self, vault_id: str, query_slug: str) -> str | None`
  - Returns the recorded `question_hash` for `(vault_id, source_kind='query', scope=query_slug, key='question_hash')`, or `None` if absent.
- Add abstractmethod `record_query_state(self, vault_id: str, query_slug: str, question_hash: str) -> None`
  - UPSERTs the row (`INSERT … ON CONFLICT(vault_id, source_kind, scope, key) DO UPDATE SET value=…, updated_at=…`).

#### File: `scripts/wiki_index/sqlite_repository.py`
- Implement both. Parameterized statements only. `scope = query_slug`, `key = "question_hash"`, `source_kind = "query"`, `value = question_hash`, `updated_at = datetime.now(timezone.utc).isoformat()`. Defensive NULL guard in `check_query_state` (corrupt `value=NULL` → treat as absent), mirroring `check_idempotency` (L-V3.2).

### Component Integration
`prepare` (007-04) calls `check_query_state` to set `is_unchanged`; `apply` (007-06) calls `record_query_state` at the end of a successful file-write + index. The `value` (question_hash) semantics — `sha256(question ‖ ordered retrieved project/slug set)` — are computed by the skill (007-04), not the DAL; the DAL just stores the string.

## Test Cases

### Unit Tests
1. **TC-UNIT-01:** `record_query_state(v, "q1", "abc")` then `check_query_state(v, "q1") == "abc"`.
2. **TC-UNIT-02:** `check_query_state(v, "missing") is None`.
3. **TC-UNIT-03:** second `record_query_state(v, "q1", "def")` updates (UPSERT) → `check_query_state == "def"` (one row, not two).
4. **TC-UNIT-04:** multi-vault isolation — `record_query_state(v1, "q1", "x")` does not affect `check_query_state(v2, "q1")` (→ `None`).
5. **TC-UNIT-05 (defensive):** a hand-inserted `value=NULL` row → `check_query_state` returns `None` (not a crash).

### Regression Tests
- `SQLiteRepository` remains instantiable (both abstractmethods implemented in the same bead — green-throughout); existing `source_state` usage by `wiki-extract-concepts` (`source_kind='extract-concepts'`) is unaffected (different `source_kind`).

## Acceptance Criteria
- [ ] Both ABC abstractmethods + `SQLiteRepository` impls land together (class always instantiable).
- [ ] Round-trip + update + multi-vault isolation + NULL guard tests green.
- [ ] No raw `source_state` SQL in any skill (the methods are the only access path).
- [ ] `mypy --strict scripts/` clean.

## Notes
Stub-First: Phase-1 abstractmethod + `SQLiteRepository` stub (`return None` / `pass`) + RED tests; Phase-2 the parameterized SELECT / UPSERT. Independent of 007-01/02 (the `source_state` table already exists) — parallel-safe at start.
