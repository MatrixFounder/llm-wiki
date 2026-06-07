# Task 019.09: [ACCEPTANCE] dogfood `samples/Demand-generation` + e2e + close

## Use Case Connection
- UC-1..6 · AC-5, AC-6, AC-9

## Task Goal
Prove the feature end-to-end on the operator's real fixture, then close out docs.

## Changes Description
### New Files
- `tests/test_wiki_sync_resummarize_e2e.py` — e2e over a committed slice of the
  `samples/Demand-generation` shape (or a fixture mirror under `tests/fixtures/resummarize/`).

### Changes in Existing Files
- `README.md`, relevant `*/.AGENTS.md` — document the re-summarization policy + `--force`.
- `docs/ROADMAP.md` — mark the R-? item; `CLAUDE.md` — TASK 019 status line.
- `docs/issues/*.md` (+ regenerate `docs/KNOWN_ISSUES.md`) — record the **cross-task
  prerequisite** (Q-019-9): obsidian-personal `type_mapping` lacks `lesson-summary` → the
  summary `upsert` leg would `skip:unmappable-type`; the dogfood vault needs a layout
  mapping (TASK 012 surface). Not a TASK 019 blocker.

## Test Cases
### E2E (over the fixture)
1. **TC-09-1 (D2a):** with generated `sources:`, `02-1..02-4.txt` skip `summary-exists:provenance`.
2. **TC-09-2 (D2b group-key):** with provenance disabled, same files skip `summary-exists:mirror`.
3. **TC-09-3 (date-key Lessons):** `20260326-01/02.txt` skip via `^(\d{8})` per-folder override.
4. **TC-09-4 (same-dir stem):** `Resources/X.docx` skipped when `X.md` exists.
5. **TC-09-5 (--force):** `--force` re-plans all raw actionable.
6. **TC-09-6 (re-run no-op / AC-6):** a fully-summarized zone → all raw skipped; report counts.

## Acceptance Criteria
- [ ] e2e green over the fixture (all 3 patterns + force + no-op).
- [ ] Zero DDL (`user_version` 5); no `import anthropic`; `mypy --strict` + full `pytest` green.
- [ ] Docs synced; KNOWN_ISSUES records the `lesson-summary` mapping prerequisite.

## Notes
Keep the committed e2e fixture small under `tests/fixtures/` (the live `samples/` tree is
gitignored scratch — durable fixtures live with the test).
