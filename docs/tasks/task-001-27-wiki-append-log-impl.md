# Task 001-27: `wiki-append-log` impl — bi-directional sync `log.md` ↔ `log_events` [LOGIC IMPLEMENTATION]

## Use Case Connection
- UC-02 step 11, UC-04, UC-05, UC-06, UC-07 (every state-mutating skill appends a log event)
- R-09 (monthly rotation)
- R-28 (log_events table)
- M-2 (architecture review): round-trip sync contract

## Task Goal
Replace `wiki-append-log` stub with the real impl. CRITICAL: write order is `log_events INSERT first → get id + offset → write to log.md → UPDATE log_events SET log_md_byte_offset=?`. Both writes happen atomically (single advisory lock); on either failure, both are rolled back. Monthly rotation per R-09.1.

## Changes Description

### New Files
- `scripts/wiki_index/logfile.py`:
  - `def rotate_log_path(vault_root: Path, when: datetime) -> Path:` — returns `<vault>/00-Vault-Index/log/{YYYY-MM}.md`. Creates the parent dir if missing.
  - `def render_event_line(event: LogEvent) -> str:` — markdown format per UC-02 step 11:
    ```
    ## [2026-05-26 14:55:00] ingest | <subject>
    - pages_created: [slug1, slug2]
    - pages_updated: [slug3]
    ```
  - `def append_atomic(log_path: Path, line: str) -> int:` — opens with `O_APPEND | O_CREAT`, acquires `fcntl.flock` (exclusive), writes line, returns the byte offset at which the line started (via `os.lseek(fd, 0, SEEK_END)` before write), releases lock.
  - `def parse_log_md(path: Path) -> list[tuple[datetime, str, str, int]]:` — reverse direction: parses existing log.md back into events (used by reindex in task-001-30). Returns `(event_ts, event_type, subject, byte_offset)` per `## [...]` heading.

### Changes in Existing Files

#### File: `scripts/wiki_skills/wiki_append_log.py`
- Replace stub `main()`:
  - Args: `--vault <id>`, `--event-type <type>`, `--subject <str>`, `--details-json <path-or-inline-json>`.
  - `config = load_config()`; `repo = make_repo(config)`.
  - `vault_root = repo.get_vault(vault_id).root_path`.
  - `log_path = rotate_log_path(vault_root, datetime.now())`.
  - Build `LogEvent(id=None, vault_id=..., event_ts=now_iso(), event_type=args.event_type, subject=..., details_json=..., log_md_path=str(log_path.relative_to(vault_root)), log_md_byte_offset=None)`.
  - Acquire flock on `<vault>/_raw/.locks/log.lock`.
  - Step 1: `event_id = repo.append_log_event(event)`.
  - Step 2: `byte_offset = append_atomic(log_path, render_event_line(event))`.
  - Step 3: `repo.update_log_event_offset(event_id, byte_offset)` (N-3 fix — public DAL method, NOT `repo._connect()` private accessor; preserves DAL boundary). Commit happens inside repository method.
  - On any failure: catch, log diagnostic, rollback DB transaction (DELETE the just-inserted log_events row), best-effort truncate log.md back to pre-write size.
  - Release flock.
  - JSON: `{"action": "logged", "event_id": ..., "log_md_path": ..., "byte_offset": ...}`.

#### File: `scripts/wiki_index/repository.py`
- Add abstract method `def update_log_event_offset(self, event_id: int, byte_offset: int) -> None: ...`.

#### File: `scripts/wiki_index/sqlite_repository.py`
- Implement: `UPDATE log_events SET log_md_byte_offset=? WHERE id=?`.

### Component Integration
- Every state-mutating skill (`wiki-index-upsert`, `wiki-lint --fix`, `wiki-reindex`) calls `wiki-append-log` (or invokes its function directly to avoid subprocess overhead).
- M-2 sync contract: a reindex (task-001-30) parses log.md back via `parse_log_md` and verifies each line matches a `log_events` row at the recorded byte_offset (regression check after rebuildability).

## Test Cases

### End-to-end Tests
1. **TC-E2E-01**: Append event → `log/{YYYY-MM}.md` exists with rendered line; `log_events` row has matching `log_md_byte_offset` pointing to the start of that line.
2. **TC-E2E-02**: Monthly rotation: events spanning May→June land in two separate files (`2026-05.md`, `2026-06.md`).
3. **TC-E2E-03**: Simulated mid-write failure: `log_events` row NOT present after rollback (atomicity).
4. **TC-E2E-04**: Concurrent append from two processes: flock serializes; both events present with distinct offsets.

### Unit Tests
1. **TC-UNIT-01**: `render_event_line` matches the documented format.
2. **TC-UNIT-02**: `append_atomic` returns correct byte offset (verified by re-reading at that offset).
3. **TC-UNIT-03**: `parse_log_md` round-trip: append N events, parse → all N reconstructed in order.
4. **TC-UNIT-04**: Invalid `event_type` rejected by schema CHECK → no log.md write (DB-side fail-fast).

### Regression Tests
- task-001-19 log_events CRUD still works.

## Acceptance Criteria
- [ ] Bi-directional sync verified (TC-E2E-01, TC-UNIT-03).
- [ ] Monthly rotation works.
- [ ] Atomicity verified.
- [ ] `log_md_byte_offset` always populated for successfully-appended events.
- [ ] M-2 round-trip contract validated.

## Notes
- ADR-002 §D2 explicitly designates `log_events.log_md_byte_offset` as the bridge — it's REQUIRED for round-trip reindex (task-001-30).
- Rollback strategy: if step 2 fails (e.g., disk full), step 1's INSERT is undone. If step 3 fails (UPDATE), step 2's line is truncated. Best-effort cleanup; document any non-atomic remainder in `KNOWN_ISSUES.md`.
- `fcntl.flock` is POSIX-only — Windows compatibility is best-effort per [TASK.md §5.3](../TASK.md).
