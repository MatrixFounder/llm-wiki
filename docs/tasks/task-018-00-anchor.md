# task-018-00 — Anchor + test module

**Parent:** TASK 018. **Depends on:** none. **RTM:** AC-9 (baseline).

## Goal
Establish a no-regression baseline and the new test module before any wiki-sync code.

## Steps
1. Confirm baseline green on branch `task-018-wiki-sync`: `pytest -q` (≥ 909 +4 skipped) +
   `mypy --strict scripts/`.
2. Create `tests/test_wiki_sync.py` with a module docstring and a single placeholder test
   `test_anchor_collects()` (`assert True`) so the file collects.

## Verification
- `pytest -q tests/test_wiki_sync.py` → 1 passed; full suite unchanged; `mypy --strict` clean.
