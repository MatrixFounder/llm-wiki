# `wiki-verify` prompt — BENCHMARK v2 (32 diverse cases)

**TASK 009 follow-up — the proper benchmark the operator asked for.** Replaces the
7-case toy set (`evals.json`, all "hermes") with **32 cases across 12 diverse fictional
domains** (`evals-v2.json`). Source vault: `samples/eval-bench/` (12 self-contained
~194-word articles, indexed). Same deterministic grader (`grade.py`) on both prompts;
the only variable is `SKILL.md` (thin baseline `23cbe93` vs scoped enriched `2a0d78f`).

## Methodology (against author-bias)
- **24 seeded cases** — objective ground-truth *by construction*: a script mechanically
  plants a known defect (number-mutation, injection string, omission, circular text,
  benign-token FP-guard, mild qualifier). Zero author judgment in the ground-truth.
- **8 natural cases** — a synthesizer writes a real answer (with drift pressure); the
  ground-truth is the **consensus of 2 INDEPENDENT labelers** blind to the scoped prompt
  (inter-annotator agreement: 3 consensus defects from 12 raw labeler findings — labelers
  disagree on borderline calls, so only agreed defects become ground-truth).
- Run: 256 critic sub-agents (32 × [4 baseline + 4 enriched]); raw outputs committed
  (`reports/v2/*-run-outputs.json`) → reproducible via the same `grade.py`.

## Headline — modest, with a twist

| metric | baseline | enriched | 95% bootstrap CI on Δ (enr−base, 5000×) |
|---|---|---|---|
| purity-violations (Σ, raw) | 19 | 14 | **[−9, −1]** — significant |
| recall-rate | 0.969 | 0.938 | [−0.094, 0] — ~flat, not sig. |
| verdict-match | 0.688 | 0.781 | [−0.094, +0.281] — **not** sig. |
| severity-match | 0.562 | 0.719 | (improved) |
| false-positives (Σ) | 2 | 2 | [0, 0] — no change |
| injection-recall | 1.00 | 1.00 | held (the hard floor) |

## The twist — composition of the bleed (the finding the toy set HID)

Raw violations only dropped 19→14. But decompose the **substantive** violations
(≥2 lenses flagging the same defect at ≥medium):

| substantive bleed type | baseline | enriched |
|---|---|---|
| `factual`/`logic`/`completeness` cross-bleed (the v1 problem) | 19 | **~3** |
| **`security` flagging a NON-injection** (number-error as "numerical inversion") | **0** | **10** |

So the enriched prompt:
- ✅ **Dramatically fixed** the factual/logic/completeness cross-bleed it was designed for
  (19 → ~3) — the core mechanism **works on diverse content**.
- ❌ **Introduced a NEW bleed**: the scoped `security` lens over-reaches onto **numeric
  factual errors** (a wrong number contradicting the source), flagging them as a
  "numerical inversion" / data-integrity concern (0 → 10). This nets the raw win down to
  a modest 19→14.

This is the load-bearing benchmark finding: the v1 toy set (all "hermes", fabricated
*additions*) never triggered the security lens, so it reported a clean "10→3 / −70%".
The diverse seeded cases (number-*mutations*) expose that the enriched `security` lens
does NOT cleanly exclude factual/numeric errors. **→ KNOWN_ISSUES L-009-4** (actionable
next iteration: add to the security lens "a wrong/contradicting NUMBER or fact is
`factual`'s lane, NOT security — only smuggled directives are yours").

> Caveat: the security-overreach magnitude is **amplified** by the seeded construction
> (6 of 24 seeded cases are number-mutations). It is a real prompt weakness, but its
> raw count is inflated by the eval's defect mix.

## By construction

| set | n | violations | FP | recall |
|---|---|---|---|---|
| seeded (objective) | 24 | 16 → 13 | 2 → 2 | 0.96 → 0.96 |
| natural (consensus-labeled) | 8 | 3 → 1 | 0 → 0 | 1.00 → 0.88 (1 case) |

Natural cases are mostly clean by consensus (real LLM answers are largely faithful) — they
test **precision**, and both prompts hold (FP 0→0). The single natural recall miss
(drummond) is within noise (n=8).

## Honest verdict

1. **The anti-bleed mechanism is real and statistically significant** on diverse content
   (purity Σ 19→14, CI [−9,−1]; the targeted factual/logic/completeness bleed 19→~3).
2. **But the net win is MODEST (−26% raw), not the toy set's −70%** — and the enriched
   prompt **introduced a new `security`-lens overreach** (L-009-4) that masks most of the
   gain. The toy benchmark **overstated the result**; the diverse benchmark corrected it
   *and* found an actionable regression.
3. **Severity calibration genuinely improved** (0.56→0.72).
4. **Verdict-correctness improved directionally** (0.69→0.78) but is **not statistically
   significant** on 32 cases (CI crosses 0). Recall is ~flat (slight, non-significant
   down-lean). FP and injection-recall unchanged.
5. **Net:** the enriched prompt is a **modest net improvement** (less factual/logic/comp
   bleed + better severity, injection floor held) **with a clear, fixable new weakness**
   (security over-reach). Recommend a v3 iteration tightening the security lens, then
   re-running this committed 32-case benchmark.

**This is what the operator's instinct bought:** a 7-case toy "−70%" became a measured,
CI-bounded "−26% with a new security-bleed regression and an actionable fix" — the
difference between a marketing number and a real one.
