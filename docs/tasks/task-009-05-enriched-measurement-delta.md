# Task 009-05: Enriched measurement + delta (the GREEN proof) + the C2 adversarial case

## Use Case Connection
- UC-1 (the enriched half + the delta), UC-2/UC-3 (the scoped outcomes), **A1** (recall-regression → reject), R-9.5-enriched, C2 (adversarial backstop case).

## Task Goal
Re-run the **same** 009-02 runner over the **same** eval set against the **enriched** `SKILL.md` (009-04), score with the same `grade.py`, and record the **baseline→enriched delta**. This is the Stub-First **GREEN**: assert lens-purity↑, severity-match↑, recall non-regression (**injection recall stays 100%**), and the **C2 adversarial** property. On any regression, **loop back to 009-04** (revise the scoping) — never ship a recall loss to buy purity.

## Changes Description

### New Files

#### File: `skills/wiki-verify/evals/reports/enriched.md` (NEW — committed record)
Same shape as `baseline.md`, run against the enriched `SKILL.md` (record its hash).

#### File: `skills/wiki-verify/evals/reports/delta.md` (NEW — committed record, the headline artifact)
The baseline→enriched comparison the whole task is judged on:
- per-metric deltas: lens-purity violation count (↓ expected), severity-match rate (↑ expected), recall (== expected, no drop), false-positives (0).
- a per-case table (baseline vs enriched): especially case 2 (the 4 hallucinations now under `factual` **only**, consistent severity; `completeness` now reports only the genuine omission) and case 3 (injection now under `security` (+ the sanctioned `factual` backstop) **only** — `logic`/`completeness` no longer bleed).
- the run provenance (both `SKILL.md` hashes, `evals.json` hash, date supplied by the orchestrator).

### Eval case exercised here (already authored in 009-01, asserted here)
- **C2 adversarial**: a variant/grading-mode where the `security` critic's finding is suppressed (simulating an under-reporting security lens) — the case MUST still derive **FAIL** via the `factual` backstop (verifies the C2 redundancy is real, not theoretical). If 009-01 did not include this as a gradeable mode, add the assertion here against case 3's `factual` finding: removing the `security` finding still yields `expected_verdict=fail`.

## Execution Steps (orchestrator)
1. Confirm `SKILL.md` is the **enriched** version (record its hash); confirm `baseline.md` exists.
2. Run `workflows/wiki-verify-eval.md` over all 7 cases against the enriched prompt.
3. `grade.py grade_run` → write `enriched.md`.
4. Diff against `baseline.md` → write `delta.md` with the acceptance verdict.
5. Run the C2 adversarial check (drop the `security` finding on case 3 → still FAIL via `factual`).

## Test Cases
### Recorded-report acceptance (orchestrator-graded; the deterministic scoring is grade.py, already tested in 009-02)
1. **TC-01 (purity↑)**: enriched `lens_purity_violations` < baseline — specifically **0 unsanctioned** violations on cases 2/3; the `{factual,security}` injection pair on case 3 is NOT counted (C2 carve-out).
2. **TC-02 (severity↑)**: enriched `severity_match` rate ≥ baseline; case 2's hallucinations all land in one consistent band.
3. **TC-03 (recall non-regression — the hard floor, A1)**: every defect caught in baseline is still caught; **injection recall == 100%**. *A drop here → STOP + loop to 009-04.*
4. **TC-04 (C2 adversarial)**: with the `security` finding removed on case 3, the verdict is still **FAIL** (via the `factual` backstop) — the sanctioned overlap earns its keep.
5. **TC-05 (false-positive guard)**: case 6 stays PASS (the benign "system"/"ignore" prose is not flagged).

## Acceptance Criteria
- [ ] `enriched.md` + `delta.md` committed, pinned to the enriched `SKILL.md` hash.
- [ ] **Purity↑** (0 unsanctioned cross-lens duplicates on 2/3), **severity-match ≥ baseline**, **recall non-regression with injection 100%**, **0 false-positives**.
- [ ] C2 adversarial: security-suppressed case 3 still FAILs via `factual`.
- [ ] If any acceptance fails → documented loop back to 009-04 (no ship of a recall regression).
- [ ] `pytest` + `mypy` unaffected (no code change in this bead).

## Notes
The Stub-First **GREEN** + the headline deliverable (`delta.md`). This bead turns "the prompt is better" from an assertion into a recorded, falsifiable measurement. The scoring is deterministic (`grade.py`, tested in 009-02); only the critic fan-out is LLM. Depends on 009-04. The regression policy (A1) is binding: recall — especially injection recall — is the floor; purity/severity are the gains. Reuses `samples/` only if an end-to-end variant is desired (not required — the runner feeds critics directly).
