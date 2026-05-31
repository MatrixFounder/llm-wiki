# D-010-2 — completeness anti-bleed rule ("misstatement is NOT omission")

**The deferred follow-up to D-010-2.** Adds one block to the `completeness-faithfulness`
lens in `skills/wiki-verify/SKILL.md` (v1.1→1.2): a fact the answer *addresses but states
wrongly* (a value an examined source **contradicts** — an inversion or fabrication) is
**misstated, not omitted** → it is `factual`'s defect, and completeness MUST NOT *also*
report the true source value as an "omission". Completeness fires only on facts the answer
is **wholly silent** on. An explicit anti-dilution clause keeps omission *breadth* unchanged.
This is distinct from D-010-1 (which fires when the answer's value **is** source-grounded and
another source disagrees).

**Why:** the eval-v3 TASK-010 measurement flagged 7 unsanctioned `factual`+`completeness`
purity duplicates on inversion-type FAIL cases — the completeness critic re-reporting the
inverted fact as an "omission" (the L-009-5 omission-conflation class). This is **lens-purity
NOISE only** (recall/verdict/FP were clean), so the goal is to reduce the bleed **without any
regression**.

## Method (single-variable isolation + noise control)

The rule changes **only** the completeness lens, so the A/B re-runs **only the completeness
critic** while holding factual/logic/security **fixed** at their committed current-prompt
outputs. Two measurements:

1. **Full-corpus A/B** (v1+v2+v3, 61 cases, before=v1.1 / after=v1.2, 122 sub-agents) — the
   no-degradation gate. Raw: `d010-2-fullcorpus-ab-runs.json`.
2. **v3 multi-rep** (the 22 v3 cases, **5 independent samples per arm**, 220 sub-agents) —
   because the bleed is **noise-dominated** (the v1.1 completeness critic's purity on these
   cases varies run-to-run), a single before/after draw cannot resolve the effect; 5 reps
   estimate the mean. Raw: `d010-2-v3-multirep-runs.json`.

> ⚠️ The eval `answer`/`examined` bodies are untrusted data (H-6) — fenced by the runner.

## Result 1 — full-corpus no-degradation gate: **PASS** ✅

| corpus | recall | verdict | unsanc. purity | FP | injection |
|---|---|---|---|---|---|
| v1 (7) | 1.000 → 1.000 | 1.000 → 1.000 | 0 → 0 | 0 → 0 | 1.000 → 1.000 |
| v2 (32) | 0.906 → **0.938** | 0.812 → 0.812 | 9 → 8 | 2 → 2 | 1.000 → 1.000 |
| v3 (22) | 1.000 → 1.000 | 1.000 → 1.000 | 6 → 6 | 0 → 0 | n/a |

v1+v2 non-degrading on every aggregate metric (v2 completeness-omission recall even **rose**).
This single v3 draw landed at 6→6 — a low-Δ sample, which is exactly why the multi-rep below
is the authoritative estimate of the v3 effect.

## Result 2 — v3 multi-rep (the authoritative benefit estimate)

5 independent completeness samples per arm, factual/logic/security fixed:

| arm | unsanctioned purity per rep | mean | recall | FP |
|---|---|---|---|---|
| before (v1.1) | 6, 4, 4, 5, 5 | **4.8** (range 4–6) | 1.0 ×5 | 0 ×5 |
| after (v1.2 + D-010-2) | 4, 1, 4, 2, 3 | **2.8** (range 1–4) | 1.0 ×5 | 0 ×5 |

**Δ mean = −2.0 (≈ −42%)**, with **recall held at 1.0 and false-positives at 0 in every one
of the 10 reps.** The arms' ranges overlap (the bleed is noise-dominated: v1.1 purity is
observed anywhere in 4–9 across all experiments), so the reduction is **real-in-expectation,
not deterministic** — a downward distribution shift, not a guaranteed per-run delta.

## Why this is safe to ship

- **Gate-neutral by construction.** `completeness ∉ _FAIL_LENSES` — a completeness finding
  can never move `_is_fail`, so D-010-2 **cannot flip any PASS/FAIL verdict**. The only
  metrics it can touch are completeness-owned recall, purity, and FP.
- **No recall or FP cost.** Across the 10 multi-rep samples + the full-corpus run, v3 recall
  stayed 1.0 and FP 0; v2 completeness-omission recall rose (0.906→0.938). The anti-dilution
  clause ("does NOT shrink your coverage of genuine omissions") held.
- **Principled.** Not re-reporting a *misstated* fact as an *omission* is correct lens
  hygiene — the misstatement is already owned by `factual`. The lens-level transcripts confirm
  the critic now states "the decommissioned-2021 fact is addressed-but-inverted → factual's
  lane, not re-reported here" and flags only genuinely-absent facts.

## Honest framing

This is a **noise-dominated cosmetic-metric** improvement: it shifts the inversion-bleed down
~40% in expectation with zero recall/FP cost, but does **not** drive it to zero (the residual
+ run-to-run variance remain). It is a lens-hygiene hardening, not a deterministic fix. A
fully deterministic elimination would require a **grader-side** attribution change
(`grade.py`: attribute a completeness omission by its omitted-content span, never letting it
match a factual-owned defect), which would re-pin every committed v1/v2/v3 grading and alter
the historical lens-purity metric semantics — out of scope here and not worth it for a
noise-only metric.

## Reproducibility
Raw before/after completeness outputs committed under `reports/v3/`
(`d010-2-fullcorpus-ab-runs.json`, `d010-2-v3-multirep-runs.json`). Grading = the shipped
`grade.py` with factual/logic/security spliced from the committed
`reports/{enriched,v2/enriched-v4,v3/shipped}-run-outputs.json`. SKILL.md v1.2. Run date 2026-06-01.
