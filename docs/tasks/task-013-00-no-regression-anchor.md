# task-013-00 — No-regression golden anchor

**Parent:** TASK 013 `wiki-search-metadata-filter`. **Type:** regression tripwire.
**Depends on:** nothing. **Must stay green through 013-01..03.**

## Goal
Lock that `wiki-search` output is **byte-identical** when no metadata flag is
passed, so the 013-01/02 changes cannot silently alter existing search behaviour
(R-MF-9).

## Stub-First
This bead is test-only (the "golden snapshot" pattern from 012-00).

1. Build/locate a small fixture vault with frontmatter-bearing pages (reuse an
   existing `tests/fixtures/*` vault or a tmp dev-project vault with 2-3 issue
   files carrying `status`/`severity`).
2. Run `wiki_search.main([...])` for a representative query (JSON + markdown
   formats) and snapshot the emitted payload.
3. Assert the snapshot is reproduced exactly on current `main` (green now).

## Acceptance
- ✅ `test_no_flag_output_unchanged` green on current code (pre-013-01).
- ✅ Remains green after 013-01 and 013-02 (the tripwire).
- ✅ All pre-existing `tests/test_wiki_search*` continue to pass.

## Files
- `tests/test_wiki_search_metadata_filter.py` (new; the no-flag anchor lives here
  alongside the later metadata-filter tests).
