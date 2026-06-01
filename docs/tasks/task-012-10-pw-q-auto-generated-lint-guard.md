# Task 012-10: PW-Q — `wiki-lint` auto-generated lint guard

## Use Case Connection
- UC-32: a manual edit of the auto-rendered `docs/KNOWN_ISSUES.md` is flagged by `wiki-lint`
  ("edit the per-issue file, not the ledger").

## Task Goal
Add a lint check that detects drift between an `auto_indexes[].output` file on disk and what
the renderer would produce — so a hand-edit of the generated ledger surfaces instead of being
silently overwritten on the next render (PW-Q). Folded into existing `wiki-lint` (no new CLI).

## Changes Description

### Changes in Existing Files

#### File: `scripts/wiki_index/lint.py`
- `check_auto_generated_unchanged(repo, vault_id, config, vault_root) -> list[LintIssue]`:
  for each `config.auto_indexes[].output`, re-render to a temp buffer (reuse
  `rendering.render_auto_index`), compute `sha256(header-stripped body)`, compare against the
  `.wiki/state.json` value AND against the on-disk file's header-stripped sha256. On mismatch
  → `LintIssue(category="auto-generated-drift", severity="warning", details={path, hint})`
  with the remediation hint ("manual edit detected at `<path>`; run
  `wiki-index-render --auto-indexes` to regenerate, or move your edit into the per-issue file").
- Wire it into `run_all_checks` (only when the vault's layout has `auto_indexes[]`; skip
  silently for Karpathy/layouts without auto-indexes).

### Changes in Test Files
#### File: `tests/test_lint_auto_generated.py` (NEW)
- Render a ledger; hand-edit the on-disk output (add a stray line) → `wiki-lint` reports
  `auto-generated-drift` with the hint; `--strict` exits non-zero.
- An untouched (freshly-rendered) ledger → no drift issue.
- A vault with no `auto_indexes[]` (Karpathy) → the check is a silent no-op (no false positive).
- The GENERATED-AT header line alone differing (timestamp) → NOT flagged (header-stripped compare).

## Acceptance Criteria
- ✅ Hand-edit flagged with a clear remediation hint; clean ledger passes; no-auto-index vaults skip.
- ✅ Header-only (timestamp) difference is not a false positive.
- ✅ `mypy --strict` clean; suite green.

## Stub-First
Phase 1: `check_auto_generated_unchanged` returns `[]`. Phase 2: re-render + sha256 compare +
the drift `LintIssue` + wiring (RED-first on the hand-edit detection).
