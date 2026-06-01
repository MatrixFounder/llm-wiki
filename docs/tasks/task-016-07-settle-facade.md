# task-016-07 — Settle the facade + prove the lock

**Parent:** TASK 016. **Depends on:** 016-06. **RTM:** R-016-2, R-016-5.

## Goal
After the five leaves are out, confirm the facade `__init__.py` is exactly the orchestration
layer + the 8 lock re-exports, with the R-2 facade-global resolution intact. No further code
moves — this is the verification/settle bead.

## Context
Facade `__init__.py` should now contain ONLY:
- Orchestration (defined here, shape A): `dispatch_to_indexer`, `prepare`,
  `_load_known_and_drift`, `_recon_single`, `_batch_prepare`, `apply`, `_apply_validate`,
  `_apply_write`, `_apply_candidates_to_db`, `_batch_apply`, `_try_update_idempotency_state`,
  `_build_parser_v3`, `main`.
- The 8 lock symbols as facade globals: `make_repo` (`from scripts.wiki_index.factory import make_repo`), `validate_manifest`/`index_from_manifest`/`WikiIngestError` (`from scripts.wiki_skills._manifest_consumer import …`), `load_known_entities`/`update_idempotency_state` (`from ._db import …`), and the facade-defined `dispatch_to_indexer`/`_apply_candidates_to_db`/`_try_update_idempotency_state`.
- Re-exports of leaf symbols used externally (e.g. `_derive_source_project`, `classify_candidates`, `write_concept_page`, `build_manifest`, `ExtractionParseError`).

## Steps
1. Audit `__init__.py`: every patched-name caller resolves the name as a bare facade global; no leaf is imported-and-called-qualified for a patched name; no leaf imports the facade.
2. Confirm `wec.validate_manifest is _manifest_consumer.validate_manifest` (and `index_from_manifest`, `WikiIngestError`) — identity preserved (AC-016-3).
3. Run the lock proof explicitly:
   - `tests/test_wiki_extract_concepts.py::test_patch_target_lock_at_skill_module`
   - `::test_module_imports_neutral_manifest_consumer`
   - all of `tests/test_perf_hardening.py`
   - the two `update_idempotency_state` patch tests.
4. `wc -l scripts/wiki_skills/wiki_extract_concepts/*.py` — confirm facade ≤ ~900 (advisory) and each leaf ≤ ~450 (advisory); no leaf is a new god-file.
5. Per-bead gate.

## Acceptance
- ✅ All 8 lock symbols rebindable at the facade; the R-2 lock + perf tests pass UNMODIFIED.
- ✅ `_manifest_consumer` identity preserved on the facade.
- ✅ Facade + leaf line counts within advisory targets; full suite green; mypy strict clean.

## Files
- `scripts/wiki_skills/wiki_extract_concepts/__init__.py` (audit/settle only — no logic change)
