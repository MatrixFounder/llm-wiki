# task-016-05 — Extract `_pages.py` (+ final `_SRC` repoint)

**Parent:** TASK 016. **Depends on:** 016-04. **RTM:** R-016-4d, R-016-7a (final).

## Goal
Move the concept-page-writing leaf. Depends on `_validation` (`_sanitize_name`,
`_sanitize_definition`, `_SLUG_RE`, `_SOURCE_SPAN_RE`) + `_errors`. Not monkeypatched.

## Context
Move (verbatim) from `__init__.py`:
- `write_concept_page`, `_format_source_quote_block`.
- The name allowlist if exclusively used here (else it stays in `_validation`).
> **R-016-7a (final)**: `write_concept_page` now leaves `__init__.py` → `_pages.py`, so
> `tests/test_extract_concepts_candidate_regression.py` `_SRC` (set to `__init__.py` in
> 016-01) MUST be repointed to `wiki_extract_concepts/_pages.py`. The pinned assertions
> (`'"is_candidate": True'`, `'"tags": ["concept", "candidate"]'`) are unchanged — pure path move.

## Steps
1. Create `_pages.py` with `from ._validation import _sanitize_name, _sanitize_definition, _SLUG_RE, _SOURCE_SPAN_RE` + `from ._errors import ExtractionParseError` + the moved `write_concept_page` + `_format_source_quote_block` (verbatim). Imports: `os`, `tempfile`, `pathlib`, `scripts.wiki_skills._common` (`atomic_write_text`, `sanitize_markdown_text`), `scripts.wiki_index.layout`/`security` as used.
2. In `__init__.py`, delete the moved defs and add `from ._pages import write_concept_page, _format_source_quote_block`.
3. Repoint `_SRC` in `tests/test_extract_concepts_candidate_regression.py:18` → `… / "wiki_extract_concepts" / "_pages.py"`.
4. Per-bead gate, with an EXPLICIT run of `tests/test_extract_concepts_candidate_regression.py` (the pinned strings must be found in `_pages.py`).

## Acceptance
- ✅ `_pages.py` imports only `_validation`/`_errors`/stdlib/`_common`/`layout`/`security`.
- ✅ `test_extract_concepts_candidate_regression.py` green (the `is_candidate`/`tags` pins found in `_pages.py`).
- ✅ Full suite green; mypy strict clean.

## Files
- `scripts/wiki_skills/wiki_extract_concepts/_pages.py` (new)
- `scripts/wiki_skills/wiki_extract_concepts/__init__.py` (delete defs + import)
- `tests/test_extract_concepts_candidate_regression.py` (`_SRC` repoint — final)
