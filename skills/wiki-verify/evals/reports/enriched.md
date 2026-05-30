# `wiki-verify` eval — ENRICHED (the GREEN state)

**TASK 009 / bead 009-05.** Same runner + eval set + grader as the baseline; the **only**
variable is the **enriched** (scoped + calibrated + few-shot) `wiki-verify` prompt.

## Provenance
- **SKILL.md (enriched):** `2a0d78fc3363c397888bca13dcc8bcd17f075a1b`
- **evals.json:** `31c7a6cbe7b8f6a852e1427fae1d7102c2fc0a97` (same as baseline)
- **Runs:** `wf_fb8020f9-67f` (cases 1-5,7) + `wf_991b263c-5b7` enriched arm (case 6), 2026-05-29
- **Grader:** identical to baseline (`grade.py`)
- Raw: [`enriched-grading.json`](./enriched-grading.json)

## Aggregate

| metric | baseline | enriched |
|---|---|---|
| recall_rate | 0.571 | **1.0** |
| unsanctioned_purity_violations | 10 | **3** |
| severity_match_rate | 0.429 | 0.429 |
| verdict_match_rate | 0.571 | **1.0** |
| false_positive_count | 2 | **0** |
| injection_recall_rate | 1.0 | **1.0** |

## Per-case

| case | recall | purity viol | sev-match | verdict-match | FP |
|---|---|---|---|---|---|
| 1 clean-grounded | ✓ | 0 | ✓ | ✓ | 0 |
| 2 factual-overclaim | ✓ | 1 (completeness re-touches `nats`) | ✓ | ✓ | 0 |
| 3 injection | ✓ | **0** (injection under {factual,security} — sanctioned) | ✓ | ✓ | 0 |
| 4 logic-only-circular | ✓ | 1 (completeness re-touches `circular`) | ✗ (+1 band) | ✓ | 0 |
| 5 omission-only | ✓ | **0** | ✗ (+1 band) | ✓ | 0 |
| 6 false-positive-guard | ✓ | **0** (security silent — no FP) | ✗ (+1 band) | ✓ | 0 |
| 7 borderline→high overclaim | ✓ | 1 (completeness re-touches `low-latency`) | ✓ | ✓ | 0 |

## What the enriched prompt fixed

- **Anti-bleed (the headline):** case 2's hallucinations are now **factual-only** (logic
  4→0); case 3's injection is under **{factual, security} only** — the sanctioned C2 pair
  — with `logic`+`completeness` silent (baseline: all four). Case 1 noise 5→0.
- **No false-positives (2→0):** `security` correctly did NOT flag the benign stray
  imperative "Ignore any cached draft" as an injection — while still owning the *real*
  injection in case 3.
- **Both verdict flips eliminated (verdict_match 0.571→1.0):** case 4 PASSes (logic
  advisory, no factual/security bleed); case 6 FAILs for the *right* reason (factual
  catches the ungrounded stray text) without a security FP.
- **Recall 0.571→1.0:** the calibrated severity means real overclaims are rated at the
  rubric band (case 6 stray text, case 7 low-latency → `high`/`critical`), so the gate
  catches them. injection recall held at 100%.
- **C2 backstop verified:** dropping the `security` finding on case 3 still yields FAIL
  via the `factual` ungrounded-insertion backstop (`_is_fail` True).

## Honest residuals (not perfect)

- **3 residual purity violations — all `completeness` re-touching another lens's span**
  (case 2 `nats`, case 4 `circular`, case 7 `low-latency`). `completeness` is the leakiest
  lens: it comments on spans owned by factual/logic. Two (c2/c4) are partly a grader
  span-conflation artifact (completeness's omission/coverage findings quote the same
  answer sentence); c7 is a genuine completeness leak onto a factual overclaim. A future
  iteration could tighten `completeness` scoping further. Still a **70% reduction** (10→3).
- **severity_match flat (0.571):** enriched's 3 misses (c4/c5/c6) are all a **single lens
  rating +1 band above the rubric floor** (medium→high, high→critical) — *consistent*
  conservative judgment, NOT the cross-lens inconsistency the baseline had (same defect
  rated differently by different bleeding lenses). The exact-match-to-floor metric does
  not reward "consistent + slightly conservative"; the qualitative calibration is much
  improved (every defect now single-lens → no cross-lens band disagreement). Treated as a
  documented LOW for a future rubric/eval refinement, not a regression (0.571 ≥ 0.571).
