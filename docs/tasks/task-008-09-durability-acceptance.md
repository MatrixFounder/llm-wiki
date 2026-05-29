# Task 008-09: §D8 durability round-trip acceptance (UC-26 — the binding gate)

> **strict-TDD** (this is the binding §D8 acceptance gate).

## Use Case Connection
- UC-26: Durability round-trip — the verdict page + its `verifies` ref reconstruct from Class A markdown alone after a full (and delta) reindex.

## Task Goal
Prove the §D8 contract: a filed verdict page survives a DB drop + rebuild from markdown alone, with its `verifies` ref reconstructed as `ref_type='verifies'` (not degraded, not clobbered). This is the acceptance test the three-part spine (008-01/02/03) exists to satisfy.

## Changes Description

### New Files

#### File: `tests/test_verify_durability.py` (NEW)
- Build a `/tmp` (tmp_path) fixture vault: register it, file a `_queries/q.md` answer (`cites: [_vault_/foo]`) + the `foo` source, then run `wiki-verify-multi prepare q` + `apply` (PASS verdict) to file `_verifications/v.md` (`verifies: _vault_/q`, body containing a `[[bar]]` `mentioned` wikilink).
- **Snapshot** DB state: the `pages` row (`type=verification`) + the `(v, q, 'verifies')` ref.
- **Delete** the DB (`.db` + `-wal` + `-shm`).
- **Re-seed the schema + vault (mandatory — adversarial-plan finding SEC-1):** the delete wipes the `vaults` row, and `reindex_full` raises `ValueError("vault_id … not registered")` if it's absent. Follow the existing `tests/test_wiki_query_durability.py::_rebuild_db` UC-20 pattern: `repo.apply_schema()` then `repo.register_vault(Vault(...))` **before** `reindex_full` (these tests use the direct `SQLiteRepository` path, where both are required — not the CLI auto-schema path).
- Run `reindex_full`.
- **Assert (full):**
  - the `_verifications/v.md` page is **indexed** as `type=verification` (it is in `PAGE_SUBDIRS` AND `TYPE_MAPPING` maps it → NOT in the reindex `skipped[]` — the 008-02 prerequisite check).
  - the `verifies` ref is reconstructed: `(v, q, 'verifies')` exists, `ref_type == 'verifies'` (**not** `'mentioned'`), reconstructed from the `verifies:` frontmatter alone.
  - the body `[[bar]]` `mentioned` ref survives (not clobbered by the frontmatter pass — Arch M-1).
- **Repeat for `--delta`** (delta-symmetry): a fresh edit + `reindex_delta` reconstructs the same refs.
- **AM-3 variant:** `verifies: _vault_/old-q` where `old-q` aliases canonical `new-q` → after reindex the ref is `(v, new-q, 'verifies')` (canonicalized, `ref_type` preserved).

## Test Cases

### End-to-end / acceptance Tests
1. **TC-ACC-01 (full round-trip):** drop DB → `reindex_full` → verdict page indexed `type=verification`; `verifies` ref `ref_type='verifies'`; body `mentioned` intact.
2. **TC-ACC-02 (delta-symmetry):** `reindex_delta` reconstructs the same `verifies` ref.
3. **TC-ACC-03 (not-skipped guard):** the verdict page is NOT in the reindex `skipped[]` report (regression for the M-1 `TYPE_MAPPING` trap).
4. **TC-ACC-04 (AM-3):** aliased `verifies:` target canonicalized with `ref_type='verifies'` preserved.

## Acceptance Criteria
- [ ] After drop-DB + `reindex_full`, the verdict page is indexed `type=verification` and its `verifies` ref is reconstructed from `verifies:` frontmatter alone, `ref_type='verifies'` (not `'mentioned'`, not clobbered).
- [ ] The same holds after `reindex_delta` (delta-symmetry).
- [ ] The verdict page is never in the reindex `skipped[]` (the M-1 guard).
- [ ] `mypy --strict` clean. **This is a whole-spine joint gate** (plan-review M-1-plan): the test is *collected (skipped)* from creation and un-skips → GREEN only once **008-01/02/03 AND 008-06/07 all land** — it cannot even file a page until the write/index path (006/007) exists, so it is **not** a per-bead RED→GREEN gate on 008-03 alone. Treat the still-skipped state as expected until the full chain lands (not a regression).

## Notes
Strict-TDD: this acceptance test is collected (skipped) early and goes green only once the **entire** spine (008-01/02/03) **plus** the write (008-06) + index (008-07) path land — it is the joint acceptance of the whole durability chain, not a gate on any single bead. Runs on a throwaway tmp vault (the repo is not a vault — CLAUDE.md). The §D8 round-trip is the binding acceptance criterion for the whole task. Depends on 008-01, 008-02, 008-03, 008-06 (to file a page), 008-07 (to index it).
