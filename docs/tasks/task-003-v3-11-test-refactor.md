# Task 003-v3-11: delete remaining anthropic-mock function tests (post-Phase-1 cleanup)

> **Note (Option A split)**: this bead is the **second half** of the original I-V3.6 test-refactor scope. The first half — deleting the 6 legacy-shape `main()` tests that would break under 003-v3-00's subparser change — was moved to **003-v3-11a** (Phase -1, runs BEFORE 003-v3-00). This bead now handles only the **9 remaining anthropic-mock tests** that exercise `extract_concepts_llm()` directly (no `main()` call); they stay green through 003-v3-00..003-v3-05 and are deleted here to unblock 003-v3-06's code deletion.

## Meta

- **Bead ID**: `task-003-v3-11-test-refactor`
- **Slug**: `test-refactor`
- **Maps to**: Issue **I-V3.6** (second sub-bead of test-refactor scope; see also 003-v3-11a).
- **Depends on**: task-003-v3-01, 02, 03, 04, 05 (all new logic landed; the 9 deleted tests' regression intent is fully covered by new tests in those beads).
- **Estimated time**: 0.25 day (reduced from 0.5d after Option A split — 11a took the harder half).
- **Priority**: Critical (blocks 003-v3-06 code deletion).

## Use Case Connection

- Test surface mirrors the v3.1 production surface. After this bead lands, the test file has 0 references to `anthropic`, `extract_concepts_llm`, `_build_extraction_prompt`, or `LLMUnavailableError` — making 003-v3-06's deletion of those symbols safe.

## Task Goal

Atomic deletion of the **9 anthropic-mock-only function tests** in `tests/test_wiki_extract_concepts.py` plus retirement of the `_validate_extraction_schema` import alias (renamed to `_validate_candidates_schema` by 003-v3-02).

### Tests to delete (verified against current file state after 11a)

| # | Original line | Test name | Notes |
|---|---|---|---|
| 1 | 241 | `test_extract_concepts_llm_parses_valid_json` | Calls `wec.extract_concepts_llm("body", [])` directly |
| 2 | 257 | `test_extract_concepts_llm_raises_on_malformed_json` | Direct LLM call |
| 3 | 266 | `test_extract_concepts_llm_raises_on_schema_violation` | Direct LLM call |
| 4 | 278 | `test_extract_concepts_llm_raises_on_api_error` | Direct LLM call |
| 5 | 290 | `test_extract_concepts_llm_uses_temperature_zero` | Direct LLM call (parameter assertion) |
| 6 | 303 | `test_extract_concepts_llm_caps_max_tokens_at_4096` | Direct LLM call (cap assertion) |
| 7 | 589 | `test_extract_concepts_llm_rejects_oversized_input` | Direct LLM call (input-size cap) |
| 8 | 612 | `test_extract_concepts_llm_wraps_bad_request_error` | Direct LLM call (error wrapping) |
| 9 | 627 | `test_extract_concepts_llm_suppresses_sdk_exception_chain` | Direct LLM call (exception-chain suppression) |

These 9 tests do NOT call `wec.main(...)` — they invoke `extract_concepts_llm("body", [])` directly. They remain GREEN through 003-v3-00..003-v3-05 because the function is still defined; they are deleted here so 003-v3-06's deletion of the function does not orphan them.

### Tests already moved to 003-v3-11a (do NOT delete here)

- `test_argparse_help_text_contains_ingest_flag` (was line 36) — gone via 11a
- `test_main_rejects_absolute_source_page_path` H-1 (was line 458) — gone via 11a; regression now in 003-v3-01
- `test_main_rejects_invalid_source_slug` H-3 (was line 486) — gone via 11a; regression now in 003-v3-01
- `test_main_ingest_partial_failure_does_not_update_source_state` C-1 (was line 522) — gone via 11a; regression now in 003-v3-03
- `test_main_with_ingest_calls_dispatch_and_emits_combined` (was line 1071) — gone via 11a; regression in 003-v3-03
- `test_main_without_ingest_emits_manifest_only` (was line 1140) — gone via 11a; regression in 003-v3-03

## Stub-First Plan

n/a (test deletion is the deliverable). No Phase-1 / Phase-2 split.

## Changes Description

### Edited files

- `tests/test_wiki_extract_concepts.py`:
  - Delete the 9 anthropic-mock function tests catalogued above.
  - Remove `_validate_extraction_schema` import alias if present; tests should use `_validate_candidates_schema` directly (the rename was provisioned by 003-v3-02).
  - Remove any helper that exists solely to support the deleted tests (e.g., `_llm_response` fixture builder) if grep confirms 0 remaining callers.

## Component Integration

- **No production code touched.**
- **Patch-target lock invariant (R-1)** carried forward: any remaining `unittest.mock.patch(...)` calls MUST target `scripts.wiki_skills.wiki_extract_concepts.<symbol>` for any symbol bound in that module. The 9 deleted tests use `mock.patch("anthropic.Anthropic")` — that's an external library, not a module symbol, so R-1 does not apply, but their removal eliminates the last `anthropic.*` patch site in the test file.

## Files Touched

- `tests/test_wiki_extract_concepts.py` (only)

## Acceptance Criteria

- [ ] **Test count delta**: pytest count drops by exactly 9 from the pre-bead state.
- [ ] **Final grep audit** — `grep -nE "anthropic\\.|LLMUnavailableError|extract_concepts_llm|_build_extraction_prompt|mock\\.patch.*anthropic|patch.*_validate_extraction_schema" tests/test_wiki_extract_concepts.py` → 0 matches.
- [ ] **Full sweep**: `pytest tests/ -q` → 0 failed.
- [ ] **Patch-target lock invariant (R-1)**: `grep -rn "patch.*_manifest_consumer\\.\\(index_from_manifest\\|validate_manifest\\|WikiIngestError\\)" tests/` → 0 matches.
- [ ] **No orphaned helpers**: `python -m pyflakes tests/test_wiki_extract_concepts.py` → no `F841` (unused local) or `F401` (unused import).
- [ ] **`_llm_response` helper**: either removed (if 0 callers) or retained (if other tests still use it — confirm via grep).

## Verification

```bash
source .venv/bin/activate

# Pre-deletion baseline
pytest --collect-only tests/test_wiki_extract_concepts.py 2>&1 | tail -3

# After deletion: final audit
grep -nE "anthropic\\.|LLMUnavailableError|extract_concepts_llm|_build_extraction_prompt|mock\\.patch.*anthropic|patch.*_validate_extraction_schema" tests/test_wiki_extract_concepts.py
# expect: 0 matches

# Full sweep
pytest tests/ -q
# expect: 0 failed

# Patch-target lock
grep -rn "patch.*_manifest_consumer\\.\\(index_from_manifest\\|validate_manifest\\|WikiIngestError\\)" tests/
# expect: empty
```

## Rollback

`git checkout HEAD~1 tests/test_wiki_extract_concepts.py`. Re-introduces the 9 anthropic-mock function tests. Suite then depends on `extract_concepts_llm` being present (which it is until 003-v3-06 runs).

## Notes

- The 9 deleted tests are NOT a coverage regression — they tested `extract_concepts_llm`, which is itself being deleted in 003-v3-06. The test surface for the v3.1 LLM-free skill is the regression migrations in 003-v3-01 (H-1, H-3) + 003-v3-03 (C-1, ingest e2e, no-ingest manifest) + all net-new tests from 003-v3-01..05 and 003-v3-17.
- **Risk R-2 mitigation**: this bead's acceptance criterion (`pytest tests/ -q` → 0 failed) confirms suite health after the deletion; the combination of 11a (pre-Phase-1 deletion) + this bead (post-Phase-1 deletion) implements the **Option A green-throughout invariant** decided in adversarial review 2026-05-28.
