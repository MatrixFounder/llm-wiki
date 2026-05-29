# Task 008-10: e2e + compounding + layout-agnostic acceptance (UC-22/23/24/25/27/28)

## Use Case Connection
- UC-22 (verify→PASS), UC-23 (FAIL→exit 6, answer untouched), UC-24 (idempotent re-verify), UC-25 (compounding), UC-27 (grounding/answer-change refusals), UC-28 (layout-agnostic).

## Task Goal
End-to-end acceptance over `main(argv)` for the full `wiki-verify-multi` surface, plus the compounding + grounding + **layout-agnostic** properties. Complements the §D8 gate (008-09).

## Changes Description

### New Files

#### File: `tests/test_verify_e2e.py` (NEW)
Drive `prepare` → (construct a verdict JSON directly — **no model SDK**, Decision-17) → `apply` over `main(argv)` on a tmp fixture vault.
- **UC-22 (PASS):** `prepare` a query page with `cites:`, build a `verdict:"pass"` JSON, `apply` → `_verifications/<slug>.md` written `type: verification`/`verdict: pass`; exit 0; `pages` row + `verifies` ref present. **Use a vault REGISTERED (not `--scaffold-new`'d) with NO pre-existing `_verifications/` directory** (the migrated-v4 case, adversarial-plan finding CMP-4) — so the test proves `apply` creates the dir (`mkdir(parents=True)`) rather than crashing with `FileNotFoundError`.
- **UC-23 (FAIL → exit 6 + no mutation):** a `verdict:"fail"` (factual finding ≥ high) → page filed `verdict: fail`; **exit 6**; the `_queries/<slug>.md` answer file is **byte-identical** before/after (hash). `--fail-on=none` → exit 0.
- **UC-24 (idempotency):** re-run identical `prepare` → `is_unchanged:true` (after `apply` recorded the state); `--force` re-verifies; editing the query answer → `prepare` no longer `is_unchanged` (re-triggers).
- **UC-25 (compounding):** after `apply`, `wiki-search <vault> "<term>" --types verification` returns the verdict page; the `(verification, query, 'verifies')` ref exists (backlink).
- **UC-27 (refusals):** `prepare` on empty `cites:` → `NO_SOURCES`; `apply` with a finding `source` ∉ examined → `FINDING_SOURCE_NOT_EXAMINED`; `apply` after the answer changed → `ANSWER_CHANGED`. None writes a file.

#### File: `tests/test_verify_layout_agnostic.py` (NEW)
- **UC-28 (layout-agnostic):** a cited source page whose `pages.file_path` is a **non-Karpathy** path (e.g. `notes/foo.md`) is read by `prepare` (its `body_excerpt` is non-empty) — proving source access uses `pages.file_path`, not a reconstructed `_sources/<slug>.md`.
- **Grep guard:** assert `scripts/wiki_skills/wiki_verify_multi.py` contains **no** literal `PAGE_SUBDIRS` member (`"_sources"`, `"_concepts"`, `"_entities"`, `"_queries"`, `"_verifications"`) — read the source + scan (the C-8/NFR-7 enforcement; co-locate with the 008-05 grep-guard or here as the canonical acceptance).

## Test Cases

### End-to-end / acceptance Tests
1. **TC-ACC-01:** UC-22 happy path (PASS, exit 0, page + ref written) on a vault with **no pre-existing `_verifications/` dir** (apply must create it, not crash — CMP-4).
2. **TC-ACC-02:** UC-23 FAIL → exit 6 + answer byte-identical; `--fail-on=none` → exit 0.
3. **TC-ACC-03:** UC-24 idempotent re-verify + `--force` + change-retrigger.
4. **TC-ACC-04:** UC-25 `wiki-search --types verification` finds the verdict + `verifies` backlink exists.
5. **TC-ACC-05:** UC-27 `NO_SOURCES` / `FINDING_SOURCE_NOT_EXAMINED` / `ANSWER_CHANGED` — all refuse, nothing written.
6. **TC-ACC-06:** UC-28 cited source read via non-Karpathy `file_path`.
7. **TC-ACC-07:** grep guard — no `PAGE_SUBDIRS` literal in `wiki_verify_multi.py`.

## Acceptance Criteria
- [ ] All six UCs (22/23/24/25/27/28) pass over `main(argv)` on a tmp fixture vault.
- [ ] FAIL → exit 6 + the answer byte-identical (no-mutation invariant re-asserted at the e2e level).
- [ ] `wiki-search --types verification` recall + `verifies` backlink (compounding).
- [ ] Layout-agnostic: cited source read via `file_path`; grep guard green.
- [ ] Verdicts constructed directly (no model SDK — Decision-17); full `pytest` green; `mypy --strict` clean.

## Notes
Stub-First: scaffold the tests with `pytest.skip` (collected) in Phase 1; fill assertions as the skill beads land. Verdict JSON is constructed by the test directly (the strict contract), never via a model call (tests/.AGENTS.md anti-pattern). Depends on 008-05, 008-06, 008-07, 008-09.
