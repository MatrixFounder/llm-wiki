---
id: L-2
type: known-issue
status: fixed
opened_at: 2026-05-26
category: logic
slug: l-2-log-events-event-date-should-be-generated-always-column
---

# log_events.event_date should be GENERATED ALWAYS column

- **Symptom**: `log_events.event_date` is currently a regular TEXT column populated by inserter logic. Drift risk if inserter forgets to set it to `substr(event_ts, 1, 10)`.
- **Root cause**: Schema design — Class B (denorm) column without storage discipline.
- **Affected components**: `docs/SCHEMA-v2.sql` log_events DDL (line ~232), `sql/wiki-index-v2.sql`, task-001-19 log_events-CRUD impl.
- **Fix plan**: Convert to `event_date TEXT GENERATED ALWAYS AS (substr(event_ts, 1, 10)) STORED`. Schema-level guarantee.
