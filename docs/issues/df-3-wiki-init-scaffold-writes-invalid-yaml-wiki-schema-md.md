---
id: DF-3
type: known-issue
status: fixed
opened_at: 2026-05-29
category: dogfood
slug: df-3-wiki-init-scaffold-writes-invalid-yaml-wiki-schema-md
---

# wiki-init scaffold writes invalid-YAML WIKI_SCHEMA.md

- **Symptom**: `wiki-init --scaffold-new` produced a `WIKI_SCHEMA.md` whose frontmatter `description: LLM Wiki vault: <id>` had an **unquoted colon** → invalid YAML (`ScannerError`). `_split_frontmatter` swallowed the error → empty dict → `--register-existing` failed with `MISSING_VAULT_ID` for **every** scaffolded vault, breaking the §D8 rebuild-from-Class-A path. Pre-existing (Phase 3a wiki-init), surfaced by the TASK 005 dogfood.
- **Root cause**: `templates/WIKI_SCHEMA.md.tmpl` rendered `description: ${description}` unquoted; the default description contains `": "`.
- **Affected components**: `templates/WIKI_SCHEMA.md.tmpl`, `scripts/wiki_skills/wiki_init.py::scaffold_new`.
- **Resolution**: template now renders `description: "${description}"` (quoted scalar) + `scaffold_new` sanitizes embedded `"`/newlines. Regression: `tests/test_dogfood_fixes.py::test_df3_scaffold_emits_valid_yaml_and_registers` (fresh scaffold parses + `--register-existing` succeeds).
