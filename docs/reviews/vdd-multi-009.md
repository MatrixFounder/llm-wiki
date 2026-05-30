# VDD Multi-Adversarial Report — TASK 009 (`wiki-verify` critic-prompt hardening)

**Date:** 2026-05-30 · **Critics:** critic-logic · critic-security · critic-performance (parallel, Layer-A)
**Scope:** the TASK-009 change set — the eval tooling (`grade.py`, `evals.json`, the recipe,
the contract test) + the enriched `wiki-verify` SKILL.md. Operator bar: *the eval tools must
work correctly + the skill must be production-grade.*
**Verdict:** **PASS** — 2 HIGH + 2 MED (logic) fixed inline + regression-locked; critic-logic
iteration-2 **clean-pass**; security + performance **bikeshedding-only**. Final: **702 pytest /
4 skip, mypy --strict clean, zero code/schema change**.

## Findings + dispositions

### 🟠 HIGH — L-1 (logic): `injection_recalled` credited a wrong-lens catch [FIXED]
`grade.py`'s `injection_recalled` was `any(d in matched …)` — `matched[defect_id]` is keyed by
**any** lens, so a `logic`/`completeness`-only catch (both FAIL-lenses missed the injection)
falsely greenlit the *binding injection-recall floor*. A future regression breaking security-lens
injection detection would not have tripped it. **Fix:** require a `_FAIL_LENSES` (`factual`/
`security`) catch. Regression: `test_injection_recall_requires_a_fail_lens_catch` (logic/completeness
-only → False; factual-only → True). **iter-2 CLOSED.**

### 🟠 HIGH — L-2 (logic): case-3 factual `critical` floor was fragile + self-contradictory [FIXED]
`evals.json` case-3 factual `min_severity: critical` contradicted its own `expected_output` "(high)"
and the SKILL.md rubric (ungrounded insertion = `high`; `critical` is the *security* lens's injection
band). A rubric-following factual critic emits `high` < `critical` → recall MISS. (Origin: an earlier
calibration over-correction.) **Fix:** revert to `high`. Severity-match drops 0.571→0.429 on **both**
runs (the backstop's high-vs-critical drift now honestly counted — still flat/non-regressed).
**iter-2 CLOSED.**

### 🟡 MEDIUM — L-3 (logic): verdict/exit invariant unpinned [FIXED]
No test asserted `_is_fail(expected_findings@min_severity) == expected_verdict` / `expected_exit`.
All 7 cases were manually consistent, but a future edit could declare a self-contradictory case.
**Fix:** `test_expected_verdict_and_exit_consistent_with_is_fail` (all 7 cases). **iter-2 CLOSED.**

### 🟡 MEDIUM — L-4 (logic): recorded grading not reproducible [FIXED]
The recorded `*-grading.json` headline numbers were hand-asserted; a `grade.py` change could
silently invalidate them. **Fix:** committed the raw critic outputs (`reports/{baseline,enriched}-run-outputs.json`)
+ `test_wiki_verify_reports.py` asserts `grade_run(evals.json, run-outputs) == grading.json`. The
deterministic measurement is now reproducible (the LLM fan-out is recorded, the scoring pinned).
**iter-2 CLOSED.**

### 🟢 Security — bikeshedding-only (production-grade confirmed)
critic-security **independently re-derived** (did not trust the 009-06 audit): H-6 preserved
byte-for-byte; the C2 backstop genuinely preserves FAIL-redundancy (the banned `logic`/`completeness`
lenses were never in `_FAIL_LENSES`, so removing their injection re-report subtracts zero gate power);
`grade.py` pure (no exec/traversal/ReDoS/leakage); case-3 injection consumed strictly as inert fixture
data; verdict/grounding/Python-enforced controls byte-stable; no `scripts/`/`sql/` change. The only
actionable item — the defang token-list is bypassable for **future** un-fenced directives — is the
already-filed **L-009-3** (LOW; SECURITY-label PR review is the backstop). Re-rated the prior audit's
F-1 MEDIUM → LOW (not exploitable in the current change set). 0 CRITICAL / 0 HIGH / 0 current MED.

### 🟢 Performance — bikeshedding-only [doc fix applied]
Grader is pure + O(F×E×L) on cold code (trivial at real scale); both regexes ReDoS-proof (linear,
100k-char-safe); no leaks, no stray writes, no silent truncation. One LOW: the recipe's `4 × len(cases)`
sub-agent fan-out (28 today, 400 at 100 cases) was undocumented → **added a cost note** to
`workflows/wiki-verify-eval.md`. Tests re-read fixtures per test (negligible; deliberate isolation).

## Convergence
critic-logic **clean-pass** (iter-2, all 4 fixes verified by exhaustive trace); critic-security
**bikeshedding-only** (production-grade: yes); critic-performance **bikeshedding-only**. 5 new
regression tests added (702 pytest / 4 skip; mypy strict clean, 62 files). Headline delta **unchanged**
by the fixes (purity 10→3, FP 2→0, verdict/recall →1.0, injection 100%); severity 0.571→0.429 (honest).
Nothing auto-committed.
