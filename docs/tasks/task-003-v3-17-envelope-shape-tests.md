# Task 003-v3-17: adversarial envelope-shape parametrized test (CWE-117 / CWE-209 regression guard)

## Meta

- **Bead ID**: `task-003-v3-17-envelope-shape-tests`
- **Slug**: `envelope-shape-tests`
- **Maps to**: Issue **I-V3.12**; RTM row **R-42**; H-5, H-6, H-9; CWE-117 / CWE-209.
- **Depends on**: task-003-v3-02 (validator envelopes), task-003-v3-03 (apply envelopes).
- **Estimated time**: 0.25 day
- **Priority**: High (security regression guard).

## Use Case Connection

- Audits every exit-2 + exit-4 sub-envelope from R-42 v3.1 to confirm it never leaks offending content. Future regression where a developer accidentally adds `value`, `raw`, `content`, or `received` to an envelope is caught by this test.

## Task Goal

Add a parametrized test `test_apply_error_envelopes_never_echo_content` (or equivalent name) to `tests/test_wiki_extract_concepts.py` that:

1. **Parametrizes** over every sub-envelope from R-42(c) + R-42(d) v3.1:
   - exit-2 sub-envelopes: `SOURCE_NOT_FOUND`, `INVALID_SOURCE_PATH`, `INVALID_SOURCE_SLUG`, `SOURCE_TOO_LARGE`, `SOURCE_CHANGED_DURING_EXTRACTION`, `INVALID_CANDIDATES_PATH`.
   - exit-4 sub-envelopes: `EXTRACTION_PARSE_ERROR`, `CANDIDATES_TOO_LARGE`, `CANDIDATE_COUNT_OUT_OF_BOUNDS`, `FIELD_TOO_LONG`, `UNKNOWN_FIELD`, `FIELD_QUOTE_NOT_IN_BODY`.
   - Total: 12 parameter cases.
2. **For each parameter** (envelope code + trigger logic):
   - Construct an input scenario that triggers the envelope (with a known "secret"-like offending string, e.g., `OFFENDING="SECRET_LEAK_CANARY_123"`).
   - Invoke the relevant subprocess or function-level path.
   - Capture stdout + parse JSON envelope.
   - **Assert envelope shape**: keys must be subset of `{error, field, reason, message}` (and a few well-known optional keys like `manifest` are OK if the test scenario emits a non-error envelope — but the failure cases tested here are error envelopes only).
   - **Assert NO keys**: `content`, `value`, `raw`, `received`.
   - **Assert no content leak**: the `OFFENDING` string is NOT a substring of any envelope-field value (including `error`, `field`, `reason`, `message`).

## Stub-First Plan

### Phase 1 — Parametrized test (Red→Green per parameter)

1. Add the parametrized test:
   ```python
   @pytest.mark.parametrize("envelope_code,trigger", [
       ("SOURCE_TOO_LARGE", _trigger_source_too_large),
       ("SOURCE_CHANGED_DURING_EXTRACTION", _trigger_source_changed),
       ("INVALID_CANDIDATES_PATH", _trigger_invalid_candidates_path),
       ("CANDIDATES_TOO_LARGE", _trigger_candidates_too_large),
       ("CANDIDATE_COUNT_OUT_OF_BOUNDS", _trigger_count_oob),
       ("FIELD_TOO_LONG", _trigger_field_too_long),
       ("UNKNOWN_FIELD", _trigger_unknown_field),
       ("FIELD_QUOTE_NOT_IN_BODY", _trigger_quote_not_in_body),
       ("INVALID_SOURCE_PATH", _trigger_invalid_source_path),
       ("INVALID_SOURCE_SLUG", _trigger_invalid_source_slug),
       ("SOURCE_NOT_FOUND", _trigger_source_not_found),
       ("EXTRACTION_PARSE_ERROR", _trigger_extraction_parse_error),
   ])
   def test_apply_error_envelopes_never_echo_content(envelope_code, trigger, tmp_path):
       OFFENDING = "SECRET_LEAK_CANARY_123"
       result = trigger(tmp_path, OFFENDING)  # returns (exit_code, stdout_dict)
       exit_code, env = result
       assert env["error"] == envelope_code
       forbidden_keys = {"content", "value", "raw", "received"}
       assert not (forbidden_keys & set(env.keys()))
       for v in env.values():
           if isinstance(v, str):
               assert OFFENDING not in v, f"envelope leaked OFFENDING via '{v}'"
   ```
2. Define 12 `_trigger_*` helpers — each one sets up the precise scenario for its envelope code, ensuring the canary string is somewhere in the input (e.g., as a `definition` field value, as a candidates-file content, etc.) but should NOT appear in the envelope output.
3. Run `pytest tests/test_wiki_extract_concepts.py::test_apply_error_envelopes_never_echo_content -v` → 12 parameter cases pass.

### Phase 2 — n/a

## Changes Description

### Edited files

- `tests/test_wiki_extract_concepts.py`:
  - Add 12 `_trigger_*` helper functions.
  - Add the parametrized test.

## Files Touched

- `tests/test_wiki_extract_concepts.py`

## Acceptance Criteria

- [ ] **R-42**: 12 parameter cases pass — every envelope code from R-42(c) + R-42(d) v3.1 is covered.
- [ ] **CWE-117 / CWE-209 regression guard**: each envelope passes the `OFFENDING NOT IN VALUE` assertion.
- [ ] No envelope contains the forbidden keys `{content, value, raw, received}`.
- [ ] **Full pytest sweep**: `pytest tests/ -q` → ≥ prior_count + 12 passed.

## Verification

```bash
source .venv/bin/activate

pytest tests/test_wiki_extract_concepts.py::test_apply_error_envelopes_never_echo_content -v
# expect: 12 passed

pytest tests/ -q
# expect: ≥ 436 passed (Option A target)
```

## Rollback

`git checkout HEAD~1 tests/test_wiki_extract_concepts.py` (revert just this bead).

## Notes

- The 12 `_trigger_*` helpers are small but necessary for parameter-isolation. Each helper sets up its own tmpdir / vault / DB to avoid cross-pollution.
- For envelope codes that require a subprocess (e.g., `INVALID_SOURCE_PATH` argparse path), use `subprocess.run` + parse stdout JSON.
- For codes triggerable at function level (e.g., `UNKNOWN_FIELD` via direct `_validate_candidates_schema` call), call the function and capture the `ExtractionParseError` attrs — convert to dict form for the assertion.
- The OFFENDING canary string is intentionally distinctive (a unique substring like `SECRET_LEAK_CANARY_123`) so the assertion never false-negatives on incidental substring matches.
