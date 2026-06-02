# task-017-02 — [LOGIC] provenance booleans in `load_layout_config`

**Parent:** TASK 017. **Depends on:** 017-01. **RTM:** Q-017-1, R-017-1e.

## Goal
Populate `ref_extraction_operator_supplied` / `paths_operator_supplied` from whether the
per-vault override actually supplied that key, so the runtime guard runs **only** for
operator-custom patterns (built-ins pay zero).

## Design (locked — ARCHITECTURE.md §3.5; Q-012-f merge policy)
`load_layout_config` resolves `merged = builtin_base`, then deep-merges the optional override
(`WIKI_SCHEMA.md` frontmatter `layout_config:` or `<vault>/.wiki/layout.yaml`). The Q-012-f
policy **replaces** the whole `paths`/`ref_extraction` list when the operator supplies it →
provenance is per-list-exact: `paths_operator_supplied = ('paths' in override_dict)`,
`ref_extraction_operator_supplied = ('ref_extraction' in override_dict)`. Thread the two
booleans into `_build(...)` → onto the frozen `LayoutConfig`. The no-override path and
`resolve_layout_config`'s built-in-only path both leave them `False`.

## Steps
1. In `load_layout_config`, capture the override dict (the value already deep-merged in);
   compute the two booleans before/at `_build`.
2. Pass them through `_build` (or set on the dataclass at construction).
3. GREEN `test_provenance_flags_on_override`; add `test_provenance_false_builtin`
   (`resolve_layout_config(karpathy_vault)` → both `False`).

## Verification
- `pytest -q tests/test_task017_hardening.py -k provenance` GREEN.
- Existing layout-config + karpathy-byte-identity tests unaffected; `mypy --strict` clean.
