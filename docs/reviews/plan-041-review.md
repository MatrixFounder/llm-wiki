# Plan Review — PLAN 041 (active-note resolution)

- **Date:** 2026-06-20
- **Reviewer:** Plan Reviewer (Planning→Execution gate, VDD)
- **Target:** `docs/PLAN.md` (PLAN 041 — 8 stub-first beads S0–S8 + RTM coverage map)
- **Checklists applied:** `skill-plan-review-checklist` **AND** `skill-self-improvement-verificator` Mode B (framework self-improvement — `skills/` + templates).
- **Status:** **APPROVED WITH COMMENTS** — no blocking (🔴); 3 MAJOR + 4 MINOR to fold in during execution.

## General assessment
House-style stub-first plan (S0–S8 + RTM coverage map, matching PLAN 037–040). The two safety hinges are structural, not aspirational: **S0 capability fixture capture is first and gates the descriptor branch shape** (HIGH-no-ask vs confirmed-MEDIUM), and **S1 (stub + RED contract test) strictly precedes S2 (logic → GREEN)**. Never-relax set named + re-verified (S5); destructive-verb re-confirm + both injection-neg evals scheduled; self-improvement constraints (SKILL.md via `skill-enhancer`; wrapper = script inside the existing skill so no `init_skill` gate; `skill-validator`; zero anthropic/DDL/deps) all stated; the mandatory `skill-self-improvement-verificator` PLAN audit is itself bead S8.

## Use Case coverage — all 8 (+b/c sub-cases) map to a bead. No gap.
UC-1→S2/S3/S4/S5 · UC-1b→S0/S2/S3/S5 · UC-1c→S3/S5 · UC-2→S3/S5 · UC-3→S3/S4 · UC-4→S1/S2/S3 · UC-5→S1/S5 · UC-6→S3/S5 · UC-6b→S3/S5 · UC-7→S3/S5 · UC-7b→S3/S5 · UC-8→S3.

## RTM coverage — every R/NF maps to ≥1 bead (judged via the coverage map, the accepted 037–040 convention).
R-1→S0/S2/S3 · R-2→S3/S5 · R-3→S0/S1/S2 · R-4→S3/S5 · R-5→S2/S3/S4 · R-6→S4/S5/S6 (see M-1) · NF-1→S1/S2/S3 · NF-2→S1/S2/S7 (see M-2).

## Structure verification
- **Stub-First — PASS** (S1 RED before S2 GREEN; restated in invariants).
- **Entry gate first — PASS** (S0 first; gates HIGH-vs-MEDIUM; "no code assumes enumeration until S0 proves it").
- **Arch-review MAJORs — all reflected:** M-1 (S0 fixture + HIGH→MEDIUM contingency), M-2 (S0 unknown (i) `obsidian file`→path), M-3 (S1 "headless = caller pre-check"; S3 "headless decided BEFORE the wrapper").
- **m-3 nit — closed** (S3 reconciles `## Targeting discipline` with a forward-pointer; *Gate* "no contradictory footgun prose").
- **Never-relax — PASS** (S5 re-verifies E-09/E-10/E-11/E-13/E-14/E-15; 7 new evals scheduled).
- **Atomicity — PASS** (each bead a single concrete *Gate:*).
- **Self-improvement meta-audit — PASS** (verification S2/S3/S6/S8; rollback present; atomic S0–S8; test coverage S1/S5; wrapper not a new skill; no Tier-0 removal).

## Comments

### 🔴 CRITICAL — None.

### 🟡 MAJOR
- **M-1 — R-6d (SKILL.md version bump + Maintenance note) isn't in the R-6 map row and no *Gate* asserts it landed.** A `skill-enhancer` edit forgetting the bump passes every current gate. **Fix:** add **S3** to the R-6 coverage row; add "SKILL.md `version:` incremented + Maintenance/changelog note present" to the S3 *Gate*.
- **M-2 — NF-2 (no regressions) has no positive verification gate beyond S2's anthropic-grep.** Zero-DDL (`user_version` 7) and no-new-deps are prose invariants with no runnable check. **Fix:** add to **S8** (or S2): `git diff --stat requirements.txt sql/wiki-index-v2.sql` empty (or `grep user_version sql/wiki-index-v2.sql` still `7`) **and** repo-wide `grep -r 'import anthropic'` clean.
- **M-3 — S0 has a hard live-app dependency with no documented fallback, inviting a fabricated fixture that silently voids the M-1/M-2 entry gate.** **Fix:** add an S0 "blocked-on-no-live-app" branch — STOP and escalate for a manual capture (DoD §3b dogfood owner); never synthesize the fixture, never proceed to S2's HIGH-branch logic without it; require a provenance line (source CLI version) so the contract test is genuinely fixture-backed.

### 🟢 MINOR
- **N-1 — UC-8 (explicit path → no resolve) has no dedicated eval** (transitive via E-01/E-05). Optional one-line S5 assertion.
- **N-2 — Q-041-7 (descriptor-not-open: ASK-but-offer-search) is LEAN and not scheduled.** Add its finalization to S3 (decide whether LOW offers a vault search) + S7 docs scope.
- **N-3 — UC-7 split-pane is a "live check" per ADR-008 but the plan doesn't say where it's exercised.** Note in S0/S3 that split-pane focus disambiguation is resolved live (re-confirm regardless of session trust); don't encode it deterministically.
- **N-4 — Q-041-2's mypy sub-decision is deferred to S2's *Gate* ("record which") but not written back to the design record.** Add "record the Q-041-2 mypy decision in open-questions §11g" to S2 or S7.

## Recommendation
**APPROVED WITH COMMENTS.** Proceed to Development. Fold M-1/M-2/M-3 (and N-2/N-4) into PLAN 041 at execution. Stub-First ordering, the S0 entry gate, the three arch-review MAJORs, and the never-relax set are all correctly honored.
