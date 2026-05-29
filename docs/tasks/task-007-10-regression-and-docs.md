# Task 007-10: regression sweep + docs (acceptance gate)

## Use Case Connection
- All UCs (UC-16..UC-21) — final verification + documentation close-out.

## Task Goal
Close TASK 007: prove the whole suite is green + typed, update the project docs to mark R-6 shipped and hand off R-7/R-8, and extend the security regression to the new surfaces. This bead is the acceptance gate (RTM: all + C-4).

## Changes Description

### Changes in Existing Files
- `docs/ROADMAP.md` — mark **R-6 `wiki-query` → DONE** (date, bead count, ship summary), and add an explicit **R-7 / R-8 hand-off** note: both are now unblocked (they layer on `wiki-query`) and remain off-by-default + gated; update the "Done since 2026-05-25" section.
- `docs/ARCHITECTURE.md` — status header **IN DESIGN → SHIPPED** (TASK 007); keep the §2/§4/§5/§11/Verification-Map content (already added in the Architecture phase).
- `README.md` — ensure `wiki-query` is in the CLI overview + quick-start (the slash command + the two-pass note).
- `tests/` (envelope regression) — extend the parametrised "error envelope never echoes content" regression suite to `wiki-query`'s surfaces (question / answer / citation) — assert `CITATION_NOT_RETRIEVED`, `QUESTION_CHANGED`, `INVALID_CITATIONS`, `NO_CONTEXT`, `INVALID_QUESTION` envelopes carry `{error, field?, reason}` only (no `value`/`content`/`raw`/`received`).
- Any `scripts/wiki_skills/.AGENTS.md` / module docs touched by the new `wiki_query.py` + `_retrieval.py` — add the one-line module descriptions (memory-tracking policy).

### Verification (run, capture output)
- `pytest tests/ -q` — full suite, 0 failed (baseline 546+ + the new TASK 007 cases).
- `mypy --strict scripts/` — Success, no issues.
- `bin/wiki-query --help`, `bin/wiki-query prepare --help`, `bin/wiki-query apply --help` — all exit 0.

## Test Cases

### Regression Tests
- **TC-REG-01:** full `pytest tests/` green (record pass/skip counts).
- **TC-REG-02:** `mypy --strict scripts/` clean.
- **TC-REG-03:** envelope-never-echoes-content parametrised test covers every `wiki-query` error envelope.
- **TC-REG-04:** `wiki-search` golden-output byte-identical on a no-query-page fixture (shared-helper extraction safe — final confirmation).

## Acceptance Criteria
- [ ] Full `pytest tests/` green; `mypy --strict scripts/` clean.
- [ ] ROADMAP R-6 → DONE + R-7/R-8 hand-off note; ARCHITECTURE status → SHIPPED.
- [ ] README updated; `.AGENTS.md` module descriptions added where new modules landed.
- [ ] Envelope regression extended to `wiki-query` surfaces.
- [ ] All Definition-of-Done items in `docs/PLAN.md` §7 checked.

## Notes
No new feature code — verification + docs only. This is the gate: TASK 007 is not done until every PLAN.md §7 DoD item holds. Depends on all prior beads (007-01..007-09).
