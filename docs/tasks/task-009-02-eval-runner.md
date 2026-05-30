# Task 009-02: Eval runner — recipe (`wiki-verify-eval`) + deterministic grader (`grade.py`)

## Use Case Connection
- UC-1: Measure baseline vs enriched. R-9.5 (mechanism). Arch "Eval harness" + F-1/F-3.

## Task Goal
Build the **runner** that turns the 009-01 eval set into a graded report: a committed **orchestrator-run recipe** (`workflows/wiki-verify-eval.md`) that fans the 4 critics over each case using the lens prompts **extracted from `SKILL.md`**, and a **deterministic, unit-tested** grader (`skills/wiki-verify/evals/grade.py`) that scores critic outputs against `evals.json` expectations. The deterministic half (grade.py) is CI-green; the LLM fan-out is the orchestrator-run half (recorded, not pytest). The runner is the *same* for baseline (009-03) and enriched (009-05) — the only variable is the `SKILL.md` content.

## Changes Description

### New Files

#### File: `skills/wiki-verify/evals/grade.py` (NEW — deterministic, test-only helper, C4-permitted)
Pure function, **no LLM, no SQL** — consumes JSON, emits JSON:
- `grade_case(case: dict, critic_outputs: list[dict]) -> dict` → the per-case grading record from the 009-01 README schema: `{case_id, recall, missing_defects, lens_purity_violations, severity_match, injection_recalled, verdict_match}`.
- **Recall**: every `case.expected_findings[].defect_id` is matched by some critic finding under (at least) its expected lens at ≥ `min_severity`. Defect matching is by `defect_id` — the runner asks each critic to tag findings it emits with the case's candidate `defect_id`s (the recipe supplies them as the "known defect catalogue" for grading ONLY — NOT shown to the critics during the audit, to keep recall honest; matching is done post-hoc by span/claim overlap → `defect_id`). Implement post-hoc matching: a critic finding maps to a `defect_id` iff its `claim` span overlaps the expected defect's span (substring/normalised-overlap heuristic documented in the docstring).
- **Lens-purity−C2** (the 009-01 README predicate): group matched findings by `defect_id`; a `defect_id` with findings under >1 lens is a violation **unless** the lens set is exactly `{factual, security}` AND `case.injection_class` is true. Emit each violation as `{defect_id, lenses}`.
- **Severity-match**: for each matched defect, the caught severity band equals the expected band (using `_SEV_ORDER` from `wiki_verify_multi` for ordering).
- **Verdict-match**: derive PASS/FAIL from the critic findings by **importing and calling** `_is_fail` (with `_FAIL_LENSES`/`_SEV_ORDER`) from `wiki_verify_multi` — **no local reimplementation** of the threshold rule (plan-review MINOR-2) — and compare to `case.expected_verdict`.
- **False-positive**: any critic finding whose span overlaps a `case.forbidden_findings` entry → recorded as a `false_positive` (fails the case).
- `grade_run(cases, run_outputs) -> dict` → aggregate: per-metric pass-rate + the per-case records (the report body 009-03/05 render).

> grade.py **imports and calls** `_is_fail` (+ `_SEV_ORDER` / `_FAIL_LENSES`) from `scripts.wiki_skills.wiki_verify_multi` — it does **not** reimplement the rule — so the grader's PASS/FAIL derivation can NEVER drift from the shipped gate (the same L-1 sync invariant, applied to the eval).

#### File: `workflows/wiki-verify-eval.md` (NEW — orchestrator-run recipe; symlinked per repo convention)
The reproducible recipe (run by the orchestrator; the run is recorded, not a pytest gate):
1. Read `skills/wiki-verify/evals/evals.json` + the lens definitions from `skills/wiki-verify/SKILL.md` (whichever version is on disk — that's the baseline/enriched switch).
2. For each case, **fan out 4 critic sub-agents** (factual/logic/security/completeness), each given ONLY: the case `question` + `answer` + `examined` sources (H-6 fenced) + its lens prompt extracted from `SKILL.md`. Critics are **blind** to `expected_findings` (honest recall). Structured output: `{lens, findings:[{severity, claim, source, note}]}`.
3. Collect the 4 outputs per case → `grade.py grade_run` → write the report (009-03/05 own the report path + the human narrative).
4. The recipe documents that it is the *same* harness for baseline and enriched; reproducibility = same `evals.json` + same recipe, the only diff is `SKILL.md`.

#### File: `tests/test_wiki_verify_grade.py` (NEW — deterministic, green-throughout)
Unit-test `grade.py` on **synthetic** critic-output fixtures (no LLM, no mocking-a-model — the inputs are hand-written critic JSON):
- a clean case with zero findings → recall n/a, purity clean, verdict PASS-match;
- case-2-shaped synthetic input where `factual` AND `completeness` both flag the same hallucination `defect_id` → **lens_purity_violation** recorded (the non-injection bleed IS a violation);
- case-3-shaped synthetic input where `factual` AND `security` both flag the injection `defect_id` on an `injection_class: true` case → **NOT** a violation (the sanctioned C2 overlap);
- a synthetic input missing an expected defect → `recall=false` + `missing_defects` populated;
- a synthetic input flagging a `forbidden_findings` span → false-positive recorded;
- severity drift (expected high, caught low) → `severity_match=false`.

## Test Cases
### Unit (deterministic — the load-bearing tests)
1. **TC-01 (C2 carve-out)**: `{factual,security}` co-report on `injection_class` defect → NOT a purity violation; the SAME pair on a non-injection defect → IS a violation. *(This is the single most important grader test — it operationalises the C2 backstop vs bleed distinction.)*
2. **TC-02 (recall)**: missing expected defect → `recall=false`.
3. **TC-03 (severity)**: caught band ≠ expected band → `severity_match=false`.
4. **TC-04 (verdict parity)**: grade.py's PASS/FAIL derivation == `_is_fail` on the same findings (grade.py **calls** `_is_fail`, so this is parity-by-construction; the test pins it).
5. **TC-05 (false-positive)**: a forbidden span flagged → case fails.
6. **TC-06 (matcher negative — plan-review MINOR-3)**: a critic finding whose `claim` span is a **near-miss** (overlaps no expected defect span beyond the heuristic threshold) does **NOT** match any `defect_id` — pins the overlap threshold so a too-loose matcher can't silently inflate recall or hide a purity violation in the recorded runs.

## Acceptance Criteria
- [ ] `grade.py` deterministic (no LLM/SQL); imports the gate's severity/FAIL semantics so it can't drift.
- [ ] `workflows/wiki-verify-eval.md` recipe committed + symlinked; critics are blind to expectations.
- [ ] `tests/test_wiki_verify_grade.py` green — esp. TC-01 (the C2 carve-out) and TC-04 (verdict parity).
- [ ] No prompt edit, no code/schema change to shipped `scripts/`; full `pytest` green; `mypy --strict` clean (grade.py is typed).

## Notes
Phase-1 "assert harness". The deterministic grader is what makes the otherwise-LLM measurement reviewable: the LLM produces findings, but the SCORING is deterministic + tested. Depends on 009-01 (the eval shape). grade.py is a test-only/eval helper (C4 permits it; it is NOT part of the shipped `wiki_verify_multi` contract). Do NOT mock a model anywhere — grade.py is tested on synthetic critic JSON, and the real fan-out runs live in 009-03/05.
