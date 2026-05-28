# Task 003-v3-11a: delete legacy-shape `main()` tests (pre-subparser cleanup)

## Meta

- **Bead ID**: `task-003-v3-11a-delete-legacy-main-tests`
- **Slug**: `delete-legacy-main-tests`
- **Maps to**: Issue **I-V3.6** (sub-bead — pre-subparser hygiene).
- **Depends on**: none (this is the **first** bead of Phase -1; blocks 003-v3-00).
- **Estimated time**: 0.25 day
- **Priority**: Critical (blocks 003-v3-00 — without this bead the suite goes red on 003-v3-00 commit).

## Use Case Connection

- **UC-08 v3.1 prep**: removes test surface that exercises the v2 `main(argv)` legacy CLI shape (`--vault X --source-page Y` with NO subcommand). After 003-v3-00 lands `add_subparsers(dest="cmd", required=True)`, these tests would fail at argparse parsing before reaching their actual assertions. Pre-removing them keeps `pytest tests/ -q` green throughout the 003-v3-00..003-v3-05 window.
- **Regression preservation**: every behavioural assertion in the deleted tests is migrated to a TODO marker referencing the future Phase-1 bead that re-asserts it via the new `prepare`/`apply` surface.

## Task Goal

Delete the **6 tests** in `tests/test_wiki_extract_concepts.py` that invoke `wec.main([... legacy args ...])` without a subcommand. Insert TODO-comment markers tying each deletion to a future regression-preservation test in 003-v3-01 / 003-v3-03.

### Tests to delete (verified against current file state)

| # | Line | Test name | Reason for deletion | Regression preserved in |
|---|---|---|---|---|
| 1 | 36 | `test_argparse_help_text_contains_ingest_flag` | Asserts top-level `--help` mentions `--ingest`/`--vault`/`--source-page` flags — under v3.1 these live under `apply` subparser, top-level help shows only `{prepare,apply}` choices. | 003-v3-00 adds `test_argparse_top_level_help_shows_subcommands` |
| 2 | 458 | `test_main_rejects_absolute_source_page_path` (H-1) | Calls `main(["--vault", "trade-agents", "--vault-root", ..., "--source-page", "/etc/passwd", "--db-path", ...])` without subcommand → argparse SystemExit before reaching INVALID_SOURCE_PATH branch. | 003-v3-01 adds `test_prepare_rejects_absolute_source_page_path` (H-1 migration) |
| 3 | 486 | `test_main_rejects_invalid_source_slug` (H-3) | Same shape — H-3 invalid-slug fired before any subcommand exists. | 003-v3-01 adds `test_prepare_rejects_invalid_source_slug` (H-3 migration) |
| 4 | 522 | `test_main_ingest_partial_failure_does_not_update_source_state` (C-1) | Calls main with legacy shape AND mocks `anthropic.Anthropic` — would have been deleted in original 003-v3-11 anyway, but moved here so it doesn't go red between 003-v3-00 and 003-v3-11. | 003-v3-03 adds `test_apply_ingest_partial_failure_does_not_update_source_state` (C-1 migration) |
| 5 | 1071 | `test_main_with_ingest_calls_dispatch_and_emits_combined` | End-to-end --ingest via legacy main + anthropic mock — same situation as #4; moved from 003-v3-11 scope. | 003-v3-03 adds `test_apply_with_ingest_emits_combined_envelope` |
| 6 | 1140 | `test_main_without_ingest_emits_manifest_only` | Same situation as #4/#5 — moved from 003-v3-11 scope. | 003-v3-03 adds `test_apply_without_ingest_emits_manifest_only` |

### Test that SURVIVES (do NOT delete)

- Line 28 `test_argparse_missing_vault_returns_exit` — calls `wec.main([])`. Under v3.1, `main([])` still triggers argparse SystemExit(2) (now for missing required subcommand instead of missing `--vault`). The mechanical assertion (`ei.value.code == 2`) remains valid. The test name becomes slightly misleading but is harmless. **Rename in 003-v3-00 Step 1 to `test_argparse_no_args_returns_exit_2`** (mechanical rename, no behaviour change).

## Stub-First Plan

n/a — test deletion is the deliverable. No Phase-1 / Phase-2 split.

## Changes Description

### Edited files

- `tests/test_wiki_extract_concepts.py`:
  - Delete the 6 tests catalogued above (function body + decorator + blank-line padding).
  - Insert TODO-comment markers at each deletion site, format:
    ```python
    # DELETED in 003-v3-11a (Option A green-throughout invariant).
    # Regression intent: [H-1 / H-3 / C-1 / help-text / ingest-e2e / no-ingest-manifest]
    # Migrated to: [task-003-v3-NN test name]
    ```
  - Remove any now-orphaned imports / helpers if the file lints clean. (`mock`, `json`, etc. likely still used — check before removing.)

## Component Integration

- **No production code touched** — pure test file edit.
- **Patch-target lock invariant (R-1)** carried forward — the 3 anthropic-mock tests being deleted (#4, #5, #6) used `mock.patch("anthropic.Anthropic")` and `mock.patch("scripts.wiki_skills.wiki_extract_concepts.dispatch_to_indexer", ...)`. Removing them does NOT violate R-1; future tests added in 003-v3-03 must still respect the lock.

## Files Touched

- `tests/test_wiki_extract_concepts.py` (only)

## Acceptance Criteria

- [ ] **Test count**: `pytest --collect-only -q tests/test_wiki_extract_concepts.py` reports exactly 51 items (was 57; − 6 = 51).
- [ ] **Suite green**: `pytest tests/ -q` → 390 passed (was 396; − 6 = 390), 0 failed. (Skips unchanged; ignore `+ N skipped` suffix.)
- [ ] **mypy --strict**: `mypy --strict scripts/` clean (no production code touched, expected to pass).
- [ ] **Grep audit**: `grep -n "wec\.main(\[" tests/test_wiki_extract_concepts.py` returns exactly **1** match — only the surviving line-28 `test_argparse_missing_vault_returns_exit` (renamed in 003-v3-00).
- [ ] **TODO markers present**: `grep -c "DELETED in 003-v3-11a" tests/test_wiki_extract_concepts.py` returns **6**.
- [ ] **No orphaned imports** (`python -m pyflakes tests/test_wiki_extract_concepts.py` reports no `F401`).

## Dependencies

- **Blocks**: 003-v3-00 (argparse subparser scaffold). The dependency relationship is: 11a MUST land before 00 because 00's argparse change breaks the 6 tests this bead removes.
- **Depends on**: none.

## Notes

- This bead is the **Option A green-throughout invariant fix** identified by adversarial review on 2026-05-28. The alternative (Option B: temporary compat shim inside 003-v3-00) was rejected as architectural impurity — it would leave Decision-17 ("skill is deterministic, no embedded LLM call, BREAKING CHANGE for legacy invocation") half-applied for 6 beads.
- Regression intent for the deleted H-1/H-3/C-1 tests is **non-negotiable** — Phase-1 beads 003-v3-01 (prepare) and 003-v3-03 (apply) MUST re-assert these via the new subcommand surface. The TODO markers in the test file are the operator's checklist.
- This bead is the only Phase -1 bead. After it lands, work resumes at 003-v3-00 per the original DAG.
