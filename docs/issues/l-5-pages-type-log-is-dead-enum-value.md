---
id: L-5
type: known-issue
status: fixed
opened_at: 2026-05-26
category: logic
slug: l-5-pages-type-log-is-dead-enum-value
---

# pages.type='log' is dead enum value

- **Symptom**: `pages.type` enum includes `'log'` (SCHEMA-v2.sql line 167) but log content lives in `log.md` (Class A file rendered by wiki-ingest), not as a page row.
- **Root cause**: Leftover from v1 design; unused.
- **Affected components**: SCHEMA-v2.sql pages.type CHECK, task-001-26 (wiki-index-render).
- **Fix plan**: Remove `'log'` from enum. Verify task-001-26 doesn't create log-type pages.
