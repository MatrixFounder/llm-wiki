---
id: DF-4
type: known-issue
status: fixed
opened_at: 2026-05-29
category: dogfood
slug: df-4-wiki-alias-add-did-not-refuse-a-cross-name-hijack
---

# wiki-alias --add did not refuse a cross-NAME hijack

- **Symptom**: `wiki-alias <slug> --add "<surface>"` only refused a surface that resolved to a different entity's **slug or alias** (via `resolve_entity`). A surface equal to a different entity's canonical **name** was accepted, hijacking that name's resolution (e.g. adding `"Beta Engine"` — beta's name — to `alpha` routed searches for "Beta Engine" to alpha). `wiki-lint` flagged it as `cross_name` only after the fact.
- **Root cause**: `resolve_entity` resolves slug/alias, not name; the add-time collision pre-check used only `resolve_entity` (the functional-architecture doc's stated `resolve_entity + find_alias_collisions` pre-check was not fully implemented).
- **Affected components**: `scripts/wiki_skills/wiki_alias.py::main` (`--add`), `scripts/wiki_index/{repository,sqlite_repository}.py`.
- **Resolution**: added DAL `find_entity_by_name(vault_id, name) → slug | None`; `--add` now refuses a surface equal to a *different* entity's name (`ALIAS_COLLISION`, exit 5, "surface is the name of entity '<slug>'"). An entity's *own* name is still allowed. Regression: `tests/test_dogfood_fixes.py::test_df4_add_refuses_cross_name_hijack` (+ `_allows_own_name`). Found via the thorough collision dogfood.
