---
id: L-1
type: known-issue
status: fixed
opened_at: 2026-05-26
category: logic
slug: l-1-entities-file-path-unique-invariant-not-explicit
---

# entities.file_path UNIQUE invariant not explicit

- **Symptom**: Architecture review noted `entities.file_path UNIQUE per (vault_id, file_path)` (SCHEMA-v2.sql line 116) but `entity_aliases` has no FK back to a unique key on entities other than `(vault_id, slug)`. Invariant that file_path may not collide with another entity's alias-target path is implicit.
- **Root cause**: Documentation gap, not behavior bug.
- **Affected components**: `docs/SCHEMA-v2.sql` (header comment), `sql/wiki-index-v2.sql` (when created via task-001-01).
- **Fix plan**: Add inline comment in SCHEMA-v2.sql + sql/wiki-index-v2.sql clarifying the invariant.
