# Task 012-12: R-X3 dogfood — migrate this repo's KNOWN_ISSUES.md (joins 012-09 + 10 + 11)

> **`skill-tdd-strict`** (acceptance of the whole KNOWN_ISSUES bundle). Joins the render path
> (012-09), the lint guard (012-10), and the splitter (012-11) — see PLAN §2 DAG.

## Use Case Connection
- UC-32: this repo's `docs/KNOWN_ISSUES.md` (743 lines) → per-file Class-A `docs/issues/*.md`
  + Class-B auto-rendered ledger; `wiki-search "hash drift"` returns one issue.

## Task Goal
Run the splitter (012-11) on this repo as the first real dogfood, regenerate the ledger via
PW-H (012-09), let the operator review the `.migration-report.md`, and verify the
rebuildability + typed-search acceptance. This is where the §D8 Class-A/B reclassification
actually lands for `obsidian-llm-wiki`.

## Changes Description

### Operator-run migration (produces committed Class-A files)
1. `python scripts/migrate_known_issues_to_files.py --vault-root .` → `docs/issues/<id>-<slug>.md`
   (Class A) + `docs/issues/.migration-report.md`.
2. **Operator + agent review** `.migration-report.md`; fix flagged issues by hand in the
   per-issue files; re-run / re-render.
3. `wiki-index-render --auto-indexes` (after this repo is a dev-vault — 012-14) regenerates
   `docs/KNOWN_ISSUES.md` (now Class B, GENERATED-AT header + sha256 in `.wiki/state.json`).
4. Operator approves; commit `docs/issues/*.md` + the regenerated ledger together.

> **Ordering note:** 012-12 depends on this repo being indexable as a dev-vault. The `wiki-search`
> acceptance (step below) runs after 012-14 (Phase A bootstrap). The split + render can be
> validated on a temp copy first (test), with the real on-disk migration committed alongside 012-14.

### Changes in Test Files
#### File: `tests/test_known_issues_dogfood.py` (NEW, tdd-strict)
- On a COPY of the real `docs/KNOWN_ISSUES.md`: split → render → assert byte-identical to the
  original modulo whitespace + GENERATED-AT (the real-data round-trip, not just the fixture).
- Assert every `## [date] <title> [STATUS]` issue in the original maps to exactly one
  `docs/issues/*.md` (count parity); no issue dropped.

## Acceptance Criteria
- ✅ Real `KNOWN_ISSUES.md` round-trips (delete + `--auto-indexes` byte-identical modulo GENERATED-AT).
- ✅ `wiki-search "hash drift" --vaults obsidian-llm-wiki` returns ONE
  specific issue, not the whole ledger (verified post-012-14).
- ✅ `wiki-lint` flags a hand-edit of the regenerated ledger (012-10).
- ✅ `.migration-report.md` reviewed; no silent data loss.

## Stub-First (`skill-tdd-strict`)
Test-first on a temp copy (real-data round-trip) before the on-disk migration is committed.
The on-disk `docs/issues/*.md` are the Class-A deliverable; the ledger becomes Class B.
