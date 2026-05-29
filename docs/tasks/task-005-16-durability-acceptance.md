# Task 005-16: durability round-trip acceptance tests — the §D8 gate (UC-14, UC-15)

## Use Case Connection
- UC-14 (confirm + alias durability), UC-15 (merge durability)

## Task Goal
The binding ADR-002 §D8 acceptance gate: prove confirm-state, aliases, **and merges** all reconstruct from Class A markdown alone after a full DB rebuild, and that AM-3 keeps mentions/backlinks correct across the rebuild.

## Changes Description

### New Files
- `tests/test_entity_resolution_durability.py` — the round-trip acceptance suite.

### Test Cases
### UC-14 — confirm + alias round-trip
1. **TC-E2E-01:** vault with one confirmed entity (`is_candidate:false`), one candidate (`is_candidate:true`), one alias (in `into.aliases` frontmatter). Snapshot DB state → delete the DB → `wiki-reindex --full` → re-read: confirmed stays confirmed, candidate stays candidate, alias rebuilt — **from markdown alone**.
### UC-15 — merge round-trip + AM-3
2. **TC-E2E-02:** merge `hermes-framework` → `hermes-agent` via `wiki-merge`; then delete DB + `wiki-reindex --full`. Assert: `from` entity **not** re-materialised; `resolve_entity("Hermes Framework")` → `hermes-agent`; `[[hermes-framework]]` refs in source bodies **not** orphaned (`find_orphan_links`); `hermes-agent.mentions_count` == de-duplicated union **after** the rebuild (AM-3 canonicalization holds).
3. **TC-E2E-03:** `get_backlinks(into)` includes the re-pointed refs both immediately after merge and after the rebuild (Risk R-6).
4. **TC-E2E-04 (C-8 recovery):** simulate a merge that fails at the DB mirror after Class A mutation (monkeypatch) → `MERGE_MIRROR_FAILED`; `wiki-reindex --delta` then restores DB consistency from Class A.

## Acceptance Criteria
- [ ] UC-14: confirm-state + alias survive `wiki-reindex --full`.
- [ ] UC-15: merge reproduced from Class A; no orphan; mentions = union survives rebuild (AM-3).
- [ ] Backlinks correct immediately + post-reindex.
- [ ] C-8 mid-merge-failure recovers via `--delta`.

## Notes
Critical acceptance bead. Depends on 005-02, 005-03, 005-09, 005-10, 005-11. Phase-1: scaffolding with `pytest.skip`; Phase-2: full assertions once the surface lands. This is where AM-3 is proven, not just asserted in docs.
