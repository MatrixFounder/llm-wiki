# Task 006-03: reindex entity-name fallback title→name→slug (L-8)

## Ledger id: L-8

## Goal
`reindex_full` registers `entities.name = updated_fm.get("title", slug)`, but
concept pages (from `write_concept_page`) emit `name:` not `title:` → display
names are lost (become the slug). Fall back `title → name → slug`.

## Changes
### `scripts/wiki_index/reindex.py` (entity-registration block)
- Replace `updated_fm.get("title", out.page_slug)` with
  `updated_fm.get("title") or updated_fm.get("name") or out.page_slug`.

## Test cases (`tests/test_reindex_is_candidate.py` or a new file)
1. `_concepts/foo.md` with `name: "Foo Bar"` and **no** `title:` → after `reindex_full`, `entities.name == "Foo Bar"` (was `"foo"`).
2. `title:` present → still wins (precedence preserved).
3. neither present → falls back to slug.

## Acceptance
- [ ] Name fallback order title→name→slug.
- [ ] Name-only concept round-trips with its display name.
- [ ] `pytest tests/` green; `mypy --strict` clean.

## Notes
Independent bead (no schema dep). Fixes the quirk found during TASK 005 005-16 acceptance.
