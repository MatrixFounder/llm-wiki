# Task 003-08: `upsert_entity_refs` — `page_entity_refs` rows with provenance

## Meta

- **Bead ID**: `task-003-08-entity-refs-upsert`
- **Slug**: `entity-refs-upsert`
- **Maps to**: Issue **I-7.8**; RTM rows **R-38**, **R-40**.
- **Depends on**: task-003-01 (helper stub exists), task-003-07b (entity rows must exist before refs link to them).
- **Estimated time**: 0.5 day
- **Priority**: Critical (provenance is the R-38 deliverable; without it, R-3 doesn't ship)

## Use Case Connection

- **UC-08 step 9**: "Calls `repo.replace_refs(...)` for all extracted entities (create + mention) against the source page; parses `'Lstart-Lend'` → `(line_start, line_end)` integers."
- **UC-09 Scenario B**: `replace_refs` is the atomic delete-then-insert that ensures re-extraction on a changed body cleanly updates the refs.

## Task Goal

Replace the `NotImplementedError` stub in `wiki_extract_concepts.py::upsert_entity_refs(repo, vault_id, source_slug, source_project, all_candidates) -> None` with:

1. Iterate over `all_candidates` (the combined `create_list + mention_list` from 003-05).
2. For each candidate, parse `source_span="Lstart-Lend"` into `(line_start, line_end)` integers (Decision-10).
3. Build a list of ref tuples: `(entity_slug=candidate["slug"], ref_type="mentioned", source_quote=candidate["source_quote"], line_start=line_start, line_end=line_end, trust_level="medium")`.
4. Call `repo.replace_refs(vault_id, source_slug, source_project, refs_list)` — Phase 3a already provides this method; it does atomic DELETE+INSERT keyed on `(vault_id, page_slug, project)`.

## Stub-First Plan

**Phase 1 — Red tests on stub**:

1. Add to `tests/test_wiki_extract_concepts.py`:
   - `test_upsert_entity_refs_parses_line_spans` (Phase 1):
     - Mock `repo.replace_refs`.
     - Call with candidates having `source_span="L12-L18"` and `source_span="L5-L5"`.
     - On stub: `NotImplementedError`. After Phase 2: assert `replace_refs` called once with a list containing `line_start=12, line_end=18` and `line_start=5, line_end=5`.
   - `test_upsert_entity_refs_rejects_malformed_span` (Phase 2):
     - Candidate with `source_span="line 12 to 18"` (wrong format).
     - Assert raises `ExtractionParseError` or similar (consistent with Decision-10 regex `^L\d+-L\d+$`).
   - `test_upsert_entity_refs_sets_trust_level_medium` (Phase 2):
     - Verify each ref tuple passed to `replace_refs` has `trust_level="medium"`.
   - `test_upsert_entity_refs_processes_both_create_and_mention` (Phase 2):
     - Mix of `action="create"` and `action="mention"` candidates → all get refs (4 candidates → 4 refs).
   - `test_upsert_entity_refs_filters_by_vault` (Phase 2):
     - Verify `replace_refs` called with `vault_id` predicate.
2. Run pytest — Red.

**Phase 2 — Logic**:

1. Add a private helper for parsing the line-span format:
   ```python
   import re
   _SPAN_REGEX = re.compile(r"^L(\d+)-L(\d+)$")

   def _parse_source_span(span: str) -> tuple[int, int]:
       """Parse 'Lstart-Lend' format (Decision-10) into (line_start, line_end)."""
       m = _SPAN_REGEX.match(span)
       if not m:
           raise ExtractionParseError(f"Malformed source_span (expected 'L<start>-L<end>'): {span!r}")
       start, end = int(m.group(1)), int(m.group(2))
       if end < start:
           raise ExtractionParseError(f"source_span end before start: {span!r}")
       return start, end
   ```
2. Implement the upserter:
   ```python
   def upsert_entity_refs(
       repo: IndexRepository,
       vault_id: str,
       source_slug: str,
       source_project: str | None,
       all_candidates: list[dict[str, Any]],
   ) -> None:
       """Replace page_entity_refs for the source page with the new extraction.

       Uses repo.replace_refs(...) atomic delete+insert semantics so re-extraction
       on a changed body doesn't leave stale refs (UC-09 Scenario B).
       """
       refs: list[dict[str, Any]] = []
       for cand in all_candidates:
           line_start, line_end = _parse_source_span(cand["source_span"])
           refs.append({
               "entity_slug": cand["slug"],
               "ref_type": "mentioned",
               "source_quote": cand["source_quote"],
               "line_start": line_start,
               "line_end": line_end,
               "trust_level": "medium",
           })
       repo.replace_refs(
           vault_id=vault_id,
           page_slug=source_slug,
           project=source_project,
           refs=refs,
       )
   ```
3. Unskip Phase-2 tests; run pytest — Green.

## Changes Description

### New Files

- None.

### Changes in Existing Files

#### File: `scripts/wiki_skills/wiki_extract_concepts.py`

- Add private helper `_parse_source_span(span) -> tuple[int, int]` with regex `^L\d+-L\d+$` (Decision-10).
- Replace `upsert_entity_refs` stub body with the logic above.

#### File: `tests/test_wiki_extract_concepts.py`

- Add 5 unit tests.

### Component Integration

- Sole writer of `page_entity_refs` rows in the extraction skill. Called after 003-07b (entity rows must exist for FK integrity — though `page_entity_refs` doesn't enforce FK in SCHEMA-v2, the logical ordering is required).
- `repo.replace_refs(...)` is the Phase 3a-shipped atomic-replace method. Signature inherited; no DAL extension needed.

## Files Touched (explicit list)

- `scripts/wiki_skills/wiki_extract_concepts.py` (modified — 1 stub replacement + 1 private helper)
- `tests/test_wiki_extract_concepts.py` (modified — add 5 tests)

## Test Surface

- **New**: 5 unit tests:
  - `test_upsert_entity_refs_parses_line_spans`
  - `test_upsert_entity_refs_rejects_malformed_span`
  - `test_upsert_entity_refs_sets_trust_level_medium`
  - `test_upsert_entity_refs_processes_both_create_and_mention`
  - `test_upsert_entity_refs_filters_by_vault`

## Acceptance Criteria

- [ ] **R-38(a)**: each extracted entity (both `create` and `mention`) produces one `page_entity_refs` row.
- [ ] **R-38(b)**: `trust_level='medium'` set on every row.
- [ ] **R-38(c)**: `source_quote` populated from LLM output (10-50 words — caller validates this in 003-04; this bead passes through).
- [ ] **R-38(d)**: `line_start` + `line_end` integer columns populated by parsing `"Lstart-Lend"` (Decision-10 / verified by `test_upsert_entity_refs_parses_line_spans`).
- [ ] **R-38(e)**: `ref_type='mentioned'` on every row.
- [ ] **R-38(f)**: `repo.replace_refs(...)` atomic semantics used (delete + insert in one transaction).
- [ ] **R-40(a)**: `vault_id` predicate present (verified by `test_upsert_entity_refs_filters_by_vault`).
- [ ] All 5 unit tests pass.
- [ ] `mypy --strict` clean.
- [ ] Full sweep `pytest tests/ -q` still green.

## Verification

```bash
pytest tests/test_wiki_extract_concepts.py -v -k "entity_refs"
pytest tests/ -q
mypy --strict scripts/wiki_skills/wiki_extract_concepts.py
```

## Rollback

Revert `upsert_entity_refs` + `_parse_source_span` to stub; remove 5 tests. Downstream (003-10 manifest builder may still ship — the manifest doesn't depend on the refs being inserted; only on the candidates list).

## Notes

- Decision-10 format (`"Lstart-Lend"`) was chosen for human readability in the LLM prompt. The parser converts to integer columns at write time so SQL queries can do range comparisons. The DB has no `source_span` column.
- The line-span regex `^L\d+-L\d+$` is the same as the validator in 003-04 (`_validate_extraction_schema`). Could share via a module-level constant; not required (DRY violation is minor — 1 line in two places).
- `replace_refs` atomic semantics handle re-extraction (UC-09 Scenario B). Without atomicity, a body-change re-run could leave stale refs from the previous extraction interleaved with new ones.
- `source_project` is typically `None` for vault-only pages. Pass through as-is; `replace_refs` handles NULL gracefully (Phase 3a contract).
