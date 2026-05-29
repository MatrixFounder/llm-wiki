# Task 005-01: Schema v2→v3 — entity_aliases PK fix + index swap (R-5.4, closes L-4)

## Use Case Connection
- UC-11 (alias mgmt — hard uniqueness), UC-13 (lint collision — PK blocks new in-DB dups)
- Closes KNOWN_ISSUES **L-4**

## Task Goal
Migrate the schema to v3: `entity_aliases` PK becomes `(vault_id, alias)` (one alias → exactly one entity per vault), drop the now-redundant `idx_aliases_lookup`, add the reverse-lookup `idx_aliases_entity (vault_id, entity_slug)`, and bump `PRAGMA user_version 2→3` + `schema_meta`. DB is Class B → migration for existing DBs is `wiki-reindex --full`, not in-place ALTER.

## Changes Description

### Changes in Existing Files
#### File: `docs/SCHEMA-v2.sql` and `sql/wiki-index-v2.sql` (keep both in sync)
- `entity_aliases`: change `PRIMARY KEY (vault_id, alias, entity_slug)` → `PRIMARY KEY (vault_id, alias)`; `entity_slug` stays `TEXT NOT NULL` (regular column, FK retained).
- **Drop** `CREATE INDEX ... idx_aliases_lookup ON entity_aliases(vault_id, alias)` (now a duplicate of the PK's implicit index).
- **Add** `CREATE INDEX IF NOT EXISTS idx_aliases_entity ON entity_aliases(vault_id, entity_slug);`
- Bump the `PRAGMA user_version = 3;` line (was 2); insert/update `schema_meta` row `('schema_version','3')`.
- Inline comment referencing L-4 closure.

#### File: `docs/adr/ADR-002-multi-vault-bottleneck-corrections.md` (or new `docs/adr/ADR-003-*.md` stub)
- §D8 amendment note: v2→v3 PK change; DB is Class B rebuildable so the migration is a full reindex (no ALTER); operators on an existing DB run one `wiki-reindex --full`.

## Test Cases
### Unit Tests (`tests/test_schema_v3.py` — new)
1. **TC-UNIT-01:** fresh `SQLiteRepository(...).apply_schema()` → `PRAGMA user_version` returns `3`.
2. **TC-UNIT-02:** insert `(v, "Hermes", "hermes-agent")` then `(v, "Hermes", "hermes-bus")` → second raises `sqlite3.IntegrityError` (PK uniqueness on `(vault_id, alias)`).
3. **TC-UNIT-03:** `idx_aliases_entity` present and `idx_aliases_lookup` absent in `sqlite_master` (query `WHERE type='index'`).
### Regression
- Run `pytest tests/` — schema-dependent fixtures rebuild cleanly under v3.

## Acceptance Criteria
- [ ] Both DDL files updated identically; `user_version == 3`.
- [ ] Same-alias→two-slug insert is rejected at the DB layer.
- [ ] `idx_aliases_entity` added; `idx_aliases_lookup` removed.
- [ ] ADR §D8 amendment (or ADR-003 stub) present; migration = full reindex documented.
- [ ] `pytest tests/` green; `mypy --strict scripts/` clean.

## Notes
Single-pass DDL bead (declarative — no Python stub). Blocks all alias DAL (005-06/07) and the reindex alias mirror (005-03). No data migration code: gitignored Class B DB is rebuilt by `wiki-reindex --full`.
