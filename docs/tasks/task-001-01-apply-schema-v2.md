# Task 001-01: Apply SCHEMA-v2.sql as `sql/wiki-index-v2.sql` + smoke test [STUB CREATION]

## Use Case Connection
- UC-01: `wiki-init` (schema is consumed by init flow)
- Foundation for all other UCs (UC-02 / UC-03 / UC-04 / UC-05)

## Task Goal
Copy `docs/SCHEMA-v2.sql` into the implementation tree as `sql/wiki-index-v2.sql` and verify it applies cleanly to a fresh SQLite database with WAL + foreign_keys pragmas. This is the foundation — no other task can verify against the DB without this in place.

## Changes Description

### New Files
- `sql/wiki-index-v2.sql` — identical byte-copy of `docs/SCHEMA-v2.sql` (v2.0 multi-vault DDL). Becomes the canonical implementation-side schema.
- `sql/.AGENTS.md` — module memory: "SQL DDL files. Only edit via Schema Change Request workflow. SCHEMA-v2.sql in /docs is the planning artifact; sql/wiki-index-v2.sql is the runtime source. Keep in sync."
- `tests/test_schema_smoke.py` — pytest smoke test asserting DDL applies and contains required tables/views/triggers.

### Changes in Existing Files
None.

### Component Integration
None — this is the base layer; subsequent components (DAL, skills) consume the resulting DB.

## Test Cases

### End-to-end Tests
1. **TC-E2E-01**: Apply schema to a fresh SQLite file and verify table/view counts.
   - Input Data: empty `sqlite3 /tmp/wiki-test.db`; pragmas applied (`journal_mode=WAL`, `foreign_keys=ON`, `synchronous=NORMAL`).
   - Expected Result: `SELECT count(*) FROM sqlite_master WHERE type='table'` ≥ 10; `SELECT count(*) FROM sqlite_master WHERE type='view'` ≥ 1; `PRAGMA journal_mode` returns `wal`; `PRAGMA foreign_keys` returns `1`; **`PRAGMA user_version` returns `2`** (M-5 fix from architecture review).
2. **TC-E2E-02**: Dead-weight indexes on out-of-MVP tables are NOT created (M-6 fix).
   - Input Data: schema applied to fresh DB.
   - Expected Result: `SELECT count(*) FROM sqlite_master WHERE type='index' AND tbl_name IN ('interactions', 'extracted_items')` returns `0`. Tables exist (forward-compat), but their indexes are deferred to Epic 6 activation. (Indexes commented out in `sql/wiki-index-v2.sql` with `-- Epic 6 reactivation: uncomment ...`.)

### Unit Tests
1. **TC-UNIT-01**: Required tables present.
   - Tested entity: `sqlite_master`.
   - Input Data: schema applied.
   - Expected Result: tables `vaults`, `pages`, `entities`, `page_entity_refs`, `log_events`, `source_state`, `batch_runs`, `pages_fts`, `entities_fts` all present.
2. **TC-UNIT-02**: `vault_id` CHECK constraint rejects malformed IDs.
   - Tested entity: `vaults` INSERT.
   - Input Data: `INSERT INTO vaults VALUES ('1bad', ...)` (leading digit); `INSERT INTO vaults VALUES ('AB', ...)` (uppercase + too short); `INSERT INTO vaults VALUES ('foo--bar', ...)` (double hyphen).
   - Expected Result: all three raise `sqlite3.IntegrityError`.
3. **TC-UNIT-03**: FTS5 triggers sync `pages` → `pages_fts` on insert/update/delete.

### Regression Tests
- N/A (no prior code).

## Acceptance Criteria
- [ ] `sql/wiki-index-v2.sql` is a copy of `docs/SCHEMA-v2.sql` with TWO additions:
   - `PRAGMA user_version = 2;` appended after the schema bootstrap section (§13 in SCHEMA-v2.sql) so it's set on every fresh init (M-5 fix).
   - Indexes on `interactions` and `extracted_items` commented out with `-- Epic 6 reactivation: uncomment ...` markers (M-6 fix). Table DDLs preserved.
- [ ] `sqlite3 /tmp/wiki-test.db < sql/wiki-index-v2.sql` exits 0.
- [ ] `PRAGMA user_version` returns `2` after apply.
- [ ] All TC-UNIT + TC-E2E tests pass.
- [ ] `tests/test_schema_smoke.py` passes under pytest.
- [ ] `sql/.AGENTS.md` exists and notes the two deltas from `docs/SCHEMA-v2.sql`.

## Notes
- The schema is **locked** (do not modify). If a mismatch with reality is discovered, raise a Schema Change Request — do not edit directly.
- ADR-002 §D1 (single global DB, `vault_id` partitioning) and §D8 (Class A/B/C contract) are encoded in this DDL — read them before any modification proposal.
- M-4 (architecture review): all upserts MUST use `ON CONFLICT(...) DO UPDATE SET` — never `INSERT OR REPLACE`. Enforced in task-001-16.
