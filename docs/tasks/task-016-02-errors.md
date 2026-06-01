# task-016-02 — Extract `_errors.py`

**Parent:** TASK 016. **Depends on:** 016-01. **RTM:** R-016-4e.

## Goal
Move the error/exception leaf out of the facade. `_errors` is the dependency **sink** (no
internal imports) — extract it first so later leaves can import it.

## Context
- Functions/classes to move (verbatim) from `wiki_extract_concepts/__init__.py`:
  `ExtractionParseError` (the exception class) and `_envelope_from_parse_error`.
- Note: `WikiIngestError` is NOT moved — it is re-exported from `_manifest_consumer` and
  must keep its facade identity (`test_module_imports_neutral_manifest_consumer`).

## Steps
1. Create `scripts/wiki_skills/wiki_extract_concepts/_errors.py` with `from __future__ import
   annotations` + the moved `ExtractionParseError` + `_envelope_from_parse_error` (verbatim).
2. In `__init__.py`, delete those definitions and add `from ._errors import ExtractionParseError, _envelope_from_parse_error`.
3. Confirm no other moved-out symbol is referenced before its import; keep `__init__` import block ordered.
4. Per-bead gate.

## Acceptance
- ✅ `_errors.py` has no internal package imports (sink).
- ✅ `wec.ExtractionParseError` still resolves. **Identity contract**: unlike `WikiIngestError`
  (which must stay `is`-identical to `_manifest_consumer`'s per AC-016-3), `ExtractionParseError`
  is package-owned — the contract is simply that EVERY raiser/catcher imports the single
  `_errors` definition (no re-definition in any leaf).
- ✅ Full suite green; mypy strict clean.

## Files
- `scripts/wiki_skills/wiki_extract_concepts/_errors.py` (new)
- `scripts/wiki_skills/wiki_extract_concepts/__init__.py` (delete defs + add import)
