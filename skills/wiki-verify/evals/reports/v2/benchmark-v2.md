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

## Results (corrected)

| metric | baseline | enr-v2 | enr-v3 |
|---|---|---|---|
| raw purity-violations (grade.py) | 19 | 14 | **12** |
| **core bleed** (≥2 of factual/logic/completeness, ≥med) | 19 | **13** | **13** |
| **security-overreach** (security flags a NON-injection) | 0 | **10** | **0** |
| recall-rate | 0.969 | 0.938 | 0.938 |
| verdict-match | 0.688 | 0.781 | **0.844** |
| severity-match | 0.562 | 0.719 | **0.750** |
| false-positives (Σ) | 2 | 2 | 2 |
| injection-recall | 1.00 | 1.00 | 1.00 |

95% bootstrap CI (5000×) on the **enr-v2 − baseline** raw-violation delta: **[−9, −1]**
(significant). recall Δ [−0.094, 0] (~flat, n.s.); verdict-match Δ [−0.094, +0.281] (n.s.).

## The honest story (three corrections to the toy-set narrative)

1. **The core anti-bleed is real but MODEST — `19 → 13` (−32%), not the toy set's −70%.**
   The factual/logic/completeness cross-bleed the enrichment targets drops by about a
   third on diverse content. (An earlier draft of this report wrongly claimed `19 → ~3`
   — that was a flawed decomposition; the clean core-bleed number is **13**, and v3 does
   not move it.)
2. **enr-v2 introduced a NEW regression the toy set hid: the `security` lens over-reached
   onto numeric-factual errors** (flagging a wrong number as a "numerical inversion"):
   security-on-non-injection went `0 → 10`. **enr-v3 fixes it cleanly → `0`** (added an
   explicit out-of-scope line: a wrong number is `factual`'s lane, not security). This is
   the concrete value the diverse benchmark delivered — it found and then verified the fix
   of a regression invisible on 7 toy cases.
3. **enr-v3 is the best version end-to-end**: verdict-correctness `0.688 → 0.844`,
   severity-match `0.562 → 0.750`, recall held (`0.938`, injection **100%** throughout),
   FP unchanged — with the security regression gone. But raw violations only fell `14→12`
   because the removed security findings were piled on top of an **already-bled
   factual↔completeness** pair, so eliminating security rarely dropped a defect below the
   2-lens threshold.

## Residual + next lever (honest)

The dominant residual is the **factual↔completeness cross-report** (~13 core violations):
a numeric/factual defect that `factual` flags AND `completeness` also touches while
flagging a nearby omission (its `claim` quotes the same answer sentence). This is **partly
real bleed + partly a grader artifact** (the omission-conflation noted in v1: a
completeness finding that quotes the answer sentence carrying the factual defect gets
attributed to that defect). Two levers for a v4:
- **prompt**: tighten `completeness` to quote the *omitted source phrase*, never the
  answer sentence carrying another lens's defect.
- **grader**: a refinement excluding low-severity confirmations + attributing omission
  findings by their *omitted-content* span, not the quoted answer span.
Tracked as **KNOWN_ISSUES L-009-5**.

## Bottom line
The diverse 32-case benchmark turned a marketing "−70%" into a measured, CI-bounded
**"−32% core anti-bleed, a security regression found-and-fixed (v3), better verdict +
severity, recall + injection held"** — and a clear, honest residual to chase next. That
gap is exactly what the operator's "make a good sample" instinct was worth.
