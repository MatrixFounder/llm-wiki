# Task 003-v3-02: strict-mode `_validate_candidates_schema` (rename + count bound + per-field caps + UNKNOWN_FIELD)

## Meta

- **Bead ID**: `task-003-v3-02-strict-validator`
- **Slug**: `strict-validator`
- **Maps to**: Issue **I-V3.1c**; RTM rows **R-33′**, **R-42**; Q10 (count bound), Q12 (per-field caps), Q14 (no extra keys); H-2, H-6, H-9.
- **Depends on**: task-003-v3-00 (subparser scaffold + module structure ready).
- **Estimated time**: 0.5 day
- **Priority**: Critical (003-v3-03 apply consumes the strict validator).

## Use Case Connection

- **UC-08 v3.1 A7**: agent emits 0 or 26+ candidates → exit 4 CANDIDATE_COUNT_OUT_OF_BOUNDS.
- **UC-08 v3.1 A8**: agent emits 10MB definition field → exit 4 FIELD_TOO_LONG.
- **UC-08 v3.1 A9**: agent emits extra key in candidate → exit 4 UNKNOWN_FIELD.

## Task Goal

Rename `_validate_extraction_schema` → `_validate_candidates_schema` and harden:

1. **Strict-mode keys (H-9, Q14)**: enforce equality `item.keys() == _REQUIRED_CANDIDATE_KEYS`. Extra keys → `UNKNOWN_FIELD` (exit 4 envelope).
2. **Count bound (H-2, Q10)**: enforce `1 ≤ len(items) ≤ 25`. Empty list OR > 25 items → `CANDIDATE_COUNT_OUT_OF_BOUNDS` (exit 4 envelope).
3. **Per-field caps (H-6, Q12)**:
   - `len(item["name"]) > 200` → `FIELD_TOO_LONG`
   - `len(item["definition"]) > 2000` → `FIELD_TOO_LONG`
   - `len(item["source_quote"]) > 500` → `FIELD_TOO_LONG`
4. **Preserve v2 invariants**: kebab slug regex (`_SLUG_RE`), `Lstart-Lend` span (`_SOURCE_SPAN_RE`), `entity_type` whitelist (`_ALLOWED_ENTITY_TYPES`).
5. **Envelope shape (CWE-117 / H-5)**: all errors emit `{error: <CODE>, field: <field_name>, reason: <human readable>}` — NEVER `content`, `value`, `raw`, `received`. The offending data value MUST NOT appear in any envelope field.
6. **Optional semantic check (Q13 / M-5)**: if `source_body` is in scope (apply passes it; validator-call sites without source_body skip), check `item["source_quote"].lower() in source_body.lower()` → `FIELD_QUOTE_NOT_IN_BODY` (exit 4). Bypass via env var `WIKI_EXTRACT_NO_QUOTE_CHECK=1`.

## Stub-First Plan

### Phase 1 — Logic + 4 new unit tests (Red→Green)

