# 031-01 — cybos layout + dev-project type_mapping (the taxonomy)

**Owns:** AC-1.1/1.2/1.3 + AC-2.1/2.2/2.3. **Dep:** 031-00 (schema; `--layout cybos`). **Detail:** PLAN.md §2.

## Scope
Add the 7 typed knowledge classes (decision/requirement/risk/incident/hypothesis/fact/event), **zero DDL**, tag-routed onto existing db_types. Ship the new `cybos` layout (full folders) + extend `dev-project` (`type_mapping` only).

Routing (db_type ∈ existing enum): decision→research/decision · requirement→brief/requirement · risk→research/risk · incident→research/incident · hypothesis→research/hypothesis · fact→concept/fact · event→summary/event.

## Files
- `scripts/wiki_index/layouts/cybos.yaml` — NEW full layout: `slug_strategy: transliterate`, `init_scaffold: none`, `ignore` (.git/.obsidian/.DS_Store/_raw/.staging), `paths[]` for `decisions/ requirements/ risks/ incidents/ hypotheses/ facts/ events/ tasks/ adr/ plans/` (project `_vault_`), `type_mapping` (7 classes + task/plan/adr spine), `ref_extraction` (wiki-link/markdown-link/id-ref, mirror dev-project), `frontmatter_synthesis: {enabled: true}`, optional `auto_indexes` (decisions→DECISIONS.md), inline per-type comments.
- `scripts/wiki_index/layouts/dev-project.yaml` — append the 7 `type_mapping` entries (additive; `paths[]` untouched).

## Stub-First (RED → GREEN)
Extend `tests/test_config_type_mapping.py`: all 7 routes (db_type+tag) via `load_layout_config` for BOTH dev-project + cybos. `test_cybos_config_loads_and_validates` (schema-valid, 7 path globs, `init_scaffold none`). E2E reindex over `tests/fixtures/cybos/` → correct `pages.type`+tags, `skipped`/`slug_collisions` empty (AC-2.2). AC-2.3: reserved edge keys NOT extracted as refs.

## Verify
Karpathy anchor green (changes isolated to cybos/dev-project); `mypy --strict`. No new db_type; `user_version` 5.
