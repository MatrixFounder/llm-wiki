# Task 006-02: append_log_event stops setting event_date (L-2 code half)

## Ledger id: L-2

## Goal
`event_date` is now a STORED generated column (006-01) — the inserter must not
supply it (inserting a value for a generated column raises).

## Changes
### `scripts/wiki_index/sqlite_repository.py::append_log_event`
- Drop the `event_date` computation (`event_date = event.event_ts.date().isoformat()`).
- Remove `event_date` from the INSERT column list AND the values tuple.

## Test cases
1. `append_log_event(LogEvent(event_ts=2026-05-29T10:00:00, …))` → stored row's `event_date == '2026-05-29'` (computed by the DB, not the caller).
2. `query_log_events` date-range filtering returns the event unchanged (read path intact).
3. Regression: existing log_events / wiki-append-log tests green.

## Acceptance
- [ ] `append_log_event` no longer references `event_date`.
- [ ] Round-trip `event_date == event_ts[:10]`.
- [ ] `pytest tests/` green; `mypy --strict` clean.

## Notes
Depends on 006-01 (the column must be GENERATED first, else the dropped insert would leave it NULL on the old NOT-NULL column). Stub-first: RED test asserting generated value before removing the inserter line.
