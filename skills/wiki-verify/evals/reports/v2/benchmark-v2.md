# `wiki-verify` prompt — BENCHMARK (32 diverse cases, baseline → v2 → v3)

**TASK 009 follow-up — the proper benchmark the operator asked for.** Replaces the
7-case toy set (all "hermes") with **32 cases across 12 diverse fictional domains**
(`evals-v2.json`; source vault `samples/eval-bench/`). Same deterministic grader
(`grade.py`) on every prompt; the only variable is `SKILL.md`.

- **baseline** = thin prompt (`23cbe93`).
- **enr-v2** = scoped/calibrated prompt (`2a0d78f`).
- **enr-v3** = v2 + the L-009-4 security-lens fix (current `SKILL.md`).

## Methodology (against author-bias)
- **24 seeded** cases — objective ground-truth *by construction* (a script mechanically
  plants a known defect: number-mutation, injection, omission, circular text, FP-guard,
  mild qualifier). Zero author judgment in the ground-truth.
- **8 natural** cases — real synthesized answers; ground-truth = the **consensus of 2
  INDEPENDENT labelers** blind to the scoped prompt (3 consensus defects from 12 raw
  labeler findings — they disagree on borderline calls, so only agreed defects count).
- 256 + 128 critic sub-agents; raw outputs committed (`reports/v2/*-run-outputs.json`)
  → reproducible via `grade.py` (`tests/test_wiki_verify_v2.py`).

## Results — two validated iterations (v3 security fix, v4 completeness fix)

| metric | baseline | enr-v2 | enr-v3 | **enr-v4** |
|---|---|---|---|---|
| raw purity-violations (grade.py) | 19 | 14 | 12 | **8** |
| substantive violations (≥medium; `substantive_purity_violations`) | 19 | 13 | 12 | **8** |
| **security-overreach** (security flags a NON-injection) | 0 | 10 | **0** | **0** |
| recall-rate | 0.969 | 0.938 | 0.938 | 0.938 |
| verdict-match | 0.688 | 0.781 | 0.844 | 0.812 |
| severity-match | 0.562 | 0.719 | 0.750 | **0.812** |
| false-positives (Σ) | 2 | 2 | 2 | 2 |
| injection-recall | 1.00 | 1.00 | 1.00 | **1.00** |

95% bootstrap CI (5000×) on the **enr-v2 − baseline** raw-violation delta: **[−9, −1]**
(significant). recall Δ [−0.094, 0] (~flat, n.s.).

**Cumulative: raw lens-bleed 19 → 8 (−58%), severity-match 0.56 → 0.81, recall held
(0.938) + injection 100% + FP 2 throughout** — driven by two benchmark-found, separately
re-validated prompt fixes (the toy set's single "−70%" was a mirage; the real story is
−58% reached in two honest steps, each measured).

## The honest story (the benchmark drove TWO validated fixes)

1. **The toy set's "−70%" was a mirage.** On 7 toy cases (all "hermes", fabricated
   *additions*) the scoped prompt scored a clean "10→3". On 32 diverse cases the *same*
   prompt (enr-v2) only managed raw `19→14`, **and** introduced a regression the toy set
   could not surface (below). (An even earlier draft of this report then *over*-corrected,
   wrongly claiming a `19→3` core-bleed drop — a flawed decomposition; corrected here.)
2. **enr-v2 introduced a NEW regression: the `security` lens over-reached onto
   numeric-factual errors** (a wrong number flagged as a "numerical inversion"):
   security-on-non-injection `0 → 10`. **enr-v3 fixed it → `0`** (out-of-scope line: a wrong
   number is `factual`'s lane). Independently security-audited (PASS — the exclusion is
   defect-class-scoped, an injection can't be disguised as a number).
3. **enr-v4 fixed the residual factual↔completeness conflation** (L-009-5): `completeness`
   now quotes the *missing source phrase*, not the answer sentence carrying a factual
   defect — so its omission findings stop being mis-matched to the factual number error.
   Raw violations `12 → 8`; severity `0.750 → 0.812`; recall + injection held.

**Net across the two iterations: raw lens-bleed `19 → 8` (−58%)**, severity-match
`0.562 → 0.812`, with recall (`0.938`), injection-recall (`100%`) and false-positives (`2`)
held throughout. The `verdict-match` wobble `0.844 → 0.812` (v3→v4) is **LLM run-to-run
noise on one case** — the completeness edit cannot move the gate verdict (completeness is
advisory). Each fix was found by the diverse benchmark and separately re-measured on the
committed 32-case set.

## Residual (honest)
~8 raw violations remain — the irreducible tail of genuine borderline cross-lens overlap +
a small grader-matching slack (the `substantive_purity_violations` helper, added in v4,
already excludes low-severity "confirmation" findings; the remaining 8 are ≥medium). Recall
is ~flat with a slight non-significant down-lean vs baseline. A v5 could chase the last few
with per-case matcher tuning, but diminishing returns: −58% bleed with every safety floor
held is a solid landing.

## Bottom line
The diverse 32-case benchmark turned a marketing **"−70% (one toy run)"** into a measured,
reproducibility-pinned **"−58% over two validated iterations (v3 security + v4
completeness), each separately audited/tested, with recall + injection + FP held"** — and
found two real prompt regressions/weaknesses the toy set could never have shown. That is
exactly what the operator's "make a good sample" instinct was worth.
