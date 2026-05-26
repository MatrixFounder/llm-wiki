# Task 001-19: `SQLiteRepository` `log_events` CRUD [LOGIC IMPLEMENTATION]

## Use Case Connection
- UC-02 step 11, UC-04, UC-05, UC-07 (all skills append log events)
- R-28 (structured log_events table)

## Task Goal
Implement `append_log_event`, `query_log_events`, `begin_batch_run`, `finish_batch_run`, `last_batch_run` on `SQLiteRepository`. `append_log_event` returns the autoincrement `id` so the caller (task-001-27 `wiki-append-log`) can record `log_md_byte_offset` for bi-directional sync.

## Changes Description

### New Files
None.

### Changes in Existing Files

#### File: `scripts/wiki_index/sqlite_repository.py`

**Method `append_log_event(self, event: LogEvent) -> int`:**
- `INSERT INTO log_events (vault_id, event_ts, event_type, subject, pages_created_json, pages_updated_json, details_json, log_md_path, log_md_byte_offset) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`.
- Serialize `pages_created_json` and `pages_updated_json` via `json.dumps` (lists of slugs).
- Serialize `details_json` via `json.dumps`.
- Use `cursor.lastrowid` to return autoincrement `id`.
- Wrap in `BEGIN IMMEDIATE` (log_events writes are write-side ops; reads need WAL snapshot).

**Method `query_log_events(self, vault_id: str, *, since: datetime | None = None, until: datetime | None = None, event_types: list[str] | None = None) -> list[LogEvent]`:**
- Build SELECT with parameterized `WHERE vault_id = ?` + optional `AND event_ts >= ?` + optional `AND event_ts <= ?` + optional `AND event_type IN (...)`.
- `ORDER BY event_ts ASC, id ASC`.
- Map rows to `LogEvent` dataclasses; deserialize JSON columns.

**Method `begin_batch_run(self, vault_id: str, mode: Literal['full','delta']) -> int`:**
- `INSERT INTO batch_runs (vault_id, mode, started_at, status) VALUES (?, ?, ?, 'in_progress')` with `started_at = datetime.now().isoformat()`.
- Return `cursor.lastrowid`.

**Method `finish_batch_run(self, run_id: int, status: str, notes: str | None = None) -> None`:**
- `UPDATE batch_runs SET finished_at=?, status=?, notes=? WHERE id=?`.
- `finished_at = datetime.now().isoformat()`.

**Method `last_batch_run(self, vault_id: str) -> BatchRun | None`:**
- `SELECT * FROM batch_runs WHERE vault_id=? ORDER BY started_at DESC LIMIT 1`.
- Map to `BatchRun` or None.

### Component Integration
- `wiki-append-log` (task-001-27) calls `append_log_event` then writes the corresponding line to `log/{YYYY-MM}.md` and updates `log_md_byte_offset` via a follow-up `UPDATE log_events SET log_md_byte_offset=? WHERE id=?` query exposed via helper.
- `wiki-reindex --full` (task-001-30) uses `begin_batch_run` / `finish_batch_run` to bracket the reindex transaction and emit synthetic log events.

## Test Cases

### End-to-end Tests
1. **TC-E2E-01**: Append event → query by `vault_id` returns it.
2. **TC-E2E-02**: Append events at different timestamps → query with `since=t1` returns only events after `t1`.
3. **TC-E2E-03**: `begin_batch_run` → returns positive int; `finish_batch_run` updates status; `last_batch_run` reflects it.

### Unit Tests
1. **TC-UNIT-01**: `pages_created_json` round-trip preserves list ordering.
2. **TC-UNIT-02**: `event_type` CHECK rejects unknown types (relies on schema CHECK).
3. **TC-UNIT-03**: `vault_id` FK violation (insert event for non-existent vault) → `IntegrityError`.
4. **TC-UNIT-04**: `query_log_events` with `event_types=['ingest','reindex']` filters correctly.
5. **TC-UNIT-05**: `last_batch_run` returns None for vault with no runs.

### Regression Tests
- task-001-16 upsert tests still pass.

## Acceptance Criteria
- [ ] All five methods implemented per spec.
- [ ] JSON columns round-trip correctly.
- [ ] CHECK + FK constraints surfaced as Python exceptions.
- [ ] All TC tests pass.
- [ ] `mypy --strict` passes.

## Notes
- ADR-002 §D2 specifies the `log_events` table is the Class B mirror; Class A canonical is `log.md`. Bi-directional sync wired in task-001-27.
- `log_md_byte_offset` is populated after the markdown write — initial `INSERT` may leave it NULL.
- M-2 (architecture review): log.md ↔ log_events round-trip is a Phase 3a-critical contract; tested in task-001-27 + task-001-30.
