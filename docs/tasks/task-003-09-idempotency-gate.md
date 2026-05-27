# Task 003-09: `check_idempotency` — `source_state` short-circuit

## Meta

- **Bead ID**: `task-003-09-idempotency-gate`
- **Slug**: `idempotency-gate`
- **Maps to**: Issue **I-7.9**; RTM row **R-39**.
- **Depends on**: task-003-01 (helper stub exists). **Parallel-safe** with 003-04..003-08 — uses only `source_state` queries, independent of LLM/refs/upserts.
- **Estimated time**: 0.25 day
- **Priority**: High (gate before LLM call — saves API tokens on no-op re-runs)

## Use Case Connection

- **UC-08 step 4**: "Queries `source_state` for `(vault_id, source_kind='extract-concepts', scope, key='source_hash')`. No prior record → proceed."
- **UC-09 Scenario A**: "Body unchanged → returns `{"status":"ok","action":"unchanged","manifest":null}`, exit 0, no LLM call, no DB mutations."

## Task Goal

Replace the `NotImplementedError` stub in `wiki_extract_concepts.py::check_idempotency(repo, vault_id, source_slug, current_hash) -> bool` with:

1. Query `source_state` for `(vault_id, source_kind='extract-concepts', scope=source_slug, key='source_hash')`.
2. If a row exists AND its `value` equals `current_hash` → return `True` (unchanged; skip extraction).
3. Otherwise → return `False` (proceed with extraction).

Pair with `update_idempotency_state(repo, vault_id, source_slug, new_hash) -> None` (private helper or co-located in the same bead) called after successful extraction to upsert the row.

## Stub-First Plan

**Phase 1 — Red test on stub**:

1. Add to `tests/test_wiki_extract_concepts.py`:
   - `test_check_idempotency_no_prior_record` (Phase 1):
     - Empty `source_state` table.
     - Call `check_idempotency(repo, "vid", "src", "hash-abc")`.
     - On stub: `NotImplementedError`. After Phase 2: returns `False`.
   - `test_check_idempotency_hash_match` (Phase 2):
     - Seed `source_state` row with `(vault_id="vid", source_kind="extract-concepts", scope="src", key="source_hash", value="hash-abc")`.
     - Call `check_idempotency(repo, "vid", "src", "hash-abc")` → returns `True`.
   - `test_check_idempotency_hash_mismatch` (Phase 2):
     - Seed row with `value="hash-old"`.
     - Call with `current_hash="hash-new"` → returns `False`.
   - `test_check_idempotency_filters_by_source_kind` (Phase 2):
     - Seed `source_state` row with `source_kind="enrich"` (different kind) and matching hash.
     - Call with `source_kind='extract-concepts'` → returns `False` (different kind, no match).
   - `test_check_idempotency_filters_by_vault_id` (Phase 2):
     - Seed row for vault "A" with `value="hash-abc"`.
     - Call with `vault_id="B"` → returns `False`.
2. Run pytest — Red.

**Phase 2 — Logic**:

1. Replace the body:
   ```python
   _SOURCE_KIND = "extract-concepts"

   def check_idempotency(
       repo: IndexRepository,
       vault_id: str,
       source_slug: str,
       current_hash: str,
   ) -> bool:
       """Return True if the source page has not changed since the last extraction.

       Queries source_state for the most recent recorded hash. On match, the caller
       should short-circuit (no LLM call, no DB mutations) per UC-09 Scenario A.
       """
       row = repo._conn.execute(
           "SELECT value FROM source_state "
           "WHERE vault_id = ? AND source_kind = ? AND scope = ? AND key = ?",
           (vault_id, _SOURCE_KIND, source_slug, "source_hash"),
       ).fetchone()
       if row is None:
           return False
       return row["value"] == current_hash


   def update_idempotency_state(
       repo: IndexRepository,
       vault_id: str,
       source_slug: str,
       new_hash: str,
   ) -> None:
       """Upsert the source_state row after successful extraction."""
       with repo._conn:
           repo._conn.execute(
               """INSERT INTO source_state (vault_id, source_kind, scope, key, value, updated_at)
                  VALUES (?, ?, ?, ?, ?, datetime('now'))
                  ON CONFLICT(vault_id, source_kind, scope, key) DO UPDATE SET
                      value = excluded.value, updated_at = excluded.updated_at""",
               (vault_id, _SOURCE_KIND, source_slug, "source_hash", new_hash),
           )
   ```
