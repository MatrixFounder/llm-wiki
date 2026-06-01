# task-016-03 — Extract `_validation.py`

**Parent:** TASK 016. **Depends on:** 016-02. **RTM:** R-016-4a.

## Goal
Move the validation/sanitization leaf. Depends only on `_errors` (+ `_common`). **None of
these symbols is monkeypatched**, so they move freely and are re-exported from the facade.

## Context
Move (verbatim) from `__init__.py`:
- Validators: `_path_is_absolute`, `_validate_source_hash`, `_validate_orchestrator_id`,
  `_validate_candidates_schema`.
- Sanitizers: `_sanitize_name`, `_sanitize_definition`, `_preflight_sanitize`.
- `classify_candidates`, `_parse_source_span`.
- Constants/regex: `_SOURCE_SPAN_RE`, `_SLUG_RE`, `_ALLOWED_ENTITY_TYPES`, `_SOURCE_HASH_RE`,
  `_ORCHESTRATOR_ID_RE`, `_REQUIRED_CANDIDATE_KEYS`, `_CANDIDATE_COUNT_MIN/MAX`, `_FIELD_CAPS`,
  `_SPAN_REGEX`, `_NAME_ALLOWLIST`.
> **`_path_is_absolute` canonical home = `_validation` (PINNED — plan-reviewer #1).** It has
> three callers across two destinations: the facade (`prepare`@1158, `apply`@1767) AND
> `_load_candidates`@1494 (which moves to `_sourcing` in 016-04). Per the §2.1 DAG
> `_validation` is a LOWER leaf than `_sourcing`, so the only non-cycling choice is to define
> `_path_is_absolute` ONCE in `_validation`; `_sourcing` does `from ._validation import
> _path_is_absolute` and the facade re-exports it from `_validation`. Do NOT co-locate it in
> `_sourcing` (that would invert the DAG if any validator ever needs it).
> **`_format_source_quote_block` is NOT moved here** — it lands in `_pages` (016-05) per §2.1
> (its only caller is `write_concept_page`); the TASK §3.1 dual-listing is resolved to `_pages`.

## Steps
1. Create `_validation.py` with `from ._errors import ExtractionParseError` + the moved
   functions/constants (verbatim). Imports: stdlib `re`, `from scripts.wiki_skills._common import sanitize_markdown_text` (as used by `_sanitize_definition`).
2. In `__init__.py`, delete the moved defs and `from ._validation import *`-style explicit
   re-export of every moved public+private name the facade/other modules use.
3. Verify `_pages` (016-05) + `_db` (016-06) will import `_sanitize_*`/`_parse_source_span`
   from `_validation` (not the facade) — acyclic.
4. Per-bead gate (the candidate-schema + sanitizer + classify tests must stay green).

## Acceptance
- ✅ `_validation.py` imports only `_errors` + `_common` + stdlib (no facade import).
- ✅ All candidate-validation / sanitization / `classify_candidates` tests green unmodified.
- ✅ Full suite green; mypy strict clean.

## Files
- `scripts/wiki_skills/wiki_extract_concepts/_validation.py` (new)
- `scripts/wiki_skills/wiki_extract_concepts/__init__.py` (delete defs + import)
