# 031-00 — config-driven layout registry (de-hardcode)  ·  `tdd-strict`

**Owns:** AC-3.1/3.2/3.3/3.4 + AC-7.1 (anchor). **Dep:** none (ship-separable). **Detail:** PLAN.md §2 / §3 🟡-1.

## Scope
Collapse the three sources of truth (`wiki_init._LAYOUT_CHOICES`/`_KARPATHY_LAYOUTS` :50-51; `layout_config._ALIAS` :194) into ONE cached YAML-derived registry. A new built-in `*.yaml` becomes a valid `--layout` value with zero Python edits.

## Files
- `config/layout-config.schema.yaml` — `#/$defs/LayoutConfig` += optional `aliases: {array<string>, default []}` + `init_scaffold: {enum [two-tier, none], default none}`. **LANDS FIRST** (strict `additionalProperties:false`).
- `scripts/wiki_index/layouts/karpathy.yaml` — += `aliases: [flat, per-project]` + `init_scaffold: two-tier`.
- `scripts/wiki_index/layout_config.py` — cached `_builtin_registry()` (key `(path, st_mtime_ns)`, re-glob each call) + `layout_choices()` / `resolve_alias()` / `is_two_tier_scaffold()` + `_reset_registry_cache()`; rewire `load_layout_config:416` to `resolve_alias`.
- `scripts/wiki_skills/wiki_init.py` — drop the 2 literals; `--layout choices=layout_choices()`; `:173`+`:299` → `is_two_tier_scaffold(...)`.

## Stub-First (RED → GREEN)
Tests first: `test_layout_choices_includes_builtins_and_aliases`, `test_is_two_tier_scaffold` (T: karpathy/flat/per-project; F: dev-project/obsidian-personal/cybos), `test_resolve_alias_parity` (flat/per-project→karpathy), `test_dropin_new_layout_appears` (temp yaml + `_reset_registry_cache()` → cache-invalidation/isolation proof, 🟡-1), `test_wiki_init_rejects_unknown_layout`. Keep `test_alias_resolution_to_karpathy` + `test_karpathy_config_matches_layout_constants` green.

## Verify
Golden anchor (`test_karpathy_byte_identity.py`) + invariant test green; `mypy --strict scripts/`. Registry reads built-ins only (no operator file at choice time); does not worsen R-X1-CFG-COST.
