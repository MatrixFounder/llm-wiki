---
id: L-3
type: known-issue
status: open
opened_at: 2026-05-26
category: logic
slug: l-3-interactions-id-is-three-identifiers-in-one
---

# interactions.id is three identifiers in one

- **Symptom**: `interactions` has `id TEXT` (composite-style `'{kind}:{source_id}'`) AND PK `(vault_id, id)` AND separate UNIQUE `(vault_id, source_kind, source_id)`. Three identifiers for one row.
- **Root cause**: Carry-over from cybos pattern; redundant.
- **Affected components**: SCHEMA-v2.sql §7 interactions table.
- **Fix plan**: Drop synthetic `id` column; PK becomes `(vault_id, source_kind, source_id)`. Out-of-MVP (Epic 6) — defer fix until Epic 6 activates this table.
