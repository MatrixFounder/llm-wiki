# Task 003-12: Unit-test consolidation + patch-target audit

## Meta

- **Bead ID**: `task-003-12-unit-tests`
- **Slug**: `unit-tests`
- **Maps to**: Issue **I-7.12**; RTM row **R-43**.
- **Depends on**: task-003-01..task-003-11 (consolidates the per-bead unit tests that landed inside each implementation bead's Phase 1).
- **Estimated time**: 0.5 day
- **Priority**: High (gates the integration test 003-13 and the acceptance gate 003-14)

## Use Case Connection

- **UC-08 + UC-09 main paths**: every code path exercised by at least one unit test consolidated here.

## Task Goal

This bead is a **consolidation gate**, not new logic. Per Stub-First (PLAN.md §3), each code-bearing bead (003-03..003-11) already landed its own unit tests in `tests/test_wiki_extract_concepts.py`. This bead:

1. **Audits patch targets** — confirms every `unittest.mock.patch(...)` in the file targets `scripts.wiki_skills.wiki_extract_concepts.<name>` and NOT `scripts.wiki_skills._manifest_consumer.<name>` (Risk R-2 in PLAN.md §6).
2. **Confirms the in-memory SQLiteRepository fixture** is the canonical test fixture, used consistently across all repo-touching tests (pattern reused from Phase 3a).
3. **Adds the `validate_manifest` live-import test** — exercises the full Decision-15 + Decision-16 contract by calling `validate_manifest` directly on a fixture manifest.
4. **Confirms test coverage** for all 9 helper functions: each has at least one Phase-2 happy-path test + at least one error-path test (where applicable).
5. **Adds missing edge cases** discovered during consolidation review.

## Stub-First Plan

**Phase 1 — n/a (this is a consolidation bead; no new stubs).**

**Phase 2 — Direct audit + additions**:

1. **Patch-target audit**:
   ```bash
   grep -rn "patch.*_manifest_consumer\." tests/test_wiki_extract_concepts.py
   # MUST be empty
   grep -rn "patch.*wiki_extract_concepts\." tests/test_wiki_extract_concepts.py
   # MUST contain all in-process dispatch patches
   ```
   If any test patches `_manifest_consumer.*`, file a fix.

2. **In-memory fixture canonicalization**: ensure `tests/conftest.py` (or similar) defines a fixture:
   ```python
   @pytest.fixture
   def in_memory_repo() -> Iterator[SQLiteRepository]:
       repo = SQLiteRepository(db_path=":memory:")
       repo.apply_schema()
       yield repo
       repo.close()
   ```
   Refactor any test that builds its own in-memory repo to use this fixture instead.

3. **`validate_manifest` live-import test** — add (if not present after 003-10):
   ```python
   def test_validate_manifest_accepts_extract_concepts_manifest(tmp_path):
       """Live contract check: a manifest built by this skill passes the neutral consumer."""
       from scripts.wiki_skills._manifest_consumer import validate_manifest
       manifest = build_manifest(
           vault_id="vid",
           source_slug="src",
           source_hash="hash",
           create_list=[{"slug":"foo","name":"Foo","entity_type":"concept","action":"create",
                         "source_quote":"q","source_span":"L1-L2","file_write_action":"created"}],
           mention_list=[],
           log_event={"event_type":"ingest","subject":"S"},
           vault_root=tmp_path,
       )
       # Ensure the _concepts/foo.md path exists so validate_manifest's path-traversal
       # check has something to inspect
       (tmp_path / "_concepts").mkdir()
       (tmp_path / "_concepts" / "foo.md").write_text("# Foo")
       validate_manifest(manifest, "vid", tmp_path)  # MUST NOT raise
   ```

4. **Coverage matrix** — confirm each helper has both happy-path and error-path coverage:

   | Helper | Happy-path test | Error-path test |
   |---|---|---|
   | `load_known_entities` | 003-03: `test_load_known_entities_returns_aggregated_aliases` | 003-03: `test_load_known_entities_empty_vault` |
   | `extract_concepts_llm` | 003-04: `test_extract_concepts_llm_parses_valid_json` | 003-04: `test_..._raises_on_malformed_json` + `..._on_api_error` |
   | `classify_candidates` | 003-05: `test_classify_candidates_splits_known_and_novel` | 003-05: `test_classify_candidates_empty_input` |
   | `write_concept_page` | 003-06: `test_..._writes_file_with_frontmatter` | 003-06: `test_..._rejects_path_outside_vault` |
   | `upsert_extracted_entity` | 003-07b: `test_..._returns_created_for_new_row` | 003-07b: `test_..._skips_confirmed` |
   | `upsert_entity_refs` | 003-08: `test_..._parses_line_spans` | 003-08: `test_..._rejects_malformed_span` |
   | `check_idempotency` | 003-09: `test_..._hash_match` | 003-09: `test_..._hash_mismatch` |
   | `build_manifest` | 003-10: `test_..._passes_validate_manifest` | (no error path — assembly always succeeds for valid inputs) |
   | `dispatch_to_indexer` | 003-11: `test_..._calls_validate_then_index` | 003-11: `test_..._propagates_wiki_ingest_error` |

   If any cell is empty (and shouldn't be), add the missing test here.

5. **In-process dispatch mock test** — confirm 003-11's tests cover both `--ingest` and no-`--ingest` paths at the `main()` level (not just the function in isolation).

## Changes Description

### New Files

- None (consolidation only).

### Changes in Existing Files

#### File: `tests/test_wiki_extract_concepts.py`

- (Optional) Refactor inconsistent fixture usage to the canonical `in_memory_repo` fixture.
- Add the `test_validate_manifest_accepts_extract_concepts_manifest` if not present.
- Add any missing edge-case tests discovered during the coverage-matrix audit.

#### File: `tests/conftest.py`

- (Optional) Add or canonicalize the `in_memory_repo` fixture if not already present in a sibling pattern.

## Test Surface

- **New (consolidation)**: ~1-3 tests added during the audit. Most coverage is reused from 003-03..003-11.

## Acceptance Criteria

- [ ] **R-43(a)**: LLM prompt construction tested (003-04 — verified present).
- [ ] **R-43(b)**: manifest schema round-trip + `validate_manifest` acceptance — **live import test present** in this bead.
- [ ] **R-43(c)**: idempotency short-circuit tested (003-09 — verified present).
- [ ] **R-43(d)**: in-process dispatch path — patch at `scripts.wiki_skills.wiki_extract_concepts.index_from_manifest`; assert exactly-once call when `--ingest` set; assert zero calls when absent (003-11 — verified present).
- [ ] **Patch-target lock audit passes**: `grep -rn "patch.*_manifest_consumer\." tests/` returns empty.
- [ ] **Coverage matrix complete**: every helper has at least one happy-path and (where applicable) one error-path test.
- [ ] **In-memory fixture canonicalized**: every test that needs a repo uses `in_memory_repo` fixture (or documents a deliberate exception).
- [ ] All tests in `tests/test_wiki_extract_concepts.py` pass.
- [ ] `mypy --strict tests/` clean (or test-suite-specific mypy config respected).

## Verification

```bash
# Patch-target audit
grep -rn "patch.*_manifest_consumer\." tests/ ; echo "exit=$? (1 = empty, expected)"

# Coverage check
pytest tests/test_wiki_extract_concepts.py -v --cov=scripts.wiki_skills.wiki_extract_concepts \
       --cov-report=term-missing | tail -30

# Full sweep
pytest tests/ -q
```

## Rollback

Revert any new tests added during this bead; the per-bead tests from 003-03..003-11 still cover the surface (the consolidation is a polish step). Patch-target audit failures can be re-fixed.

## Notes

- **Patch-target drift is the #1 silent-failure risk** for this task (Risk R-2 in PLAN.md). Make the grep check a mandatory step in the bead's checklist.
- The `tests/conftest.py` fixture canonicalization is **optional** — if the existing per-bead patterns are clean enough, no need to refactor. Document the decision in the bead's PR description.
- `--cov` coverage report is a good sanity check but not a hard gate (project may or may not have `pytest-cov` configured; if absent, install in `.venv` for this bead only).
- The bead does **not** add new business-logic tests — those live in the per-bead implementation files. This bead's surface is *test hygiene* + a single live-contract test.