1. In `scripts/wiki_skills/wiki_extract_concepts.py`:
   - **Rename** `_validate_extraction_schema` → `_validate_candidates_schema`. Keep `_validate_extraction_schema` as a one-bead alias (`_validate_extraction_schema = _validate_candidates_schema`) until 003-v3-06 removes the alias. This preserves existing v2 test imports (12 LLM-mock tests still call the old name) through the refactor window.
   - **Rename constant** `_REQUIRED_LLM_KEYS` → `_REQUIRED_CANDIDATE_KEYS`. Same value, same shape.
   - Add new module-level constants:
     ```python
     _MAX_NAME_LEN = 200
     _MAX_DEFINITION_LEN = 2000
     _MAX_SOURCE_QUOTE_LEN = 500
     _MIN_CANDIDATE_COUNT = 1
     _MAX_CANDIDATE_COUNT = 25
     ```
   - Change validator signature to `_validate_candidates_schema(items: list[Any], source_body: str | None = None) -> None`. The `source_body` arg is optional; when provided AND env var `WIKI_EXTRACT_NO_QUOTE_CHECK` is not set, the quote-in-body check runs.
   - Body order: count-bound FIRST (cheapest check that doesn't need iteration); then per-item iteration: shape check (dict), `keys() == _REQUIRED_CANDIDATE_KEYS` (strict equality — extra key → `UNKNOWN_FIELD`), per-field cap, slug regex, span regex, entity_type whitelist, optional quote check.
   - When raising `ExtractionParseError`, the message must follow `{error: CODE, field: FIELD, reason: REASON}` shape (JSON-serialized inside the exception message OR raised with an attribute). To keep envelope construction in one place, raise with `ExtractionParseError(error="UNKNOWN_FIELD", field="<key>", reason="extra key not in required set")` — this requires extending `ExtractionParseError` to accept structured kwargs OR shipping a small `_envelope` helper. **Implementation choice**: extend `ExtractionParseError` with optional `error`, `field`, `reason` attributes (default None for back-compat with v2 raises that pass a string). The caller (apply, 003-v3-03) emits the envelope using these attrs when present.
2. Add 4 new tests to `tests/test_wiki_extract_concepts.py`:
   - `test_validator_strict_unknown_field_raises_H9` — items list has extra key `model="evil"`; expect `ExtractionParseError` with `.error == "UNKNOWN_FIELD"`, `.field == "model"`; offending string `"evil"` NOT in `str(e)` or `e.reason`.
   - `test_validator_count_bound_empty_raises_H2` — items list `[]`; expect `ExtractionParseError` with `.error == "CANDIDATE_COUNT_OUT_OF_BOUNDS"`, `.field == "<root>"`.
   - `test_validator_count_bound_too_many_raises_H2` — items list with 26 entries; expect same envelope code.
   - `test_validator_field_too_long_definition_raises_H6` — items list with one valid item but `definition = "x" * 5000`; expect `ExtractionParseError` with `.error == "FIELD_TOO_LONG"`, `.field == "definition"`; offending string (5000 x chars) NOT a substring of `e.reason`.
   - `test_validator_field_too_long_name_raises_H6` — `name = "x" * 201`; same envelope code with `.field == "name"`.
   - `test_validator_field_too_long_source_quote_raises_H6` — `source_quote = "x" * 501`; same envelope code with `.field == "source_quote"`.
   - `test_validator_quote_in_body_optional_M5` — items list with valid item where `source_quote = "this exact quote"` and `source_body = "...this exact quote is in the body..."`; assert NO raise. Then swap source_body to `"foo bar"`; assert `ExtractionParseError` with `.error == "FIELD_QUOTE_NOT_IN_BODY"`.
   - `test_validator_quote_in_body_bypass_env_var_M5` — set `WIKI_EXTRACT_NO_QUOTE_CHECK=1`; assert no raise even when quote is absent.

   Net new tests: **+8** (Note: spec said +4 but per Stub-First we ship one test per behaviour. Updated math: 003-v3-02 contributes +8 tests; total target is 436 per PLAN §2 suite-size table.)

3. Run `pytest tests/test_wiki_extract_concepts.py -k validator -v` → 8 new tests pass.

### Phase 2 — n/a (logic lands inside Phase 1 — strict validator IS the deliverable)

## Changes Description

### Edited files

- `scripts/wiki_skills/wiki_extract_concepts.py`:
  - Rename `_validate_extraction_schema` → `_validate_candidates_schema` + add alias for back-compat.
  - Rename `_REQUIRED_LLM_KEYS` → `_REQUIRED_CANDIDATE_KEYS` + add alias.
  - Add 5 new module-level cap/count constants.
  - Extend `ExtractionParseError` with optional `error`, `field`, `reason` attributes.
  - Add strict-mode logic + count-bound + per-field cap + optional quote-in-body check.
- `tests/test_wiki_extract_concepts.py`: add 8 new tests.

## Component Integration

- `apply` (003-v3-03) calls `_validate_candidates_schema(candidates, source_body=...)` and surfaces the envelope via `emit({...}, exit_code=4)` using the structured `ExtractionParseError` attrs.
- Existing v2 tests that import `_validate_extraction_schema` still pass (alias preserved).
- 003-v3-17 (envelope-shape parametrized test) consumes the structured `(error, field, reason)` shape for its content-leak audit.

## Files Touched

- `scripts/wiki_skills/wiki_extract_concepts.py`
- `tests/test_wiki_extract_concepts.py`

## Acceptance Criteria

- [ ] **R-33′ (b)**: `_validate_candidates_schema` enforces strict equality on keys; rejects extra keys with `UNKNOWN_FIELD`.
- [ ] **R-33′ (b) (H-2)**: count bound `1 ≤ N ≤ 25` enforced.
- [ ] **R-33′ (b) (H-6)**: per-field caps enforced (`name ≤ 200`, `definition ≤ 2000`, `source_quote ≤ 500`).
- [ ] **R-33′ (b) (M-5)**: optional quote-in-body check; env var `WIKI_EXTRACT_NO_QUOTE_CHECK=1` bypasses.
- [ ] **R-42 (CWE-117)**: every `ExtractionParseError` raised by the validator has `.error`, `.field`, `.reason` populated; offending field content is NOT a substring of `.reason`.
- [ ] Preserved v2 invariants: kebab slug regex, span regex, entity_type whitelist.
- [ ] Existing 12 LLM-mock tests still pass (alias `_validate_extraction_schema = _validate_candidates_schema` is the bridge).
- [ ] 8 new tests pass.
- [ ] **Full pytest sweep**: `pytest tests/ -q` → 402 (post-01) + 8 = **≥ 410 passed, 0 failed** (per PLAN §2 suite-size table).
- [ ] `mypy --strict scripts/wiki_skills/wiki_extract_concepts.py` clean.

## Verification

```bash
source .venv/bin/activate

pytest tests/test_wiki_extract_concepts.py -k validator -v
# expect: 8 passed

pytest tests/ -q
# expect: ≥ 410 passed

mypy --strict scripts/wiki_skills/wiki_extract_concepts.py

# Manually inspect envelope shape:
python -c "
from scripts.wiki_skills.wiki_extract_concepts import _validate_candidates_schema
try:
    _validate_candidates_schema([{'slug':'x','name':'X','definition':'d','source_quote':'q','source_span':'L1-L2','entity_type':'concept','evil':'leak-me'}])
except Exception as e:
    assert getattr(e, 'error', None) == 'UNKNOWN_FIELD'
    assert getattr(e, 'field', None) == 'evil'
    assert 'leak-me' not in str(e)
    print('OK: envelope has structured attrs, no content leak')
"
```

## Rollback

Revert the edits. Test count drops back to 402 (post-01 baseline per PLAN §2).

## Notes

- The `ExtractionParseError` extension is intentionally additive (default-`None` attrs) so v2 raises that pass a single string still work. The v2 raises die in 003-v3-06 when `extract_concepts_llm` is deleted.
- Optional quote-in-body check defaults ON. Operator who knows the orchestrator produces approximate quotes can opt out via env var; this is documented in `.agent/skills/concept-extraction/SKILL.md` (003-v3-07).
