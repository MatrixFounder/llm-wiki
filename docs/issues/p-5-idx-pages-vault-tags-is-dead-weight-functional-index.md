---
id: P-5
type: known-issue
status: fixed
opened_at: 2026-05-26
category: performance
slug: p-5-idx-pages-vault-tags-is-dead-weight-functional-index
---

# idx_pages_vault_tags is dead-weight functional index

- **Symptom**: `idx_pages_vault_tags ON pages(vault_id, json_extract(frontmatter_json, '$.tags'))` is maintained on every upsert but indexes a JSON array (compared as string), which provides no useful query path. Tag queries should route through `pages_fts.tags`.
- **Root cause**: Speculative index added during schema design; never used by any query.
- **Affected components**: `sql/wiki-index-v2.sql`, `docs/SCHEMA-v2.sql`.
- **Fix plan**: Drop the index. If tag selectivity becomes a real need, build a `pages_tags(vault_id, slug, tag)` join table populated by trigger.

---
