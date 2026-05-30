# Task 009-03: Baseline measurement (the RED state — prove the bleed before the fix)

## Use Case Connection
- UC-1: Measure baseline vs enriched (the **baseline** half). R-9.5-baseline.

## Task Goal
Run the 009-02 runner over the eval set using the **CURRENT (thin) `skills/wiki-verify/SKILL.md`** and record the baseline metrics. This is the Stub-First **RED** state: it must *visibly reproduce* the dogfood defects (lens-bleed on cases 2/3; severity drift on case 2) so the enriched delta (009-05) has a real "before" to beat. **This bead MUST land before any `SKILL.md` edit (009-04)** — the baseline is unmeasurable once the prompt changes.

## Changes Description

### New Files

#### File: `skills/wiki-verify/evals/reports/baseline.md` (NEW — committed record)
The recorded orchestrator-graded run (the report is committed; the run itself is not a pytest gate):
- Per-case grading records from `grade.py grade_run` (recall / lens-purity−C2 / severity-match / verdict-match / false-positives).
- The aggregate per-metric pass-rate.
- A short narrative confirming the **RED expectations** are observed on the current prompt:
  - case 2 (factual-overclaim): the 4 hallucinations are reported under **both** `factual` and `completeness` → **lens_purity_violations present**; severity drift (`high` vs `critical`) → **severity_match=false** for ≥1 defect.
  - case 3 (injection): the injection is reported under **3–4 lenses** (incl. `logic`/`completeness`, which the rubric will later forbid) → **lens_purity_violations present**.
  - recall is already good (the dogfood showed this) — baseline recall ≈ 100% incl. injection; the bleed + severity are the deltas to fix, NOT recall.
- The exact run provenance: `evals.json` hash, the `SKILL.md` git blob/hash at run time, the date (supplied by the orchestrator — not generated in-script).

## Execution Steps (orchestrator)
1. Confirm `SKILL.md` is the **unedited** TASK-008 version (record its hash).
2. Run `workflows/wiki-verify-eval.md` over all 7 cases (4 critics × 7 = 28 critic sub-agents; the proven dogfood fan-out pattern).
3. Pipe the collected critic outputs through `grade.py grade_run`.
4. Write `evals/reports/baseline.md` with the records + aggregate + the RED-confirmation narrative.

## Test Cases
### Recorded-report assertions (not pytest — this is the orchestrator-graded run)
1. **TC-01**: the report exists, is well-formed (one record per case), and pins the `SKILL.md` hash it ran against.
2. **TC-02 (RED confirmed)**: cases 2 and 3 show ≥1 `lens_purity_violation` each; case 2 shows a `severity_match=false`. *(If the baseline does NOT show the bleed, STOP — either the eval set doesn't exercise it (fix 009-01) or the assumption is wrong; do not proceed to 009-04 measuring against a baseline with nothing to beat.)*
3. **TC-03**: baseline recall ≈ 100% (incl. injection) — establishes that 009-05 must not regress it.

## Acceptance Criteria
- [ ] `evals/reports/baseline.md` committed, pinned to the unedited `SKILL.md` hash.
- [ ] RED confirmed: lens-bleed + severity drift visible on cases 2/3 (the metrics to improve).
- [ ] Baseline recall recorded (the floor 009-05 must hold, esp. injection 100%).
- [ ] `SKILL.md` is **untouched** at the end of this bead (no edit yet); `pytest` + `mypy` unaffected (no code change).

## Notes
The Stub-First **RED**. The whole task's value proposition is "measurably reduce bleed without regressing recall" — that claim is only falsifiable against a recorded baseline. Depends on 009-02. **Hard ordering gate**: 009-04 must not start until `baseline.md` is committed (the orchestrator/`vdd-develop-all` chain enforces the sequence). The run is orchestrator-graded + recorded; `grade.py` (the scoring) is the deterministic, already-tested part.
