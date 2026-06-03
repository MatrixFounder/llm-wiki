# task-018-09 — [LOGIC] unmappable-type predictor (layout-general) + degenerate inputs

**Parent:** TASK 018. **Depends on:** 018-05 (+ the layout resolver). **RTM:** E2.3, AC-11, AC-12 (part), EC-2/EC-7/W-1.

## Goal
Finish the `.md` default route: a ready note → `upsert` only when `wiki-index-upsert` would
accept it; never raise on degenerate input.

## Design (locked — W-1)
The unmappable-type check must use **the same layout resolution `wiki-index-upsert`→
`normalize_frontmatter` evaluates** (the resolved vault layout's `type_mapping` /
`path_type_fallback`), NOT a hardcoded karpathy assumption.

## Steps
1. No-tag `.md`: resolve the vault layout (same path as the indexer); if the frontmatter `type:`
   maps (`type_mapping`) OR the file sits under a `path_type_fallback` subdir → `upsert`; else →
   `skip(reason="unmappable-type")` (flagged — avoids the `UnmappedTypeError` crash).
2. Degenerate (apply early, never raise): zero-byte / empty body → `skip(reason="empty-source")`;
   frontmatter that fails to parse → treat as no-frontmatter, route by path, `reason` carries
   `frontmatter-unparseable` (mirror `try/except yaml.YAMLError → fallback`).
3. GREEN: `test_unmappable_type_skips` (type-less prose .md under karpathy AND dev-project →
   skip, not raise), `test_empty_source_skips`, `test_unparseable_frontmatter_no_raise`.

## Verification
- `pytest -q -k "classify or unmappable or degenerate"` GREEN; `mypy --strict` clean.
