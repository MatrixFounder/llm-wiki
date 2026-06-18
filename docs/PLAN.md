# PLAN 040 — config-driven write-grammar (collapse the Karpathy/PARA forks)

Behaviour-preserving refactor (ADR-007). Green throughout; `mypy --strict`; zero-DDL; zero deps;
no `import anthropic`. **Karpathy byte-identity is the gate** — every step keeps karpathy output
byte-identical (the YAML value reproduces the old constant). Additive YAML keys, legacy defaults.

## Atomic checklist (stub-first per step; Red→Green; golden-gated)

- **S0 — Branch + GOLDEN CAPTURE (do FIRST).** Branch `task-040-…`. Build a `samples/` karpathy
  fixture; capture the CURRENT (pre-refactor) outputs as a golden: extract-concepts `prepare`+`apply`
  written files/manifest + wiki-import note path/filename + wiki-init scaffold tree + `wiki-reindex
  --full` page rows. This WRITE-side capture is the byte-identity baseline (the existing
  `tests/test_karpathy_byte_identity.py` pins only the READ side — discover/reindex — so nothing
  else guards the write side); asserted unchanged after S2-S4. *Gate:* golden captured.
- **S1 — `write:` block in LayoutConfig + schema + YAMLs (R-1).** Add `WriteGrammar`
  (`source_subdir: str=""`, `source_filename: str="title"` dataclass defaults) to `LayoutConfig`;
  parse the optional `write:` map; `config/layout-config.schema.yaml` += the block; built-ins:
  `karpathy.yaml` (`source_subdir: _sources`, `source_filename: slug`),
  `obsidian-personal`/`dev-project`/`cybos` (`source_subdir: ""`, `source_filename: title`).
  Default semantics (mirror TASK 031 `aliases`/`init_scaffold`): each BUILT-IN YAML declares its `write:`
  block explicitly (karpathy `_sources`/`slug`; PARA-family `""`/`title`); an absent `write:` in a per-vault
  OVERRIDE deep-merges OVER the built-in base (which DOES declare it); the dataclass/schema default (`""`/`title`,
  = PARA-legacy) fires ONLY for a YAML that omits the block entirely. Also EXTEND/verify
  `test_karpathy_config_matches_layout_constants` for the new (write-only, indexer-ignored) keys.
  Tests: parse + per-layout values + omitted-block default + the projection invariant. *Gate:* S1 green.
- **S2 — extract-concepts reads config (R-2, R-5).** repoint ALL `SOURCES_SUBDIR` uses in `_resolve_source_inside_sources` to `layout.write.source_subdir`
  (resolve once per call, thread it): the vault-tier lookup `vault_root/SOURCES_SUBDIR/<slug>.md` (L163), the
  course-tier glob `*/SOURCES_SUBDIR/<slug>.md` (L170), AND the `parent.name == SOURCES_SUBDIR` concepts-anchor
  check (L207 + `__init__.py` `_apply_write` L805). When `source_subdir == ""` (PARA): gate the WHOLE slug-form
  search block (vault-tier + course-tier) off (Q-040-2) so PARA goes straight to the verbatim-path branch and the
  parent.name check (never `== ""`) yields sibling `_concepts/`. **Assert the S0 karpathy golden byte-identical**;
  add a PARA case. *Gate:* golden + tests green.
- **S3 — wiki-import reads config (R-3).** `_note_dir` = `folder / source_subdir`; filename per
  `source_filename` (`slug`→`_MINT_SLUG` mint+validate; `title`→`fname_sanitize`). Delete the
  `resolve_alias(...)=="karpathy"` + `is_karpathy` branches. Tests: both layouts (the TASK 039 apply
  tests still pass, now config-driven). *Gate:* S3 green.
- **S4 — wiki-init audit (R-4) — DESCOPED to verify+comment.** Confirmed: wiki-init is ALREADY
  config-driven (`is_two_tier_scaffold`, TASK 031) and is NOT a layout-NAME fork (the grep fork-guard
  does not flag it). `SCAFFOLD_DIRS` is the gated two-tier-scaffold page-subdir SET (a constant for
  *which* dirs a two-tier scaffold creates), not a Karpathy/PARA branch — touching it risks init for no
  fork-removal gain. Action: add an audit comment only (no behaviour change). *Gate:* existing init tests green.
- **S5 — fork-guard + drop-in proof (R-2/NF-2 + DoD 1,4).** `grep -rE
  "parent\.name *== *SOURCES_SUBDIR|resolve_alias\([^)]*\) *== *.karpathy" scripts/wiki_skills/` → empty.
  A NEW throwaway layout YAML (`source_subdir`/`source_filename` set) placed UNDER `samples/` or a tmp dir (NOT
  `layouts/` — `_builtin_registry()` globs+caches it and raises on stem/alias shadow), pointed at via a test vault's
  `layout_config:`, files correctly with ZERO Python edit; clean up after.
- **S6 — e2e BOTH layouts + gates (DoD 2,3).** Re-run the TASK 039 e2e (PARA meeting transcript +
  Karpathy article) — both reproduce identically; `wiki-reindex --full` collisions==0; diff the karpathy
  vault vs the S0 golden = empty. `mypy --strict scripts/`; full `pytest`; `grep import anthropic` empty.
- **S7 — VDD.** self-improvement-verificator on this plan (design-time); after S6, `/vdd-multi`
  (code-reviewer + critic-security + critic-logic) → fix → re-green. Commit on user request.

## Invariants / guards
- **Byte-identity (R-5):** karpathy is a golden anchor — the refactor is a pure constant→config
  substitution where `karpathy.write.source_subdir == SOURCES_SUBDIR`. S0 captures, S2–S6 assert unchanged.
- **NF-2:** ONE parameterized write path; no construct skill branches on a layout name. The grep-guard (S5) enforces it.
- **Decision-17 / zero-DDL (`user_version` 7, this is layout config) / mypy --strict** throughout.
- **Rollback:** isolated branch; additive YAML keys + constant→config substitution → revert = drop the
  branch; no DB migration (Class-B rebuild only if needed).

## Out of plan
- External `wiki_ingest` (Karpathy-by-design); `wiki-enrich` retirement; any read-side grammar change; DDL.
