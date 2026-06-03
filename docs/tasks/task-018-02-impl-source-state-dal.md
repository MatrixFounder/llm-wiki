# task-018-02 — [LOGIC] implement `get/set_source_state` + zero-DDL

**Parent:** TASK 018. **Depends on:** 018-01. **RTM:** E3.4d, Q-018-8, AC-8. **Method:** `skill-tdd-strict` (idempotency correctness — RED-first).

## Goal
Implement the two generic `source_state` accessors; prove zero-DDL.

## Steps
1. `set_source_state` → parameterized `INSERT INTO source_state(vault_id, source_kind, scope,
   key, value, updated_at) VALUES (?,?,?,?,?,?) ON CONFLICT(vault_id, source_kind, scope, key)
   DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at` (ISO-8601 `updated_at`).
2. `get_source_state` → `SELECT value FROM source_state WHERE vault_id=? AND source_kind=? AND
   scope=? AND key=?` → `str | None`. No raw SQL outside the DAL; params only.
3. GREEN `test_source_state_roundtrip`; add `test_source_state_zero_ddl` — after a `set` with
   `source_kind='sync'`, `PRAGMA user_version` is still **5** and the row reads back (no CHECK
   rejection); `test_source_state_overwrite` (second `set` updates in place).

## Verification
- `pytest -q -k source_state` GREEN; `mypy --strict` clean; `sql/wiki-index-v2.sql` unchanged.