2. Wire into `main()`:
   ```python
   source_body = read_source_body(args.vault_root, args.source_page)
   current_hash = hashlib.sha256(source_body.encode("utf-8")).hexdigest()
   if check_idempotency(repo, args.vault, args.source_page, current_hash):
       print(json.dumps({"status": "ok", "action": "unchanged", "manifest": None}))
       return 0
   # ... proceed with extraction ...
   # at the end:
   update_idempotency_state(repo, args.vault, args.source_page, current_hash)
   ```
3. Unskip Phase-2 tests; run pytest — Green.

## Changes Description

### New Files

- None.

### Changes in Existing Files

#### File: `scripts/wiki_skills/wiki_extract_concepts.py`

- Replace `check_idempotency` stub body.
- Add new helper `update_idempotency_state(...)` co-located in the same module (closely paired with the gate).
- Add `_SOURCE_KIND = "extract-concepts"` module constant.
- Wire into `main()` (idempotency check happens AFTER hash computation, BEFORE the LLM call; update happens AFTER successful extraction).

#### File: `tests/test_wiki_extract_concepts.py`

- Add 5 unit tests.

### Component Integration

- The gate sits between source-body read (in `main()`) and LLM extraction. If the gate returns `True`, `main()` immediately emits the "unchanged" envelope and returns 0.
- `update_idempotency_state` runs at the very end of `main()`, after `upsert_entity_refs` (003-08) — so a mid-pipeline failure leaves `source_state` un-updated, allowing the next run to retry.

## Files Touched (explicit list)

- `scripts/wiki_skills/wiki_extract_concepts.py` (modified — 1 stub replacement + 1 new helper + 1 module constant + wiring in `main()`)
- `tests/test_wiki_extract_concepts.py` (modified — add 5 tests)

## Test Surface

- **New**: 5 unit tests:
  - `test_check_idempotency_no_prior_record`
  - `test_check_idempotency_hash_match`
  - `test_check_idempotency_hash_mismatch`
  - `test_check_idempotency_filters_by_source_kind`
  - `test_check_idempotency_filters_by_vault_id`

## Acceptance Criteria

- [ ] **R-39(a)**: `sha256(source_body)` computed BEFORE the gate (so the gate has something to compare against).
- [ ] **R-39(b)**: Match → return `{"status":"ok","action":"unchanged","manifest":null}`, exit 0, NO LLM API call (verified by `test_check_idempotency_hash_match` + integration test 003-13).
- [ ] **R-39(c)**: No prior record OR mismatch → proceed with extraction; update `source_state` after success.
- [ ] Filter by `source_kind='extract-concepts'` (verified by `test_check_idempotency_filters_by_source_kind`).
- [ ] Filter by `vault_id` (verified by `test_check_idempotency_filters_by_vault_id`).
- [ ] `source_state` row primary key includes `source_kind` (so different kinds don't collide on same `(vault_id, scope)` — see Risk R-6 in PLAN.md).
- [ ] All 5 unit tests pass.
- [ ] `mypy --strict` clean.
- [ ] Full sweep `pytest tests/ -q` still green.

## Verification

```bash
pytest tests/test_wiki_extract_concepts.py -v -k "idempotency"
pytest tests/ -q
mypy --strict scripts/wiki_skills/wiki_extract_concepts.py
```

## Rollback

Revert both functions to stub; remove the 5 tests + module constant + `main()` wiring. The pipeline still works without the gate (just makes API calls every run); R-39 won't be satisfied but no breakage in other beads.

## Notes

- `source_state.source_kind` is `TEXT NOT NULL` with no CHECK constraint (TASK.md §6); the new value `"extract-concepts"` is allowed without DDL change.
- The primary key on `source_state` is `(vault_id, source_kind, scope, key)` per Phase 3a — verify by reading `docs/SCHEMA-v2.sql`. If the PK is different, the `ON CONFLICT` clause needs adjustment.
- `update_idempotency_state` runs at the very end so partial failures don't update the hash — next run will retry. This is intentional: the gate's contract is "if I claim unchanged, the previous run COMPLETED successfully."
- Bypassing the DAL with `repo._conn.execute(...)` is the same pattern used in 003-03 (load_known_entities) and 003-07b (`_lookup_entity_row`). Documented in PLAN.md §9 — TASK.md §1.3 limits DAL extensions to `upsert_entity` only.
