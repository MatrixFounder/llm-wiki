# Task 003-v3-16: regression sweep + mypy + patch-target lock verification (ACCEPTANCE GATE)

## Meta

- **Bead ID**: `task-003-v3-16-regression-sweep`
- **Slug**: `regression-sweep`
- **Maps to**: Issue **I-V3.11**; RTM row **R-43**; H-3 (test count math).
- **Depends on**: all prior task-003-v3-00..task-003-v3-15.
- **Estimated time**: 0.25 day
- **Priority**: Critical (final acceptance gate).

## Use Case Connection

- Closes the v3.1 task. After this bead, the task can ship.

## Task Goal

1. **Pytest sweep**: `pytest tests/ -q` → assert at least **436 passed, 0 failed** (Option A target — see PLAN.md §2 suite-size table).
2. **Mypy strict**: `mypy --strict scripts/` → assert "Success: no issues found".
3. **Help-routing smoke**:
   - `bin/wiki-extract-concepts prepare --help | grep -q "source-page"`.
   - `bin/wiki-extract-concepts apply --help | grep -q "source-hash"`.
   - `bin/wiki-extract-concepts --help | grep -qE "prepare|apply"`.
4. **Patch-target lock invariant (Risk R-1)**: `grep -rn "patch.*_manifest_consumer\.\(index_from_manifest\|validate_manifest\|WikiIngestError\)" tests/` → **0 matches**.
5. **Mid-refactor invariant retrospective (Option A)**: verify (by reading git log + the bead acceptance histories) that no individual bead's verification step recorded < 390 passing tests. The floor **390** holds between every bead boundary (lowered from the originally-claimed 396 because Phase -1 bead 003-v3-11a removes 6 legacy-shape tests pre-emptively — see PLAN.md §6 R-2 for rationale). After 003-v3-00 lands the suite returns to ≥ 396 and monotonically grows to the ~436 final.
6. **Retire SDK-metadata deep-sweep deferred item from `docs/KNOWN_ISSUES.md`** (moot post-v3 — no SDK in scope).
7. **Anthropic-free invariant**:
   - `grep -ni "anthropic" scripts/` → 0 matches.
   - `grep -ni "anthropic" tests/` → 0 matches.
   - `grep anthropic requirements.txt` → 0 matches.

## Stub-First Plan

n/a (verification only).

## Changes Description

### Edited files

- `docs/KNOWN_ISSUES.md`: retire SDK-metadata deep-sweep entry (if it exists).

## Files Touched

- `docs/KNOWN_ISSUES.md` (housekeeping edit)

## Acceptance Criteria

- [ ] **R-43**: `pytest tests/ -q` → ≥ 436 passed, 0 failed (Option A target; baseline 396 − 15 deleted + 55 added).
- [ ] **R-43**: `mypy --strict scripts/` → no issues.
- [ ] Three subcommand help routes work.
- [ ] **R-1 (patch-target lock)**: grep returns 0 matches.
- [ ] **Anthropic-free**: 3 separate greps all return 0 matches.
- [ ] **Mid-refactor invariant (Option A)**: retrospective confirms ≥ 390 floor between all bead boundaries (was originally ≥ 396 pre-Option-A, but 11a temporarily dropped to 390 to enable green-throughout under 003-v3-00's argparse change).

## Verification

```bash
source .venv/bin/activate

# Full sweep
pytest tests/ -q
# expect: ≥ 436 passed

# Mypy
mypy --strict scripts/

# Help routing
bin/wiki-extract-concepts prepare --help | grep -q "source-page" && echo "OK: prepare help"
bin/wiki-extract-concepts apply --help | grep -q "source-hash" && echo "OK: apply help"
bin/wiki-extract-concepts --help 2>&1 | grep -qE "prepare|apply" && echo "OK: top-level help"

# Patch-target lock
grep -rn "patch.*_manifest_consumer\.\(index_from_manifest\|validate_manifest\|WikiIngestError\)" tests/
# expect: empty

# Anthropic-free invariants
grep -rni "anthropic" scripts/ && echo "FAIL: scripts/ refs" || echo "OK: scripts/"
grep -rni "anthropic" tests/ && echo "FAIL: tests/ refs" || echo "OK: tests/"
grep -i "anthropic" requirements.txt && echo "FAIL: dep refs" || echo "OK: requirements.txt"
```

## Rollback

n/a (verification step; no rollback meaningful unless the gate fails — at which point the upstream bead causing the failure is the one to rollback).

## Notes

- This bead is the explicit acceptance gate. After all checks pass, the task is "Done" per PLAN.md §7.
- If pytest returns < 436, identify which bead's acceptance step let the regression through; rollback + re-do that bead.
- If mypy fails, the offending file is logged; identify the source bead and re-do.
- The mid-refactor invariant (Option A: ≥ 390 floor between boundaries) is a retrospective check — the per-bead acceptance steps already enforce it, but this is the final audit.
