# Task 001-34: End-to-end rebuildability test

## Use Case Connection
- ADR-002 §D8 Class A → B reconstruction invariant
- Phase 3a exit criterion

## Task Goal
End-to-end test that proves the rebuildability invariant: `rm global.db → wiki-init --register-existing → wiki-reindex --full → identical search/lint output as before deletion`. This is the Phase 3a gate test.

## Changes Description

### New Files
- `tests/test_e2e_rebuildability.py`:
  - `def test_rebuildability_minimal_vault(minimal_vault):`
    1. Run `wiki-init --register-existing --vault <minimal_vault>`.
    2. Run `wiki-reindex --full --vault minimal-test`.
    3. Run `wiki-search "alpha"` → capture results A.
    4. Run `wiki-lint --vault minimal-test --json-sidecar /tmp/lint-before.json` → capture issues B.
    5. Delete the DB file (`db_path.unlink()`).
    6. Re-run `wiki-init --register-existing --vault <minimal_vault>` (re-creates DB + schema).
    7. Re-run `wiki-reindex --full --vault minimal-test`.
    8. Re-run `wiki-search "alpha"` → capture A2.
    9. Re-run `wiki-lint --vault minimal-test --json-sidecar /tmp/lint-after.json` → capture B2.
    10. Assert `A == A2` (search results identical: order, slugs, bm25 scores within ±0.001).
    11. Assert `B == B2` modulo `registered_at` (the only Class C field allowed to drift).
  - `def test_rebuildability_multi_vault(multi_vault):` — same but for both vaults; cross-vault duplicates section identical pre/post.
  - `def test_rebuildability_with_log_md(minimal_vault):` — pre-state has 3 entries in `log.md`; after rebuild, `log_events` has 3 rows with matching `log_md_byte_offset`s (M-2 contract).

### Changes in Existing Files
- `tests/conftest.py` — add helper `def run_skill_cli(skill_name: str, args: list[str]) -> dict:` that spawns CLI and parses JSON output.

### Component Integration
- The gate test for Phase 3a exit. Must be in CI.

## Test Cases

### End-to-end Tests
1. **TC-E2E-01**: Rebuildability holds on minimal vault.
2. **TC-E2E-02**: Rebuildability holds on multi-vault (cross-vault concept duplicates preserved).
3. **TC-E2E-03**: log.md round-trip: byte offsets match after rebuild.

### Unit Tests
N/A (this task IS the integration layer).

### Regression Tests
- All Stage 2 tests still pass.

## Acceptance Criteria
- [ ] All three E2E test cases pass.
- [ ] BM25 score tolerance documented (±0.001 — float drift acceptable, larger deviations indicate a bug).
- [ ] `registered_at` is the ONLY field allowed to differ between pre and post state.

## Notes
- This test is the practical encoding of ADR-002 §D8 — if it ever fails, the architectural invariant has regressed.
- BM25 scores depend on FTS5 internals; minor float drift across re-indexes is expected. Snippet text should be byte-identical.
- The test deliberately deletes only the DB file (not the WAL/SHM siblings); SQLite handles the recreation correctly.
