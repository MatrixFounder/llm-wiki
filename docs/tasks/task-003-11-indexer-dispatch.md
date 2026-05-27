# Task 003-11: `dispatch_to_indexer` — in-process call via neutral module

## Meta

- **Bead ID**: `task-003-11-indexer-dispatch`
- **Slug**: `indexer-dispatch`
- **Maps to**: Issue **I-7.11**; RTM row **R-41**.
- **Depends on**: task-003-00 (the neutral module — import target), task-003-10 (manifest dict is the input).
- **Estimated time**: 0.5 day
- **Priority**: Critical (the Decision-15 path; without this, `--ingest` is just a flag with no effect)

## Use Case Connection

- **UC-08 main scenario (with `--ingest`)** steps 11′-15′:
  - 11′ Build manifest dict in memory.
  - 12′ Import `validate_manifest` + `index_from_manifest` from `_manifest_consumer`.
  - 13′ Call `validate_manifest(...)` → on `WikiIngestError` emit error envelope, exit 6.
  - 14′ Call `index_from_manifest(...)` → capture summary.
  - 15′ Emit combined `{"extraction": <manifest>, "index": <summary>}`. Exit 0 (or 5 if `summary["failed"]` non-empty).

## Task Goal

Replace the `NotImplementedError` stub in `wiki_extract_concepts.py::dispatch_to_indexer(manifest_dict, vault_id, vault_root, db_path) -> dict` with:

1. Call `validate_manifest(manifest_dict, vault_id, vault_root)` from the **already-imported-at-module-top** `_manifest_consumer` symbols (003-01 pinned them).
2. On `WikiIngestError` → propagate (caller in `main()` catches and maps to exit 6).
3. Call `index_from_manifest(manifest_dict, vault_id, vault_root, db_path=db_path)`.
4. Return the summary dict.

**CRITICAL PATCH-TARGET LOCK** (Risk R-2 in PLAN.md §6, see I-7.12 patch-target note in TASK.md §4): the import lives at the **module top** of `wiki_extract_concepts.py` (pinned by 003-01) so that:
```python
# in tests:
unittest.mock.patch("scripts.wiki_skills.wiki_extract_concepts.index_from_manifest")
# NOT:
unittest.mock.patch("scripts.wiki_skills._manifest_consumer.index_from_manifest")
```
Tests that patch the source-of-truth module name will pass during isolated testing but fail under refactor. The bound name in `wiki_extract_concepts` is what `dispatch_to_indexer` actually calls.

## Stub-First Plan

**Phase 1 — Red tests on stub**:

1. Add to `tests/test_wiki_extract_concepts.py`:
   - `test_dispatch_to_indexer_calls_validate_then_index` (Phase 1):
     - Mock both `validate_manifest` and `index_from_manifest` (patched at `scripts.wiki_skills.wiki_extract_concepts.*` — the bound names).
     - Call `dispatch_to_indexer({"status":"ok","vault_id":"vid",...}, "vid", Path("/v"), None)`.
     - On stub: `NotImplementedError`. After Phase 2: assert `validate_manifest` called once with the manifest + vault_id; `index_from_manifest` called once after; returns the mock's summary.
   - `test_dispatch_to_indexer_propagates_wiki_ingest_error` (Phase 2):
     - Mock `validate_manifest` to raise `WikiIngestError("bad")`.
     - Call `dispatch_to_indexer`.
     - Assert `WikiIngestError` propagated; `index_from_manifest` NOT called.
   - `test_dispatch_to_indexer_returns_summary_dict` (Phase 2):
     - Mock returns `{"upserted":[{...}], "failed":[]}`.
     - Assert function returns the same dict.
   - `test_main_with_ingest_calls_dispatch` (Phase 2 — end-to-end-ish):
     - Patch `scripts.wiki_skills.wiki_extract_concepts.dispatch_to_indexer` to return `{"upserted":[],"failed":[]}`.
     - Run `main(["--vault","v","--vault-root","/v","--source-page","s","--ingest"])` with all other helpers mocked.
     - Assert `dispatch_to_indexer` called exactly once.
     - Assert stdout contains `{"extraction": ...}` and `{"index": ...}` combined JSON.
   - `test_main_without_ingest_does_not_call_dispatch` (Phase 2):
     - Same setup, but no `--ingest` flag.
     - Assert `dispatch_to_indexer` called ZERO times.
     - Stdout contains only the manifest, NOT the combined object.
2. Run pytest — Red.

**Phase 2 — Logic**:

1. Replace the body:
   ```python
   def dispatch_to_indexer(
       manifest_dict: dict[str, Any],
       vault_id: str,
       vault_root: Path,
       db_path: str | None,
   ) -> dict[str, Any]:
       """In-process dispatch to the neutral manifest consumer.

       Imports validate_manifest + index_from_manifest from _manifest_consumer
       (pinned at module top of this file — see 003-01 patch-target lock).

       Raises WikiIngestError on contract violation (caller maps to exit 6).
       """
       validate_manifest(manifest_dict, vault_id, vault_root)
       return index_from_manifest(
           manifest_dict,
           vault_id,
           vault_root,
           db_path=db_path,
       )
   ```
2. Wire into `main()` after the manifest is built:
   ```python
   manifest = build_manifest(...)
   if args.ingest:
       try:
           summary = dispatch_to_indexer(manifest, args.vault, args.vault_root, args.db_path)
       except WikiIngestError as e:
           print(json.dumps({"error": "MANIFEST_INVALID", "message": str(e)}))
           return 6
       combined = {"extraction": manifest, "index": summary}
       print(json.dumps(combined, indent=2))
       if summary.get("failed"):
           return 5
       return 0
   else:
       print(json.dumps(manifest, indent=2))
       return 0
   ```
