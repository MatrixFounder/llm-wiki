# Task 019.00: Anchor + back-compat byte-identity lock

## Use Case Connection
- UC-5 (back-compat) · AC-7

## Task Goal
Establish a green baseline + the new test module, and **lock byte-identity**: with no
`resummarize:` block, `wiki_sync._build_entries` must produce a plan identical to the
TASK 018 output. This regression-locks AC-7 BEFORE any code changes.

## Changes Description
### New Files
- `tests/test_wiki_sync_resummarize.py` — TASK 019 test module.

### Changes in Existing Files
- none (anchor bead).

## Test Cases
### Regression / Anchor
1. **TC-00-1:** `pytest -q` + `mypy --strict scripts/` green (baseline, 986+ tests).
2. **TC-00-2 (byte-identity):** build a tmp fixture vault (a small zone with a `.txt` raw
   + a ready `.md`) with **no** `.wiki/sync.yaml` `resummarize:`; assert `_build_entries(...)`
   returns the same entries (action/reason/order) it does today. Snapshot/golden compare.

## Acceptance Criteria
- [ ] New test module collects + runs green.
- [ ] Byte-identity golden test passes (current behavior captured).
- [ ] `mypy --strict` clean.

## Notes
The golden becomes the AC-7 guard for every later bead — re-run it after 02/06/07.
