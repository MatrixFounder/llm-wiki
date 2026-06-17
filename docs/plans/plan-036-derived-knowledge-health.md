# PLAN 036 — Derived knowledge health: lifecycle-drift + coverage (R-15, Track A)

Green-throughout. Read-side only; **zero DDL** (`user_version` stays 7). The DAL SQL mirrors
the proven TASK-034 `--as-of` `NOT EXISTS` walk; all rule values are bound params. Status:
✅ COMPLETE — every bead landed, `/vdd-multi` converged (3 logic + 2 perf fixes folded in),
1524 pytest / mypy strict.

## Beads

- **036-00 — models + schema (grammar).** ✅ `DriftRule`/`CoverageRule`/`DriftHit`/`CoverageGap`
  frozen dataclasses in `models.py` (one definition site → no import cycle). New strict
  `DriftRule`/`CoverageRule` `$defs` (+ `oneOf` exactly-one-of) and the `drift_rules`/
  `coverage_rules` array properties (default `[]`) in `config/layout-config.schema.yaml`.
- **036-01 — layout engine.** ✅ `LayoutConfig` gains the two rule tuples; `_build` constructs
  them; `_validate_health_rules` (called from `load_layout_config`) validates edge vocabulary
  (`reindex._INVERSE_REF_TYPE`, lazy import), field allow-list, non-empty status, exactly-one-of.
- **036-02 — DAL.** ✅ `find_lifecycle_drift` / `find_coverage_gaps` abstract (ABC) + SQLite
  impl: keyed on `$.type`; drift = `json_type='text'` + `<>`/`IN`; coverage = `NOT EXISTS` edge
  OR `$.field` NULL/`''`/`'[]'`/`'{}'`. COUNT-guard-free (page-side unambiguous). Bound params.
- **036-03 — A1 wiring.** ✅ `check_lifecycle_drift` + `lifecycle-drift` `LintIssue` in
  `run_all_checks` (severity warning → error under `--strict`); layout resolved ONCE per vault
  and shared with `check_auto_generated_unchanged`.
- **036-04 — A2 CLI.** ✅ `scripts/wiki_skills/wiki_health.py` (`coverage` subcommand, always
  exit 0, `--class` filter, INVALID_CLASS=2 / VAULT_NOT_FOUND=6, no-rules note) + `bin/wiki-health`.
- **036-05 — cybos rules.** ✅ 3 `drift_rules` + 3 `coverage_rules` in `layouts/cybos.yaml`
  (template-grounded edge semantics).
- **036-06 — tests.** ✅ `tests/_health_fixtures.py` (+ generic `build_cybos_vault`) +
  `test_lifecycle_drift.py` / `test_wiki_health.py` / `test_health_rules_config.py` (20 tests:
  DAL, lint integration, `--strict` gate, CLI, config parse/validate, the 5 hardening cases,
  EXPLAIN index guard).
- **036-07 — VDD + dogfood + docs.** ✅ `/vdd-multi` (3 critics) converged with fixes folded in;
  live dogfood on a real cybos vault; ADR-006, ROADMAP R-15 → SHIPPED, CLAUDE.md (17 CLIs),
  ARCHITECTURE Q-036, README, `commands/wiki-health.md` + `skills/wiki-health/SKILL.md` + symlinks.

## Verification (run from repo root, venv active)
- `pytest tests/test_lifecycle_drift.py tests/test_wiki_health.py tests/test_health_rules_config.py`
- `pytest tests/` (full regression) + `mypy --strict scripts/`
- Dogfood: scaffold a cybos vault with a superseded-but-`accepted` decision + a sourceless fact →
  `bin/wiki-lint --strict` exits 1 (lifecycle-drift); `bin/wiki-health coverage` lists the gaps, exit 0.
- Rebuildability: `wiki-reindex --full` stays green; `user_version` unchanged at 7.
