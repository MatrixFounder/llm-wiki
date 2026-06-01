# task-016-00 — Anchor (baseline + lock-surface record)

**Parent:** TASK 016. **Depends on:** —. **RTM:** R-016-NF2.

## Goal
Establish the green baseline and pin the gate BEFORE any move. No code change.

## Context
- `scripts/wiki_skills/wiki_extract_concepts.py` (2174 lines — the target).
- Gate tests: `tests/test_wiki_extract_concepts.py::test_patch_target_lock_at_skill_module`,
  `::test_module_imports_neutral_manifest_consumer`,
  `::test_apply_error_envelopes_never_echo_content`; `tests/test_perf_hardening.py` (all);
  `tests/test_wiki_extract_concepts_integration.py` (the `-m` subprocess).
- File-path-literal tests that will need repointing: `tests/test_extract_concepts_candidate_regression.py:18` (`_SRC`).

## Steps
1. `source .venv/bin/activate && python -m pytest tests/ -q` → record the count (expect **879 passed, 4 skipped**).
2. `mypy --strict scripts/` → record **0 errors (63 files)**.
3. Confirm the 8-symbol lock surface by grep (each must be patched at `…wiki_extract_concepts.<name>`):
   `make_repo`, `load_known_entities`, `validate_manifest`, `index_from_manifest`,
   `dispatch_to_indexer`, `_apply_candidates_to_db`, `_try_update_idempotency_state`,
   `update_idempotency_state`.
4. Record `wc -l scripts/wiki_skills/wiki_extract_concepts.py` = 2174 (the "before" number).

## Acceptance
- ✅ Baseline recorded: 879 (+4 skip) pytest green, mypy strict clean.
- ✅ 8-symbol lock surface confirmed present in the suite.
- ✅ No code change.

## Files
- (none — read-only anchor)
