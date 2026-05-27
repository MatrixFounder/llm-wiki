# Task 003-03: `load_known_entities` — pre-extraction DB query

## Meta

- **Bead ID**: `task-003-03-load-known-entities`
- **Slug**: `load-known-entities`
- **Maps to**: Issue **I-7.3**; RTM row **R-32**.
- **Depends on**: task-003-01 (helper stub exists), task-003-07a (DAL extension — provides the repo handle even though this bead uses read-path queries directly).
- **Estimated time**: 0.25 day
- **Priority**: High (input to 003-04 LLM extraction)

## Use Case Connection

- **UC-08 step 5**: "System: Queries `entities` + `entity_aliases` for `vault_id`; serialises known-concepts list."

## Task Goal

Replace the `NotImplementedError` stub in `scripts/wiki_skills/wiki_extract_concepts.py::load_known_entities(repo, vault_id) -> list[dict]` with a real implementation that:

1. Executes `SELECT slug, name, type FROM entities WHERE vault_id = ?` plus a LEFT JOIN onto `entity_aliases` to collect aliases.
2. Aggregates results into the CONTRACT §2 known-concepts format: `[{"slug": "...", "name": "...", "aliases": [...], "type": "..."}]`.
3. Returns an empty list `[]` for a vault with no entities (R-32(c)).

The output is the input to `extract_concepts_llm` (003-04) which embeds it in the LLM prompt as the de-dup hint.

## Stub-First Plan

**Phase 1 — Red test on stub**:

1. Confirm `wiki_extract_concepts.py::load_known_entities` is still `raise NotImplementedError` from 003-01.
2. Add `tests/test_wiki_extract_concepts.py::test_load_known_entities_empty_vault`:
   - Build an in-memory `SQLiteRepository` fixture against an empty `entities` table.
   - Call `load_known_entities(repo, vault_id="test-vault")`.
   - Initial expectation: raises `NotImplementedError`.
3. Run pytest — Red.

**Phase 2 — Logic**:

1. Open `scripts/wiki_skills/wiki_extract_concepts.py`. Replace the body:
   ```python
   def load_known_entities(repo: IndexRepository, vault_id: str) -> list[dict[str, Any]]:
       """Load known entities + aliases for the vault.

       Returns CONTRACT §2 known-concepts format:
           [{"slug": "...", "name": "...", "type": "...", "aliases": [...]}]
       Empty vault → empty list (R-32c).
       """
       rows = repo.list_entities_with_aliases(vault_id)  # new repo method? or use raw SQL
       result: list[dict[str, Any]] = []
       for row in rows:
           result.append({
               "slug": row["slug"],
               "name": row["name"],
               "type": row["type"],
               "aliases": row.get("aliases", []),
           })
       return result
   ```
   - **Choice**: either add a `list_entities_with_aliases(vault_id)` method on `IndexRepository` (clean DAL extension) OR execute raw SQL via the repo's underlying connection.
   - **Recommendation**: raw SQL on the repo's `_conn` attribute, scoped tight to this caller — extending the DAL adds work and TASK.md §1.3 explicitly limits new DAL methods to `upsert_entity`. Document the choice inline with a comment referencing this note.
2. Update test:
   - `test_load_known_entities_empty_vault` — asserts `[]` returned.
   - Add `test_load_known_entities_returns_aggregated_aliases`:
     - Seed 2 entity rows and 3 alias rows (2 for one entity, 1 for the other).
     - Call `load_known_entities`.
     - Assert result length 2; assert one entry has `aliases=["alias-a", "alias-b"]`, the other `aliases=["alias-c"]`.
   - Add `test_load_known_entities_filters_by_vault`:
     - Seed entities for vault "A" and vault "B".
     - Call with `vault_id="A"` → only A's entities returned (ADR-002 §D1.1 multi-vault invariant).
3. Run pytest — Green.

## Changes Description

### New Files

- None.

### Changes in Existing Files

#### File: `scripts/wiki_skills/wiki_extract_concepts.py`

- Replace `load_known_entities` stub body with the SQL-aggregation logic above.

#### File: `tests/test_wiki_extract_concepts.py`

- Add 3 unit tests: empty vault, aggregated aliases, multi-vault filter.

### Component Integration

- Output consumed by `extract_concepts_llm` (003-04) — the list is JSON-serialized and embedded in the LLM prompt as the de-dup hint per R-32(b).

## Files Touched (explicit list)

- `scripts/wiki_skills/wiki_extract_concepts.py` (modified — replace one stub body)
- `tests/test_wiki_extract_concepts.py` (modified — add 3 tests)

## Test Surface

- **New**: 3 unit tests in `tests/test_wiki_extract_concepts.py`:
  - `test_load_known_entities_empty_vault`
  - `test_load_known_entities_returns_aggregated_aliases`
  - `test_load_known_entities_filters_by_vault`

## Acceptance Criteria

- [ ] **R-32(a)**: `SELECT slug, name FROM entities WHERE vault_id = ?` plus aliases JOIN executes BEFORE any LLM API call.
- [ ] **R-32(b)**: result serialised as `[{"slug": ..., "name": ..., "aliases": [...]}]` (matching CONTRACT §2).
- [ ] **R-32(c)**: empty vault → `[]` returned, no exception.
- [ ] Multi-vault isolation: query filters by `vault_id` predicate (verified by `test_load_known_entities_filters_by_vault`).
- [ ] All 3 unit tests pass.
- [ ] `mypy --strict scripts/wiki_skills/wiki_extract_concepts.py` clean.
- [ ] Full sweep `pytest tests/ -q` still green.

## Verification

```bash
pytest tests/test_wiki_extract_concepts.py::test_load_known_entities_empty_vault -v
pytest tests/test_wiki_extract_concepts.py::test_load_known_entities_returns_aggregated_aliases -v
pytest tests/test_wiki_extract_concepts.py::test_load_known_entities_filters_by_vault -v
pytest tests/ -q
mypy --strict scripts/wiki_skills/wiki_extract_concepts.py
```

## Rollback

Revert the `load_known_entities` body to `raise NotImplementedError` and remove the 3 new tests. The 003-04 LLM extraction bead will fail until this is restored, but that bead hasn't shipped yet so no propagation.

## Notes

- Choosing raw SQL on `repo._conn` vs. extending the DAL is a planner-level micro-decision. Recommendation in this bead: raw SQL — keeps the DAL extension surface tight (TASK.md §1.3 non-goal). If a second reader complains during code review, switch to a `list_entities_with_aliases(vault_id)` repo method.
- The output format MUST match the `known_concepts` parameter shape on the vendored `ingest()` API (`scripts/wiki_ingest/commands/ingest.py`) — interface symmetry per TASK.md §1.0 row.
- `type` field is included so the LLM prompt can hint at entity classification (CHECK enum: `person | concept | tool | dataset | source | event`).
