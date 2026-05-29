# Task 008-11: regression sweep + docs (the acceptance gate)

## Use Case Connection
- All RTM (R-8.1..R-8.10 + R-8.5e + AM-3 + C-8/NFR-7); the task-level Definition of Done (PLAN §7).

## Task Goal
Close TASK 008: full green regression + type-check, ship-state docs, ROADMAP/ARCHITECTURE status flips, and the envelope-never-echoes-content regression extension. This is the final acceptance gate — nothing merges until every box is ticked.

## Changes Description

### Verification (run + assert)
- `pytest tests/ -q` → all green (baseline ≈599 post-TASK-007 + the new TASK 008 cases), 0 failed.
- `mypy --strict scripts/` → Success.
- `bin/wiki-verify-multi --help` exits 0; the `.claude/`/`.agent/` symlinks resolve.
- `PRAGMA user_version == 5`; a fresh scaffold + `wiki-reindex --full` over a tmp vault with a verdict page is clean (0 errors).
- **`wiki-query` behaviour unchanged** — a regression test confirms `wiki-query apply` does NOT invoke `wiki-verify-multi` (R-8 is off-by-default, R-8.10).
- **Grep guard** (from 008-05/10) green — no `PAGE_SUBDIRS` literal in `wiki_verify_multi.py`.

### New / extended Tests

#### File: `tests/test_verify_envelope_safety.py` (NEW, or extend the existing envelope-safety suite)
- Parametrized: every `wiki-verify-multi` error envelope (`QUERY_NOT_FOUND`, `NO_SOURCES`, `ANSWER_CHANGED`, `INVALID_VERDICT`, `VERDICT_PARSE_ERROR`, `VERDICT_TOO_LARGE`, `FINDING_SOURCE_NOT_EXAMINED`, `INVALID_VERIFICATION_PAGE`, `INVALID_ANSWER_HASH`, `INVALID_SLUG`) carries `{error, field?, reason}` only and **never echoes** the offending answer/source/finding/verdict content (CWE-117/209). Feed adversarial payloads (a finding `note` containing `\n`, control chars, a fake `error:` line) and assert they don't appear in the envelope.

### Doc Updates (Class A)
- **`docs/ROADMAP.md`**: R-8 → **DONE 2026-05-29 (TASK 008)** with a one-paragraph ship summary (verdict page, 4 prose critics, FAIL=exit6/no-mutation, schema v4→v5, R-8.5e durability, layout-agnostic); note R-7 (`wiki-research`) stays independent. Fix the stale intro if it omits TASK 007/008.
- **`docs/ARCHITECTURE.md`** (index): status header `TASK 008 … IN DESIGN` → **SHIPPED** (mirror the TASK 007 SHIPPED block: bead count, gate count, pytest count, schema v5).
- **`README.md`**: add `wiki-verify-multi` to the CLI list + a one-line description.
- **`CLAUDE.md`**: add `wiki-verify-multi` / `wiki-verify` to the CLIs paragraph; bump the status line (TASK 008 shipped, schema v4→v5); add the task/plan/review pointers.
- **`skills/.AGENTS.md`**: note `wiki-verify` (SECURITY-SENSITIVE — SECURITY-label PR rule) alongside `concept-extraction`/`wiki-query-synthesis`.
- **`tests/.AGENTS.md`**: add the TASK 008 test surface (the new test files).
- **`scripts/wiki_skills/.AGENTS.md`** + **`scripts/wiki_index/.AGENTS.md`**: note `wiki_verify_multi.py`, the `check/record_verify_state` DAL, and the `_frontmatter_refs` generalisation.
- **`docs/KNOWN_ISSUES.md`**: record any deferred TASK 008 findings (the `/vdd-multi` round, if run post-plan) + a dogfood section placeholder.

## Test Cases

### Regression / acceptance Tests
1. **TC-GATE-01:** full `pytest` green; `mypy --strict` clean.
2. **TC-GATE-02:** envelope-safety parametrized suite green (no content echo).
3. **TC-GATE-03:** `wiki-query` regression — `wiki-query apply` does not call `wiki-verify-multi` (off-by-default).
4. **TC-GATE-04:** `user_version == 5`; scaffold + reindex over a verdict-page vault → 0 errors.

## Acceptance Criteria
- [ ] All PLAN §7 Definition-of-Done boxes ticked.
- [ ] Envelope-never-echoes-content regression extended to the `wiki-verify-multi` surfaces.
- [ ] ROADMAP R-8 → DONE; ARCHITECTURE status → SHIPPED; README/CLAUDE.md/.AGENTS.md updated.
- [ ] `wiki-query` behaviour unchanged (off-by-default verified); grep guard green.
- [ ] Full `pytest` green; `mypy --strict` clean.

## Notes
No new feature logic — verification + docs + the envelope regression. Depends on **all** prior beads (008-01..008-10). This bead gates the merge; if a `/vdd-multi` adversarial sweep is run after planning, its must-fix items land before this gate closes (their LOW/deferred items go to KNOWN_ISSUES).
