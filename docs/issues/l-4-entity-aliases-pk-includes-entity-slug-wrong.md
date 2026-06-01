---
id: L-4
type: known-issue
status: fixed
opened_at: 2026-05-26
category: logic
slug: l-4-entity-aliases-pk-includes-entity-slug-wrong
---

# entity_aliases PK includes entity_slug (wrong)

- **Symptom**: `entity_aliases` PK `(vault_id, alias, entity_slug)` allows the same alias to point at two different entity_slugs in one vault. Probably wrong — `"Sharpe ratio"` should resolve to a single entity.
- **Root cause**: Schema design error.
- **Affected components**: SCHEMA-v2.sql §3 entity_aliases.
- **Resolution (TASK 005 / R-5.4, 005-01)**: PK changed to `(vault_id, alias)`; `entity_slug` is now a regular column; `idx_aliases_lookup` dropped (duplicate of the PK index), `idx_aliases_entity (vault_id, entity_slug)` added for the reverse lookup; `PRAGMA user_version` 2→3. The DB is Class B rebuildable, so the migration is `wiki-reindex --full` (no in-place ALTER) — documented in the ADR-002 §D8 amendment. Guarded by `tests/test_schema_v3.py::test_alias_pk_rejects_same_alias_two_slugs`.
