---
id: DF-5
type: known-issue
status: fixed
opened_at: 2026-05-29
category: dogfood
slug: df-5-wiki-alias-add-created-a-redundant-self-alias
---

# wiki-alias --add created a redundant self-alias

- **Symptom**: `wiki-alias <slug> --add "<slug>"` (an entity's own slug as alias) inserted a redundant `slug -> slug` row (`action: added`) — harmless (resolution unaffected, no false lint positive) but noise.
- **Root cause**: the add path only short-circuited when the surface already resolved to a *different* entity; a surface resolving to *this* entity (own slug / own alias) fell through to the insert.
- **Affected components**: `scripts/wiki_skills/wiki_alias.py::main` (`--add`).
- **Resolution**: a surface that resolves to THIS entity now returns `action: unchanged` (no row written). Regression: `tests/test_dogfood_fixes.py::test_df5_add_own_slug_is_unchanged_not_redundant_alias`.

---
