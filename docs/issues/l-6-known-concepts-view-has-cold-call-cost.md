---
id: L-6
type: known-issue
status: fixed
opened_at: 2026-05-26
category: logic
slug: l-6-known-concepts-view-has-cold-call-cost
---

# known_concepts view has cold-call cost

- **Symptom**: `known_concepts` view (SCHEMA-v2.sql line 470) uses `json_group_array(alias)` correlated subquery. Performant for read but unindexed.
- **Root cause**: Trade-off — correlated subquery is concise but uncached.
- **Affected components**: SCHEMA-v2.sql `known_concepts` view; task-001-17 search-pages impl (if it uses known_concepts).
- **Fix plan**: Document cold-call cost in view header comment. If wiki-ingest v1.1 known-concepts injection causes latency issue, materialise as a table populated by trigger.
