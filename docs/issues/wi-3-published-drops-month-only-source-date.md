---
id: WI-3
type: known-issue
status: fixed
opened_at: 2026-07-09
closed_at: 2026-07-09
category: robustness
severity: SEV-4
slug: wi-3-published-drops-month-only-source-date
---

# wiki-import: month-precision source date (`YYYY-MM`) has no valid `published` slot → publication date lost

- **Symptom**: `prepare` reliably extracts a month-precision publication date for arXiv (`date: "2025-10"`, derived from the arXiv id) and similar sources (ECB, working papers). But the REASON schema's `published` is typed `YYYY-MM-DD | null`, so a month-only value can't be represented without fabricating a day — it gets set to `null`, and the filed note ends up with no publication date at all (only `Created`/`Updated` = the import timestamp). Surfaced 2026-07-09 importing `arxiv.org/abs/2510.08369` (`date: "2025-10"` → `published: null`).
- **Root cause**: `published` accepts only full `YYYY-MM-DD`; and `apply` does not fall back to `prepare`'s already-extracted `date` when the note JSON's `published` is null.
- **Affected components**: `skills/wiki-import/references/reason-contract.md` (`published` field type); note-assembly in `scripts/wiki_skills/wiki_import_article/_authoring.py`; `prepare` date extraction in `scripts/wiki_skills/wiki_import_article/_fetch.py` / `_detect.py`.
- **Fix plan**:
  1. Accept partial dates (`YYYY`, `YYYY-MM`) in `published` and normalize/store them (e.g. keep the partial, or pad to `-01` while retaining a precision marker).
  2. Have `apply` fall back to `prepare`'s `date` for `published` when the note JSON leaves it null, so the extracted publication date isn't silently dropped.
- **Note**: low impact for `summary`/`article` notes (non-temporal), but publication date is genuinely useful provenance and would matter if a typed knowledge page (with `--as-of` semantics) is ever imported this way.
- **Resolution (2026-07-09, TASK 055)**: both fix-plan items shipped.
  1. `skills/wiki-import/references/reason-contract.md` now types `published` as
     `YYYY | YYYY-MM | YYYY-MM-DD | null` and tells the REASON step to keep the precision the source gives
     (do NOT fabricate a day). `_authoring.assemble_note` already passes `published` through verbatim
     (`_fm_scalar` + `"`→`'`), so a `2025-10` value renders cleanly into both the `published:` frontmatter and
     the source provenance line.
  2. `wiki-import apply` gained `--published <prepare.date>`; when the note JSON leaves `published` null/blank,
     `apply` backfills from it (a note-authored value of any precision still wins). Plumbed through the SKILL +
     workflow docs. Non-string note values are coerced safely (`str(... or "")`). `published` is stored only in
     `frontmatter_json` and is not date-parsed by the indexer/`--as-of`, so a partial value breaks nothing.
     Tests: `test_wi3_apply_published_falls_back_to_source_date`, `test_wi3_note_published_wins_over_source_date`,
     `test_wi3_no_published_and_no_fallback_omits_field` (`tests/test_import_article_apply.py`).
