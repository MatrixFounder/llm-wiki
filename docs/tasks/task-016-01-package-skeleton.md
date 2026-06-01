# task-016-01 — Convert module → package skeleton

**Parent:** TASK 016. **Depends on:** 016-00. **RTM:** R-016-1, R-016-7a (interim).

## Goal
Turn `wiki_extract_concepts.py` into the package `wiki_extract_concepts/` with the **entire
current body verbatim** in `__init__.py` (the facade), plus a `__main__.py` so `python -m`
still works. ZERO body edits — pure file relocation. Subsequent beads carve leaves OUT of
`__init__.py`; the orchestration layer + 8 lock symbols **never leave** `__init__.py`
(facade shape A).

## Context
- `scripts/wiki_skills/wiki_extract_concepts.py` → becomes `scripts/wiki_skills/wiki_extract_concepts/__init__.py`.
- `bin/wiki-extract-concepts` + `tests/test_wiki_extract_concepts_integration.py:87` depend on `python -m`.
- `tests/test_extract_concepts_candidate_regression.py:18` `_SRC` literal → must repoint.

## Steps
1. `mkdir scripts/wiki_skills/wiki_extract_concepts` and `git mv scripts/wiki_skills/wiki_extract_concepts.py scripts/wiki_skills/wiki_extract_concepts/__init__.py` (preserves history; body unchanged).
2. Create `scripts/wiki_skills/wiki_extract_concepts/__main__.py`:
   ```python
   from __future__ import annotations
   import sys
   from . import main
   if __name__ == "__main__":
       sys.exit(main())
   ```
3. Repoint the file-path-literal test (R-016-7a interim): in
   `tests/test_extract_concepts_candidate_regression.py:18` change `_SRC` to
   `… / "scripts" / "wiki_skills" / "wiki_extract_concepts" / "__init__.py"` (assertions
   unchanged — `write_concept_page` still lives in `__init__.py` at this bead).
4. Run the per-bead gate (full pytest + mypy + `-m --help`).

## Acceptance
- ✅ `import scripts.wiki_skills.wiki_extract_concepts as wec` works; every public + the 8 lock names resolve on `wec`.
- ✅ `python -m scripts.wiki_skills.wiki_extract_concepts --help` exits 0 (`{prepare,apply}`).
- ✅ Full suite green (incl. lock/canary/perf/integration); mypy strict clean.
- ✅ Old `.py` gone; package dir present.

## Files
- `scripts/wiki_skills/wiki_extract_concepts/__init__.py` (moved verbatim)
- `scripts/wiki_skills/wiki_extract_concepts/__main__.py` (new)
- `tests/test_extract_concepts_candidate_regression.py` (`_SRC` repoint — interim)
