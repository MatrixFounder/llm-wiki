# Task 001-31: `wiki-reindex --delta` impl — mtime-based incremental [LOGIC IMPLEMENTATION]

## Use Case Connection
- Operator routine maintenance
- SLO: < 100ms / 100 docs (no changes) per [TASK.md §5.1](../TASK.md)

## Task Goal
Replace `wiki-reindex --delta` stub with the incremental impl: read `vaults.last_ingest_at` (or `MAX(log_events.event_ts WHERE event_type='ingest')` if NULL), walk filesystem and re-index only files with `mtime > last_ingest_at`. Delete DB rows for files that disappeared from disk.

## Changes Description

### New Files
None.

### Changes in Existing Files

#### File: `scripts/wiki_index/reindex.py`

**Function `reindex_delta(repo: IndexRepository, vault_id: str) -> dict`:**
- `vault = repo.get_vault(vault_id)`.
- Determine cutoff:
  - `last_event = repo.last_event_at(vault_id)` (new helper — see below) OR `vault.registered_at` if no events.
- `paths_on_disk = discover_pages(vault_root)`.
- For each path: if `path.stat().st_mtime > cutoff_timestamp` → re-ingest via same code path as `reindex_full` step 6.
- Cross-check: query `SELECT slug, project FROM pages WHERE vault_id=?`; for any DB row whose path no longer exists on disk → `repo.delete_page(...)` (and emit `log_event(event_type='ingest', details={action: 'deleted'})`).
- Emit `LogEvent(event_type='reindex', subject='delta', details={touched: N, deleted: K})`.

**Function `last_event_at(self, vault_id: str) -> datetime | None` in `SQLiteRepository`:**
- `SELECT MAX(event_ts) FROM log_events WHERE vault_id=?`.

**Function `repository.py` abstract:**
- Add `def last_event_at(self, vault_id: str) -> datetime | None: ...`.

### Changes in Existing Files

#### File: `scripts/wiki_skills/wiki_reindex.py`
- Wire `--delta` → `reindex_delta(...)`.

### Component Integration
- Operator-facing routine — much faster than `--full` for steady-state operations.
- SLO < 100ms / 100 docs (no changes) hinges on mtime stat being O(N) only.

## Test Cases

### End-to-end Tests
1. **TC-E2E-01**: After `reindex --full`, immediate `reindex --delta` → 0 files touched, exit 0.
2. **TC-E2E-02**: Touch one file → `reindex --delta` → exactly that file re-indexed.
3. **TC-E2E-03**: Delete one file → `reindex --delta` → DB row removed.

### Unit Tests
1. **TC-UNIT-01**: SLO: 100-doc fixture, no changes → < 100ms.
2. **TC-UNIT-02**: `last_event_at` returns latest timestamp.

### Regression Tests
- task-001-30 full reindex still works.

## Acceptance Criteria
- [ ] Delta logic per spec.
- [ ] Deletion detection works.
- [ ] SLO met.
- [ ] All TC tests pass.

## Notes
- Mtime-based detection can miss in-place edits with preserved mtime (rare); rely on `--full` periodically for safety.
- The cutoff timestamp is `last_ingest_at` (from `log_events` MAX), NOT `registered_at` — operator intent matters.
