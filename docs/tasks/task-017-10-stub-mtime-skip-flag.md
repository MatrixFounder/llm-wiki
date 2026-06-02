# task-017-10 — [STUB] `--mtime-skip` flag + `trust_mtime` param threaded

**Parent:** TASK 017. **Depends on:** 017-00. **RTM:** R-017-2c (partial), Q-017-3.

## Goal
Add the opt-in `wiki-lint --mtime-skip` CLI flag (default OFF) and thread a `trust_mtime`
parameter all the way to `check_drift` — accepted but **ignored** (stub), so default behavior
(always full-hash) is byte-unchanged.

## Design (locked — ARCHITECTURE.md §8.4; D-017-B)
- `scripts/wiki_skills/wiki_lint.py`: `parser.add_argument("--mtime-skip",
  action="store_true", help="skip re-hash when stored mtime matches disk (integrity-relaxed)")`.
- `scripts/wiki_index/lint.py`: the lint runner gains `mtime_skip: bool = False`; the
  `repo.check_drift(vid)` call (line 61) becomes `repo.check_drift(vid, trust_mtime=mtime_skip)`.
- `scripts/wiki_index/sqlite_repository.py::check_drift(self, vault_id, *, trust_mtime: bool =
  False)` — add the keyword-only param; **do not use it yet** (017-11 implements). Default
  `False` keeps every existing caller unchanged.

## Steps
1. Add the CLI flag; thread `mtime_skip` from `wiki_lint.main` → lint runner → `check_drift`.
2. Add `trust_mtime` kwarg to `check_drift` (ignored).
3. RED `test_check_drift_mtime_skip`: on an unchanged vault with `trust_mtime=True`, assert
   the file is **not** re-hashed (spy on `compute_file_hash` / `read_bytes`) — RED until 011.

## Verification
- `pytest -q -k "mtime_skip"` → the new test RED (xfail), everything else GREEN.
- Default `wiki-lint` (no flag) behavior + envelope byte-identical; `mypy --strict` clean.
