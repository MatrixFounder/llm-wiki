# Task 003-07b: `upsert_extracted_entity` — call site in skill

## Meta

- **Bead ID**: `task-003-07b-call-upsert-entity`
- **Slug**: `call-upsert-entity`
- **Maps to**: Issue **I-7.7b**; RTM row **R-37**.
- **Depends on**: task-003-01 (helper stub exists), task-003-06 (concept page written first), task-003-07a (DAL `upsert_entity` method available).
- **Estimated time**: 0.25 day
- **Priority**: Critical (the second half of R-37)

## Use Case Connection

- **UC-08 step 8 (call site)**: "calls `repo.upsert_entity(...)` with `is_candidate=1`".
- **UC-08 alternative A1 (call-layer defensive)**: even though the SQL guard (003-07a) is primary, this bead adds a defensive call-layer check — DON'T write `is_candidate=1` if an `is_candidate=0` row already exists; just skip.

## Task Goal

Replace the `NotImplementedError` stub in `wiki_extract_concepts.py::upsert_extracted_entity(repo, vault_id, candidate, source_slug, today) -> str` with:

1. (Defensive) Query `entities` for `(vault_id, slug)`. If a row exists with `is_candidate=0`, return `"confirmed"` (skip the upsert — the SQL guard would no-op anyway, but explicit skip avoids unnecessary writes).
2. Call `repo.upsert_entity(vault_id=vault_id, slug=candidate["slug"], name=candidate["name"], type=candidate["entity_type"], is_candidate=1, canonicalized_by=f"llm:{candidate.get('model','claude-sonnet-4-6')}@{today}", first_seen=today, last_updated=today)`.
3. Return `"created"` if the row was new, `"updated"` if it pre-existed as a candidate. Determine by querying before the upsert (or via SQLite's `INSERT OR ABORT` + `UPDATE` two-step — pick the simpler).

The return value is consumed by 003-10 (manifest builder) for the `action` field on `mentioned[]` items (subtle: it's not the same as 003-05's `action` annotation — that's `create`/`mention`/`unchanged` referring to **pages**; this is `created`/`updated`/`confirmed` referring to **entity rows**).

## Stub-First Plan

**Phase 1 — Red test on stub**:

1. Add to `tests/test_wiki_extract_concepts.py`:
   - `test_upsert_extracted_entity_calls_repo_with_is_candidate_1` (Phase 1):
     - Mock `repo.upsert_entity`.
     - Call `upsert_extracted_entity(repo, "vid", {"slug":"foo","name":"Foo","entity_type":"concept"}, "src", "2026-05-27")`.
     - On stub: `NotImplementedError`. After Phase 2: assert `repo.upsert_entity` called once with `is_candidate=1`, `vault_id="vid"`, etc.
   - `test_upsert_extracted_entity_skips_confirmed` (Phase 2):
     - Seed an `entities` row with `(vault_id="vid", slug="foo", is_candidate=0)`.
     - Call `upsert_extracted_entity`.
     - Assert returned `"confirmed"` and `repo.upsert_entity` NOT called.
   - `test_upsert_extracted_entity_returns_created_for_new_row` (Phase 2):
     - Empty DB; call upsert; assert return value `"created"`.
   - `test_upsert_extracted_entity_returns_updated_for_existing_candidate` (Phase 2):
     - Seed row with `is_candidate=1`; call upsert with new `last_updated`; assert return value `"updated"`.
2. Run pytest — Red.

**Phase 2 — Logic**:

1. Replace the body:
   ```python
   def upsert_extracted_entity(
       repo: IndexRepository,
       vault_id: str,
       candidate: dict[str, Any],
       source_slug: str,
       today: str,
   ) -> str:
       """Upsert the entity row for an extracted candidate.

       Returns one of:
         - "confirmed" — existing row had is_candidate=0; skipped to avoid no-op write.
         - "created" — row did not exist; inserted with is_candidate=1.
         - "updated" — existing candidate row was updated.
       """
       existing = repo.resolve_entity(vault_id, candidate["slug"])  # may raise NotImplementedError per Phase 3a
       # ^ if resolve_entity is still stub, fall back to raw query
       if existing and existing.get("is_candidate") == 0:
           return "confirmed"
       canonicalized_by = f"llm:{candidate.get('model', 'claude-sonnet-4-6')}@{today}"
       repo.upsert_entity(
           vault_id=vault_id,
           slug=candidate["slug"],
           name=candidate["name"],
           type=candidate["entity_type"],
           is_candidate=1,
           canonicalized_by=canonicalized_by,
           first_seen=existing.get("first_seen", today) if existing else today,
           last_updated=today,
       )
       return "updated" if existing else "created"
   ```
2. **Fallback for `resolve_entity` stub**: TASK.md §1.3 explicitly says `resolve_entity` stays `NotImplementedError`. So this bead cannot call `repo.resolve_entity`. Instead, query via the repo's read path directly:
   ```python
   def _lookup_entity_row(repo: IndexRepository, vault_id: str, slug: str) -> dict[str, Any] | None:
       """Direct lookup bypassing resolve_entity (which is still a stub per Phase 3a)."""
       row = repo._conn.execute(
           "SELECT slug, name, is_candidate, first_seen FROM entities WHERE vault_id = ? AND slug = ?",
           (vault_id, slug),
       ).fetchone()
       if row is None:
           return None
       return dict(row)
   ```
   Use this helper in the body instead of `repo.resolve_entity`.
3. Unskip Phase-2 tests; run pytest — Green.

## Changes Description

### New Files

- None.

### Changes in Existing Files

#### File: `scripts/wiki_skills/wiki_extract_concepts.py`

- Replace `upsert_extracted_entity` stub body with the logic above.
- Add private helper `_lookup_entity_row(repo, vault_id, slug)` to bypass the still-stubbed `resolve_entity`.

#### File: `tests/test_wiki_extract_concepts.py`

- Add 4 unit tests (1 Phase-1 + 3 Phase-2).

### Component Integration

- Output (string action: `created`/`updated`/`confirmed`) flows into manifest builder (003-10) for the `mentioned[]` array's `action` field.
- This bead is **downstream of 003-06**: concept page write happens first, entity upsert second. Order matters because if the file write fails (path-traversal, disk full), we don't pollute the entity table.

## Files Touched (explicit list)

- `scripts/wiki_skills/wiki_extract_concepts.py` (modified — 1 stub replacement + 1 private helper)
- `tests/test_wiki_extract_concepts.py` (modified — add 4 tests)

## Test Surface

- **New**: 4 unit tests:
  - `test_upsert_extracted_entity_calls_repo_with_is_candidate_1`
  - `test_upsert_extracted_entity_skips_confirmed`
  - `test_upsert_extracted_entity_returns_created_for_new_row`
  - `test_upsert_extracted_entity_returns_updated_for_existing_candidate`

## Acceptance Criteria

- [ ] **R-37(a)**: `repo.upsert_entity` called with `is_candidate=1` for novel concepts.
- [ ] **R-37(b)**: existing `is_candidate=0` entity → defensive skip at call layer (function returns `"confirmed"` without invoking `upsert_entity`).
- [ ] **R-37(c)**: `canonicalized_by` set to `"llm:claude-sonnet-4-6@<date>"` (or whatever model was used).
- [ ] **R-37(d)**: `first_seen` preserved from existing row when present; defaults to `today` for new rows.
- [ ] All 4 unit tests pass.
- [ ] `mypy --strict` clean.
- [ ] Full sweep `pytest tests/ -q` still green.

## Verification

```bash
pytest tests/test_wiki_extract_concepts.py -v -k "upsert_extracted_entity"
pytest tests/ -q
mypy --strict scripts/wiki_skills/wiki_extract_concepts.py
```

## Rollback

Revert `upsert_extracted_entity` to `NotImplementedError`; remove the 4 tests + private helper. Downstream beads (003-10 manifest builder) will fail until restored.

## Notes

- The defensive call-layer check is **double-belt** — the SQL-level guard in 003-07a is primary. R-5 (Risk Register entry) was specifically about this guard surviving schema migrations; the call-layer skip is the second belt.
- Bypassing `resolve_entity` (which stays stubbed per TASK.md §1.3 non-goal) is deliberate. A future bead (R-4 promotion CLI) will implement `resolve_entity` properly; until then, `_lookup_entity_row` is the local fallback.
- Distinguish the two "actions" meanings:
  - 003-05 classifier: `action` on a candidate ∈ {`create`, `mention`} — refers to whether a `_concepts/<slug>.md` PAGE will be written.
  - 003-07b (this bead): return string ∈ {`created`, `updated`, `confirmed`} — refers to what happened to the ENTITY ROW.
  - Both are surfaced in the manifest via different fields. 003-10 (manifest builder) keeps them straight.
