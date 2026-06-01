# task-015-00 — No-regression anchor

**Parent:** TASK 015. **Depends on:** none. **RTM:** R-015-NF3.

## Goal
Establish a green baseline before any code changes. Create the task-015 test file
and confirm current pytest + mypy counts so every subsequent bead stays green-throughout.

## Steps

1. Create `tests/test_perf_hardening.py` with one smoke import test:
   ```python
   from scripts.wiki_skills.wiki_index_upsert import main  # noqa: F401

   def test_smoke_import() -> None:
       assert callable(main)
   ```

2. Run the baseline:
   ```bash
   source .venv/bin/activate
   pytest -q 2>&1 | tail -3
   mypy --strict scripts/ | tail -3
   ```
   Confirm: pytest ≥ 852 passed (+4 skip), mypy 0 errors. Record counts.

## Acceptance
- ✅ `tests/test_perf_hardening.py` exists; 1 test passes.
- ✅ Full pytest suite ≥ 852 passing; no unexpected failures.
- ✅ `mypy --strict scripts/` — 0 errors.

## Files
- `tests/test_perf_hardening.py` (create)
