# Task 006-01: Schema v3→v4 (drop dead index + dead enum + GENERATED event_date)

## Ledger ids: MIG, P-5, L-5, L-2 (schema half)

## Goal
Land the v3→v4 DDL hygiene changes in both schema files; bump the version marker.

## Changes
### `sql/wiki-index-v2.sql` + `docs/SCHEMA-v2.sql` (keep in sync)
- **P-5**: delete `CREATE INDEX … idx_pages_vault_tags ON pages(vault_id, json_extract(frontmatter_json,'$.tags'))`.
- **L-5**: remove `'log'` from the `pages.type` CHECK enum list.
- **L-2**: `log_events.event_date TEXT NOT NULL` → `event_date TEXT GENERATED ALWAYS AS (substr(event_ts, 1, 10)) STORED` (keep `idx_log_vault_date` — indexes the STORED column).
- Bump `PRAGMA user_version = 3;` → `4;`; update `schema_meta` comment to 4.0.
### `docs/adr/ADR-002-*.md`
- §D8 amendment: v3→v4 = three Class-B DDL hygiene changes; migration = `wiki-reindex --full` (no ALTER — STORED generated column can't ALTER into a populated table).
### `tests/test_schema_smoke.py`
- assert `user_version == 4`.

## Test cases (`tests/test_schema_v4.py` — new)
1. fresh `apply_schema` → `PRAGMA user_version == 4`.
2. `idx_pages_vault_tags` absent from `sqlite_master`.
3. `INSERT INTO pages(… type='log' …)` → `sqlite3.IntegrityError` (CHECK).
4. `INSERT INTO log_events(… NO event_date …, event_ts='2026-05-29T10:00:00')` → stored `event_date == '2026-05-29'` (generated; inserting `event_date` explicitly raises).

## Acceptance
- [ ] Both DDL files updated identically; `user_version==4`.
- [ ] Dead index + dead enum gone; `event_date` generated.
- [ ] ADR §D8 v3→v4 note; smoke test ==4.
- [ ] `pytest tests/` green; `mypy --strict` clean.

## Notes
Single-pass DDL (declarative). Blocks 006-02 (inserter) + 006-05 (lint scan). Migration = reindex (Class B), per ADR.
