# task-017-12 — Benchmark evidence + full regression

**Parent:** TASK 017. **Depends on:** 017-08, 017-11. **RTM:** R-017-4d, NF7, AC-017-5.

## Goal
Prove the P-2/P-3 wins with measured `scripts/benchmark.py` deltas (P-5 lesson: no blind
changes) and confirm the full gate.

## Steps
1. Run `scripts/benchmark.py --n 1000` for `reindex-delta` (no-op) and `wiki-lint`
   **before** (stash/checkout baseline) vs **after** this branch; also `--n 10000` if the
   synthetic-vault generation is feasible in reasonable time.
2. For `wiki-lint`, capture both default and `--mtime-skip` numbers (the opt-in is where the
   order-of-magnitude no-op win lands; default-mode gain is the YAML-parse removal only — be
   honest in the writeup).
3. Record the table in `docs/TASK.md` status block (n=1000 delta + lint ms, before→after).
4. Confirm full gate: `pytest -q` (≥ 879 + the new R-017 tests) + `mypy --strict scripts/`
   clean + `tests/test_karpathy_byte_identity.py` green + `python -m` smoke for the touched
   CLIs.

## Verification
- Benchmark numbers present in TASK status; `user_version` still 5 (`PRAGMA user_version`
  on a built sample DB); all gates green.