3. Unskip Phase-2 tests; run pytest — Green.

## Changes Description

### New Files

- None.

### Changes in Existing Files

#### File: `scripts/wiki_skills/wiki_extract_concepts.py`

- Replace `dispatch_to_indexer` stub body.
- Wire `main()` to call dispatch when `--ingest` is set; map `WikiIngestError` → exit 6; map `summary["failed"]` non-empty → exit 5.

#### File: `tests/test_wiki_extract_concepts.py`

- Add 5 unit tests (1 Phase-1 + 4 Phase-2). Patch targets are STRICTLY at `scripts.wiki_skills.wiki_extract_concepts.*`.

### Component Integration

- This is the final integration point. After 003-11 lands, `main()` has the full happy-path wiring; only tests (003-12, 003-13) and regression (003-14) remain.
- The patch-target lock is a contract: any future refactor that changes WHERE `dispatch_to_indexer` imports `validate_manifest` / `index_from_manifest` from MUST update the tests in lockstep.

## Files Touched (explicit list)

- `scripts/wiki_skills/wiki_extract_concepts.py` (modified — 1 stub replacement + `main()` wiring)
- `tests/test_wiki_extract_concepts.py` (modified — add 5 tests)

## Test Surface

- **New**: 5 unit tests:
  - `test_dispatch_to_indexer_calls_validate_then_index`
  - `test_dispatch_to_indexer_propagates_wiki_ingest_error`
  - `test_dispatch_to_indexer_returns_summary_dict`
  - `test_main_with_ingest_calls_dispatch`
  - `test_main_without_ingest_does_not_call_dispatch`

## Acceptance Criteria

- [ ] **R-41(a)**: running `wiki-extract-concepts ...` (without `--ingest`) emits a manifest that passes `validate_manifest(...)` from `_manifest_consumer` (verified by 003-10's contract test).
- [ ] **R-41(b)**: with `--ingest`, this skill calls `validate_manifest` then `index_from_manifest` IN-PROCESS (no subprocess) — verified by `test_dispatch_to_indexer_calls_validate_then_index`.
- [ ] **R-41(b) combined emit**: stdout JSON has both `extraction` and `index` keys (verified by `test_main_with_ingest_calls_dispatch`).
- [ ] **R-41(d)**: without `--ingest`, dispatch NOT called (verified by `test_main_without_ingest_does_not_call_dispatch`).
- [ ] **R-41(e)**: `wiki_enrich.py` argparse surface untouched — `grep -E "manifest-file|manifest-stdin" scripts/wiki_skills/wiki_enrich.py` returns empty (Decision-15 invariant, verified by smoke 9 in TASK.md §7).
- [ ] **R-41(f)**: failure inside `index_from_manifest` returns `partial`/`error` envelope; `main()` maps to exit 5.
- [ ] **R-42(g)**: `WikiIngestError` → exit 6 with `MANIFEST_INVALID` envelope (verified by `test_dispatch_to_indexer_propagates_wiki_ingest_error` + `main()` wiring test).
- [ ] **Patch-target lock**: `grep -rn "patch.*_manifest_consumer.index_from_manifest" tests/` returns empty.
- [ ] All 5 unit tests pass.
- [ ] `mypy --strict` clean.
- [ ] Full sweep `pytest tests/ -q` still green.

## Verification

```bash
pytest tests/test_wiki_extract_concepts.py -v -k "dispatch or main_with_ingest or main_without_ingest"
pytest tests/ -q
mypy --strict scripts/wiki_skills/wiki_extract_concepts.py

# Patch-target lock check (must be empty)
grep -rn "patch.*_manifest_consumer\.index_from_manifest" tests/
grep -rn "patch.*_manifest_consumer\.validate_manifest" tests/

# Decision-15 invariant
grep -E "manifest-file|manifest-stdin" scripts/wiki_skills/wiki_enrich.py
# expect: no output
```

## Rollback

Revert `dispatch_to_indexer` to stub; remove the 5 tests + `main()` wiring (keep only the manifest-emit path). The `--ingest` flag becomes dead code (still parsed by argparse, but has no effect). Smoke 4 in TASK.md §7 will fail until restored.

## Notes

- The dispatch function is intentionally tiny (~3 lines of logic) — most of the work is in 003-00 (the neutral module's `index_from_manifest` body, which was moved verbatim from `wiki_enrich.py`).
- **Patch-target lock rationale**: `unittest.mock.patch("X.Y")` patches the name `Y` as bound in module `X`. Since `wiki_extract_concepts` imports `index_from_manifest` at module top, the bound name lives at `scripts.wiki_skills.wiki_extract_concepts.index_from_manifest`. Patching `_manifest_consumer.index_from_manifest` would patch the source-of-truth name but NOT the already-bound name in `wiki_extract_concepts` — the test would appear to pass (no errors) but the real function would still execute. This is a classic Python-mock pitfall worth a code-review check.
- The combined JSON emit shape `{"extraction":..., "index":...}` matches v1 contract per TASK.md §3 v2 row (Decision-15 + Decision-16).
- `WikiIngestError` is imported at module top from `_manifest_consumer` (003-01); `except` clause in `main()` catches it. No re-import inside `dispatch_to_indexer` body.
