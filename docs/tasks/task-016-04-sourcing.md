# task-016-04 — Extract `_sourcing.py`

**Parent:** TASK 016. **Depends on:** 016-03. **RTM:** R-016-4b, R-016-7b.

## Goal
Move the source-IO / path-resolution leaf. Depends only on `_errors` (+ stdlib, `layout`,
`security`). None of these is monkeypatched.

## Context
Move (verbatim) from `__init__.py`:
- `_FileTooLargeError`, `_read_file_bounded`.
- `_resolve_source_inside_sources`, `_all_concepts_dirs`, `_derive_source_project`.
- `_load_candidates`.
- `_path_is_absolute` is NOT moved here — it is PINNED to `_validation` (016-03). `_sourcing`
  does `from ._validation import _path_is_absolute` (used by `_load_candidates`). Do NOT duplicate.
- Byte caps: `_MAX_SOURCE_BODY_BYTES`, `_MAX_CANDIDATES_BYTES`.
- `_SOURCE_KIND` (used by source resolution).

> **R-016-7b**: `tests/test_slug_strategy.py:73` does
> `from scripts.wiki_skills.wiki_extract_concepts import _derive_source_project`. After the
> move, `__init__.py` MUST re-export `_derive_source_project` so that import still resolves —
> **NO test edit** (the facade re-export is the contract). Verify this test stays green
> unmodified.

## Steps
1. Create `_sourcing.py` with `from ._errors import ExtractionParseError` (+ `from ._validation import _path_is_absolute` if applicable) + the moved symbols (verbatim). Imports: `os`, `hashlib`, `pathlib`, `scripts.wiki_index.layout` (SOURCES/CONCEPTS subdirs), `scripts.wiki_index.security` (`validate_inside_vault`, `PathTraversalError`).
2. In `__init__.py`, delete the moved defs and add an explicit `from ._sourcing import …` re-export covering `_derive_source_project` + everything the facade/leaves use.
3. Per-bead gate, with an EXPLICIT run of `tests/test_slug_strategy.py` (the `_derive_source_project` facade-import) — must pass unmodified.

## Acceptance
- ✅ `_sourcing.py` imports only `_errors`/`_validation`(for `_path_is_absolute`)/stdlib/`layout`/`security`.
- ✅ `from …wiki_extract_concepts import _derive_source_project` still resolves (test_slug_strategy green, NO edit).
- ✅ Source-resolution / candidate-load / bounded-read tests green; full suite green; mypy strict clean.

## Files
- `scripts/wiki_skills/wiki_extract_concepts/_sourcing.py` (new)
- `scripts/wiki_skills/wiki_extract_concepts/__init__.py` (delete defs + import)
