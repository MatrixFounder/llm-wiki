# Task 029-05: Agentic eval run — the GREEN gate `[VERIFICATION]`

## Use Case Connection
- RTM **R-029-7** (run half); acceptance §6.3; Q-029-1 grading model; PLAN §5 regression policy.

## Task Goal
All 029-01 eval cases PASS against the finished skill content (029-02/03/04), graded
deterministically per the expectation fields, with the report + transcripts filed.

## Steps
1. **Runner**: for each case in `evals.json`, spawn ONE fresh sub-agent (no cross-case
   context). The sub-agent receives: the skill content (SKILL.md; references on
   demand), the case `prompt_setup`, and the `vault_state` framing (registered /
   unregistered / cli-absent / headless — stated as environment facts in the prompt;
   for `cli-absent`/`headless` cases instruct the agent that the probe FAILED, do
   NOT have it actually mutate anything). Cases E-01..E-14 are **dry-run scenarios**:
   the sub-agent plans/states its commands; no live vault is touched in THIS bead
   (live execution is 029-06).
2. **Grade** each transcript against the case's `expect_*` fields per the
   `evals/README.md` binary checklist (substring present/absent, routing target,
   refusal, tier citation).
3. **Report**: `evals/reports/eval-run-2026-MM-DD.md` — table (case → field verdicts →
   PASS/FAIL) + the raw transcripts (inline or as sibling files).
4. **Loop on FAIL** (PLAN §5 policy): routing/safety wording → 029-02; command facts →
   029-03; recipe steps → 029-04. Re-run ONLY the failed cases after the fix; full
   green re-run once at the end. **Never weaken an expectation**; E-03 (wiki-search-
   first) and E-09 (eval canary) may NEVER be relaxed. **Loop cap (plan-review
   REC-2): if more than 2 full fix→re-run cycles are needed, STOP and report to the
   operator** (a persistent failure signals a design problem, not a wording one —
   escalate rather than burn N×14 runs).

## Verification
- The final report shows 14/14 (≥12) PASS with per-field verdicts.
- Each transcript came from a fresh context (runner notes the spawn per case).
- Any 029-02..04 edits made during the loop are listed in the report (traceability).

## Acceptance Criteria
- [ ] All cases PASS; report + transcripts filed under `evals/reports/`.
- [ ] Zero expectation weakened (diff of `evals.json` vs 029-01 commit = none, or
      strictly additive cases).
- [ ] Loop edits (if any) recorded and re-verified.

## Notes
Cost control: one sub-agent per case, smallest sufficient model is fine for E-01..E-08
(routing checks); use the default model for E-09/E-10 (injection judgment).
