# Task 005-17: regression sweep + docs + acceptance gate (all RTM)

## Use Case Connection
- All UC-09..UC-15 (final integration gate)

## Task Goal
Close TASK 005: full regression + type sweep, the security-envelope regression extension, and all documentation/ledger updates (ADR amendment, ROADMAP, KNOWN_ISSUES L-4, README, `.AGENTS.md`). This is the Definition-of-Done gate.

## Changes Description

### Changes in Existing Files
- `docs/adr/ADR-002-*.md` (or new `docs/adr/ADR-003-*.md`): finalize the §D8 amendment for the v2→v3 PK change (migration = full reindex).
- `docs/ROADMAP.md`: mark **R-4** + **R-5** DONE (with ship date + commit placeholder); note `wiki-merge` shipped; R-X5 now unblocked.
- `docs/KNOWN_ISSUES.md`: mark **L-4** `[STATUS: fixed 2026-05-..]` with resolution note (PK → `(vault_id, alias)`).
- `README.md`: add `wiki-confirm`/`wiki-alias`/`wiki-merge` to the CLI list + quick examples.
- `.AGENTS.md` (scripts/wiki_skills, scripts/wiki_index, tests): bring to TASK-005 surface (new methods, new CLIs, new models).
- `tests/` — extend the **parametrised envelope-never-echoes-content** regression (from v3.1) to cover `wiki-alias` + `wiki-merge` surfaces (architecture review m-2).

### Test Cases
1. **TC-GATE-01:** `pytest tests/ -q` → all green (baseline 450+ + new cases), 0 failed.
2. **TC-GATE-02:** `mypy --strict scripts/` → Success: no issues found.
3. **TC-GATE-03:** envelope regression: for every new error code (`ALIAS_COLLISION`, `INVALID_MERGE`, `MERGE_MIRROR_FAILED`, `ENTITY_NOT_FOUND`, `ENTITY_FILE_MISSING`), the emitted JSON never contains the offending surface/value (CWE-117/209).
4. **TC-GATE-04:** `PRAGMA user_version == 3`; `idx_aliases_lookup` absent; `idx_aliases_entity` present (L-4 closed).
5. **TC-GATE-05:** all `bin/<cmd> --help` (confirm/alias/merge) exit 0; symlinks resolve.

## Acceptance Criteria
- [ ] Full `pytest` green; `mypy --strict scripts/` clean.
- [ ] Envelope regression extended to alias + merge surfaces.
- [ ] ADR amendment + ROADMAP R-4/R-5 DONE + KNOWN_ISSUES L-4 fixed + README + `.AGENTS.md` updated.
- [ ] Definition of Done (PLAN.md §7) fully checked.

## Notes
Verify/docs bead — no stub phase. Depends on **all** prior beads (005-01..005-16). This bead is the merge-to-`main` acceptance gate; a post-ship `/vdd-multi` adversarial sweep (as done for 003/004) is recommended but tracked separately.
