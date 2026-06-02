---
id: DF-017-1
type: known-issue
status: fixed
opened_at: 2026-06-02
category: quality
severity: SEV-3
slug: df-017-1-check-drift-type-mismatch-not-layout-mapping-aware
---

# check_drift type-mismatch is not layout-type-mapping-aware (false positives on non-karpathy layouts)

- **Symptom**: `wiki-lint` reports spurious `type-mismatch` drift on vaults using a
  non-karpathy layout whose `type_mapping` has entries beyond the three karpathy ones.
  On **this repo's own `dev-project` docs vault** (`wiki-reindex --full` + `wiki-lint`,
  TASK 017 dogfood 2026-06-02): **56 false `type-mismatch`** — every `docs/issues/*.md`
  declares frontmatter `type: known-issue`, the `dev-project` layout maps it to
  `db_type: research` (`scripts/wiki_index/layouts/dev-project.yaml` `type_mapping`),
  and `check_drift` flags `known-issue` ≠ `research` as drift.
- **Root cause**: `SQLiteRepository._is_intentional_mapping` carries a **hardcoded
  3-entry table** (`lesson-summary`/`summary-light`/`meeting-summary` → `summary`) and
  does **not** consult the config-driven layout's `type_mapping` (introduced TASK 012 /
  R-X1). Any raw `type:` the layout legitimately maps to a different `db_type` looks like
  drift. Karpathy vaults are unaffected (their `type:` already equals the `db_type`).
- **Affected components**: `scripts/wiki_index/sqlite_repository.py`
  (`check_drift` → `_is_intentional_mapping`).
- **NOT caused by TASK 017** (recorded for provenance): TASK 017's P-3 change altered only
  type *extraction* (`_extract_frontmatter_type`: PyYAML → regex fast-path) and the *walk*
  (`discover_pages` → equivalent `iter_pages`); `git diff` shows **zero** change to
  `_is_intentional_mapping` or the type-mismatch comparison, and the new fast-path was
  verified **byte-identical to PyYAML on all 331 real docs files** (0 disagreements). This is
  a pre-existing gap that predates the config-driven layout engine and was surfaced by the
  TASK 017 dogfood. (Side note: `wiki-lint --mtime-skip` masks it — an unchanged file is
  skipped before the type check — so the false positives only show in the default full-hash mode.)
- **Fix plan**: thread the resolved layout `type_mapping` into the comparison. `check_drift`
  **already resolves** `LayoutConfig` (since the TASK 017 `iter_pages` walk), so the mapping
  is in hand — pass `config.type_mapping` to `_is_intentional_mapping` and treat
  `config.type_mapping.get(file_type).db_type == db_type` (optionally also the tag marker) as
  NOT drift, unioned with the existing hardcoded karpathy entries (back-compat). ~SEV-3:
  false-positive lint noise on dev-project/obsidian-personal vaults; no data loss; default
  karpathy unaffected.
- **Prevention**: a per-built-in-layout fixture-vault lint smoke (assert `type-mismatch == 0`
  on a freshly-reindexed dev-project/obsidian-personal vault) would catch type-mapping drift-noise.
- **Resolution (2026-06-02, same-session dogfood fix)**: `_is_intentional_mapping` now unions the
  resolved layout `config.type_mapping` (passed from `check_drift`, which already resolves it for
  the P-2 walk) with the karpathy defaults, keeping the marker-tag disambiguation (null-marker →
  db_type match suffices). Verified end-to-end: the repo's docs-vault `wiki-lint` type-mismatch
  dropped **56 → 0**. Regression test `test_is_intentional_mapping_layout_aware`.
