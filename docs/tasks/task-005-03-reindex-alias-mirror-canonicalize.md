# Task 005-03: reindex mirrors `aliases:` + canonicalizes ref targets (R-5.3, AM-3)

## Use Case Connection
- UC-14 (alias rebuilt from frontmatter), UC-15 (merge durability — mentions/backlinks survive reindex)

## Task Goal
Two reindex round-trip closures, both load-bearing for §D8 durability:
1. **R-5.3** — mirror each entity page's Class A `aliases:` frontmatter into `entity_aliases` (Class B), **report-and-skip** on hard-PK collision (never silent `INSERT OR IGNORE`).
2. **AM-3** — canonicalize `page_entity_refs.entity_slug` through the alias table at build time so a `[[surface]]` whose target is a registered alias is stored under the **canonical** slug. Enforces phase order **entities → aliases → refs → recompute_mentions** so `recompute_mentions`/`get_backlinks` survive a rebuild.

## Changes Description

### Changes in Existing Files
#### File: `scripts/wiki_index/reindex.py` (`reindex_full`)
- After entity registration, **before** ref insertion: parse `updated_fm.get("aliases")` (flat list) per entity page; insert into `entity_aliases` with `alias_type='spelling_variant'` (default — flat list carries no type, documented C-4 limitation). On `IntegrityError` (PK `(vault_id, alias)` collision), append `{alias, kept_slug, skipped_slug}` to the run's `skipped`/warnings report; do **not** abort.
- Build an in-memory `alias_map: dict[str, str]` (`alias → canonical entity_slug`) once per vault (set-based, **no per-ref SQL** — see Risk R-1).
- In the ref-build loop, canonicalize each `PageRef.entity_slug`: `alias_map.get(raw_target, raw_target)`.
- Move `recompute_mentions` to run **after** the canonicalized ref insert (it already runs at Step 3 — confirm ordering).

## Test Cases
### E2E Tests (`tests/test_reindex.py`)
1. **TC-E2E-01:** entity page `_concepts/hermes-agent.md` with `aliases: ["Hermes", "Hermes Framework"]` → `reindex_full` → two `entity_aliases` rows for `hermes-agent`. *(RED — reindex never mirrored aliases.)*
2. **TC-E2E-02:** a source page with `[[Hermes]]` where `Hermes` is an alias of `hermes-agent` → its `page_entity_refs` row stored with `entity_slug='hermes-agent'` (canonicalized), not `'hermes'`.
3. **TC-E2E-03:** two entity pages declaring the same alias → reindex completes; one mirrored, the other recorded in the skipped report (no crash, no silent drop).
4. **TC-E2E-04:** `into.mentions_count` after reindex counts the canonicalized refs (proves AM-3 union survives).
### Regression
- `pytest tests/test_reindex.py tests/` green.

## Acceptance Criteria
- [ ] `aliases:` mirrored to `entity_aliases`; PK collision → report-and-skip (recorded, not silent).
- [ ] Ref targets canonicalized via a per-vault alias map (set-based, no per-ref query).
- [ ] Phase order entities → aliases → refs → recompute enforced.
- [ ] AM-3: mentions/backlinks reflect canonical slugs after a full rebuild.
- [ ] `mypy --strict` clean; regression green.

## Notes
The durability spine. Depends on 005-01 (v3 PK + `idx_aliases_entity`). Risk R-1 mitigation: alias map built once, not per-ref. Exercised end-to-end by 005-16 (UC-15 §D8 gate).
