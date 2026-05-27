# Task 003-05: `classify_candidates` — de-duplication classifier

## Meta

- **Bead ID**: `task-003-05-dedup-classifier`
- **Slug**: `dedup-classifier`
- **Maps to**: Issue **I-7.5**; RTM row **R-34**.
- **Depends on**: task-003-01 (helper stub exists), task-003-04 (LLM output is input).
- **Estimated time**: 0.25 day
- **Priority**: High (gates concept-page write — only `create` items go to 003-06)

## Use Case Connection

- **UC-08 step 7 (classify half)**: "System: Validates LLM response JSON; classifies into `create` / `mention` lists."
- **UC-08 alternative A1**: concept already exists as confirmed — slug match → `mention` action, no concept page written, no entity downgrade.

## Task Goal

Replace the `NotImplementedError` stub in `wiki_extract_concepts.py::classify_candidates(llm_results, known_slugs) -> tuple[list[dict], list[dict]]` with a slug-set diff:

- For each LLM result item, check if `item["slug"]` is in `known_slugs` (set built from `load_known_entities` output).
- If yes → append to `mention_list` (the entity already exists; we'll add a ref but not create a page).
- If no → append to `create_list` (novel concept; needs concept-page write + entity row insert).
- Annotate each item with `action="mention"` or `action="create"` in-place so the manifest builder (003-10) can use it.

## Stub-First Plan

**Phase 1 — Red test on stub**:

1. Add to `tests/test_wiki_extract_concepts.py`:
   - `test_classify_candidates_splits_known_and_novel`:
     - `known_slugs = {"alpha", "beta"}`
     - `llm_results = [{"slug":"alpha",...}, {"slug":"gamma",...}, {"slug":"beta",...}, {"slug":"delta",...}]`
     - Initial (stub): expect `NotImplementedError`.
     - After Phase 2: `create_list` has gamma+delta with `action="create"`; `mention_list` has alpha+beta with `action="mention"`.
   - `test_classify_candidates_empty_input` (Phase 2):
     - `llm_results=[]`, `known_slugs=set()` → returns `([], [])`.
   - `test_classify_candidates_all_known` (Phase 2):
     - All 3 LLM items are in known_slugs → `create_list=[]`, `mention_list` has all 3.
2. Run pytest — Red.

**Phase 2 — Logic**:

1. Replace the body:
   ```python
   def classify_candidates(
       llm_results: list[dict[str, Any]],
       known_slugs: set[str],
   ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
       """Split LLM-extracted candidates into create-list and mention-list.

       Each item is annotated with action="create" or action="mention" for the
       manifest builder. (R-34: de-dup at extraction time.)
       """
       create_list: list[dict[str, Any]] = []
       mention_list: list[dict[str, Any]] = []
       for item in llm_results:
           # Defensive copy so callers don't mutate the original
           annotated = {**item}
           if item["slug"] in known_slugs:
               annotated["action"] = "mention"
               mention_list.append(annotated)
           else:
               annotated["action"] = "create"
               create_list.append(annotated)
       return create_list, mention_list
   ```
2. Unskip Phase-2 tests; run pytest — Green.

## Changes Description

### New Files

- None.

### Changes in Existing Files

#### File: `scripts/wiki_skills/wiki_extract_concepts.py`

- Replace `classify_candidates` stub body with the slug-set diff logic.

#### File: `tests/test_wiki_extract_concepts.py`

- Add 3 unit tests: split known/novel, empty input, all known.

### Component Integration

- `create_list` consumed by 003-06 (concept-page writer) — one page per item.
- `mention_list` items skip the page-writer; both lists feed 003-08 (entity-refs upsert) — both `create` and `mention` get a `page_entity_refs` row.
- Caller pattern in `main()`:
  ```python
  llm_results = extract_concepts_llm(...)
  known_slugs = {e["slug"] for e in known_entities}
  create_list, mention_list = classify_candidates(llm_results, known_slugs)
  for cand in create_list:
      write_concept_page(args.vault_root, cand, args.source_page, today)
      upsert_extracted_entity(repo, args.vault, cand, args.source_page, today)
  all_refs = create_list + mention_list
  upsert_entity_refs(repo, args.vault, args.source_page, source_project, all_refs)
  ```

## Files Touched (explicit list)

- `scripts/wiki_skills/wiki_extract_concepts.py` (modified — 1 stub replacement)
- `tests/test_wiki_extract_concepts.py` (modified — add 3 tests)

## Test Surface

- **New**: 3 unit tests:
  - `test_classify_candidates_splits_known_and_novel`
  - `test_classify_candidates_empty_input`
  - `test_classify_candidates_all_known`

## Acceptance Criteria

- [ ] **R-34(b)**: LLM items with `slug` matching an existing entity → `action="mention"` (ref only).
- [ ] **R-34(c)**: Items with novel `slug` → `action="create"`.
- [ ] **R-34(d)**: Classification annotated on each item for the manifest's `extraction_summary` field (manifest builder 003-10 reads `action`).
- [ ] All 3 unit tests pass.
- [ ] `mypy --strict` clean.
- [ ] Full sweep `pytest tests/ -q` still green.

## Verification

```bash
pytest tests/test_wiki_extract_concepts.py -v -k "classify"
pytest tests/ -q
mypy --strict scripts/wiki_skills/wiki_extract_concepts.py
```

## Rollback

Revert `classify_candidates` to `NotImplementedError`, remove the 3 tests. Downstream beads (003-06, 003-07b, 003-08) will fail until restored.

## Notes

- This bead is intentionally tiny (~10 LoC) — the classifier is set-membership-only. All the heavy lifting (LLM call, page write, entity upsert) lives in neighboring beads.
- Future bead (R-5 / aliases) will extend this to check `known_aliases` too. For R-3 it's slug-only.
- The `**item` defensive-copy is small overhead but means callers can't surprise-mutate the LLM output through the classifier's return value.
