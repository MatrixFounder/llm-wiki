# Task 012-08: ADR-002 §D8 amendment acceptance pin (Class-B "rebuildable markdown")

## Use Case Connection
- UC-32: KNOWN_ISSUES migration — the amendment defines which file is canonical (Class A
  per-issue) vs rebuildable (Class B ledger). **Gates 012-09 (PW-H)** per C-7.

## Task Goal
The ADR-002 §D8 amendment was **drafted during the Architecture phase** (the
`Amendment (TASK 012, NO schema change — 2026-06-01)` block already exists in
`docs/adr/ADR-002-multi-vault-bottleneck-corrections.md`). This bead is its **acceptance
pin**: assert the amendment is present and the rebuildability invariant is well-defined,
so the gate-before-PW-H ordering is explicit and machine-checked (not a fresh authoring task).

## Changes Description

### Changes in Test Files
#### File: `tests/test_adr_002_amendment.py` (NEW)
- Read `docs/adr/ADR-002-multi-vault-bottleneck-corrections.md`; assert the §D8 block contains
  the `Amendment (TASK 012` marker.
- Assert the amendment defines the Class-B "rebuildable markdown" sub-case (substring checks:
  `rebuildable markdown`, `docs/issues/`, `wiki-index-render --auto-indexes`).
- Assert the rebuildability invariant text is present + well-defined: byte-identical
  **modulo a `GENERATED-AT` header**, sha256 in `.wiki/state.json`, the stable-total-order +
  `id` tiebreaker clause, and the "pure deterministic function of Class-A content" clause
  (architecture-review M2).
- Assert the "no schema change / `user_version` stays 5 / TYPE_MAPPING tag-route" clause.

## Acceptance Criteria
- ✅ The §D8 TASK-012 amendment is present + the rebuildability invariant is well-defined
  (machine-asserted), so 012-09 may proceed (C-7 gate satisfied).
- ✅ `mypy --strict` clean; suite green.

## Stub-First
Docs-only acceptance bead: the test is the deliverable (the amendment already exists). No
source change. Phase 1 == Phase 2 (a single assertion module).
