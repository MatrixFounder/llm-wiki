# task-022-03 — JSON schema: `index_db` add + override ban (DiD) [R-022-1]

**Goal:** document `index_db` in `WikiRootConfig` and forbid it (with `vault_id`) in
`WikiProjectOverride`. Defense-in-depth — the binding validation is in task-022-01.

**Context (read/edit):**
- `config/wiki-config.schema.yaml` — `$defs.WikiRootConfig` (validated by `config_loader.load_root_config`
  against the merged frontmatter; `additionalProperties: true`), `$defs.WikiProjectOverride` (the
  existing `vault_id` ban is `not: {required: [vault_id]}`).

**Steps:**
1. `WikiRootConfig.properties.index_db: {type: string, minLength: 1}` (path semantics validated in
   code, NOT a schema pattern — do not over-constrain).
2. `WikiProjectOverride`: replace the lone `not: {required: [vault_id]}` with
   `allOf: [{not: {required: [vault_id]}}, {not: {required: [index_db]}}]` (a single
   `not: {required: [vault_id, index_db]}` only rejects having BOTH — wrong).

**Verification:** `pytest tests/test_schema_index_db.py -q`
- `Draft202012Validator(<#/$defs/WikiRootConfig>)` accepts `{vault_id:"v", index_db:".wiki/index.db"}`;
- `…(<#/$defs/WikiProjectOverride>)` is INVALID for `{index_db:"x"}` AND for `{vault_id:"v"}`, VALID for `{}`.
- `python -c "import yaml; yaml.safe_load(open('config/wiki-config.schema.yaml'))"` (still parses).
