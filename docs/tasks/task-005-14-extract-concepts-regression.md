# Task 005-14: extract-concepts Class A flag regression guard (R-4.6)

## Use Case Connection
- UC-14 (durability — applied candidate stays candidate)

## Task Goal
Pin the invariant that `wiki-extract-concepts apply` writes `is_candidate: true` into Class A frontmatter, and add a regression test that a freshly-applied candidate survives `wiki-reindex --full` as a candidate (closing the loop with 005-02).

## Changes Description

### Changes in Existing Files
#### File: `scripts/wiki_skills/wiki_extract_concepts.py`
- Confirm `write_concept_page` frontmatter pins `"is_candidate": True` + `tags: [..., "candidate"]` (already present at ~line 653-654). No behavior change expected; add an inline comment referencing R-4.6 + the 005-02 read-side.

### Test Cases
### Regression / Integration (`tests/test_wiki_extract_concepts.py` or `tests/test_reindex.py`)
1. **TC-REG-01:** run `apply` on a candidates fixture → the written `_concepts/<slug>.md` has `is_candidate: true` in frontmatter.
2. **TC-REG-02:** then run `reindex_full` on that vault → the `entities` row is `is_candidate == 1` (round-trip preserved — depends on 005-02).
3. **TC-REG-03 (guard):** an audit-style assertion that `write_concept_page` source still contains the `is_candidate` pin (mirrors the existing load-bearing-grep guard pattern from v3.1).

## Acceptance Criteria
- [ ] `apply` writes `is_candidate: true` to Class A frontmatter (pinned + guarded).
- [ ] Applied candidate survives `reindex --full` as `is_candidate=1`.
- [ ] `mypy --strict` clean; regression green.

## Notes
Regression-only bead (the pin already exists from TASK 003 v3.1). Depends on 005-02. No stub phase (no new code surface beyond a comment + tests).
