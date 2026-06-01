---
id: D-010-2
type: known-issue
status: mitigated
opened_at: 2026-05-31
category: security
slug: d-010-2-completeness-omission-bleed-on-inversion-defects-v3-quantified
---

# completeness-omission bleed on inversion defects (v3-quantified)

- **Symptom**: On inversion-type FAIL cases (temporal / negation / composition mis-join /
  entity swap / fabrication), the `completeness` critic adds a "the answer omitted the true
  source fact" finding alongside `factual`'s inversion finding. The grader matches the
  omission to the same `defect_id` → a `factual`+`completeness` unsanctioned lens-purity
  duplicate. eval-v3 measured **7 such violations across 22 cases** (`grade.py`
  `substantive_purity_violations`: total=7, core=7, security_on_noninjection=0).
- **Root cause**: the SAME omission-conflation class already documented as the **L-009-5
  residual** (the v4 completeness fix reduced but did not eliminate it). v3 makes it more
  visible because v3's defects are predominantly *inversions* — for an inversion, "the
  answer's claim is false" (factual) and "the answer omitted the true fact" (completeness)
  are two views of the *same* fact, so a rule-compliant completeness omission still overlaps
  the factual defect's source region.
- **Affected components**: `skills/wiki-verify/SKILL.md` (`completeness` lens), and/or
  `skills/wiki-verify/evals/grade.py` (omission→defect attribution by omitted-content span).
- **Impact**: lens-purity NOISE only — recall 1.0, verdict-match 1.0, false-positives 0 on
  eval-v3 (`reports/v3/benchmark-v3.md`). The gate is sound; this does not flip any verdict.
- **Fix plan (deferred)**: a future `completeness`-tightening prompt change (e.g. "do not
  emit an omission for a fact the answer actively *misstates* — that defect is already
  owned by factual; only flag a fact the answer is wholly silent on") and/or a grader
  attribution refinement. SECURITY-SENSITIVE (touches the live prompt) → its own
  code-review + security-audit PR, gated by the full-corpus v1+v2+v3 no-degradation A/B
  (PLAN §"Regression safety"); v3 is the standing "before" measurement.
- **Prevention**: `tests/test_wiki_verify_v3.py` + the committed `reports/v3/` pin the
  current residual so a future fix can show the delta and prove no v1/v2 regression.
- **Resolution (2026-06-01, mitigated)**: shipped the deferred prompt fix — a
  "**Misstatement is NOT omission**" block in the `completeness-faithfulness` lens
  (`skills/wiki-verify/SKILL.md` v1.1→1.2): a fact the answer states *wrongly* (a value a
  source contradicts) is `factual`'s inversion, not a completeness omission; completeness
  fires only on *wholly-silent* facts. An anti-dilution clause preserves omission breadth.
  **Evidence** (`reports/v3/completeness-bleed-d010-2.md`; completeness-only re-run, factual/
  logic/security held fixed): full-corpus no-degradation A/B **PASS** (v1/v2/v3 non-degrading;
  v2 completeness-recall 0.906→0.938). v3 **multi-rep** (5 samples/arm, 220 sub-agents):
  unsanctioned purity mean **4.8→2.8 (≈ −42%)** with **recall 1.0 and FP 0 in all 10 reps**.
  **Mitigated, not eliminated** — the bleed is noise-dominated (v1.1 purity varies 4–9), so
  the reduction is real-in-expectation, not deterministic; a full deterministic fix would need
  a `grade.py` attribution change (re-pins every committed grading + alters the lens-purity
  metric semantics) and is not worth it for a noise-only metric. **Gate-neutral by
  construction** (`completeness ∉ _FAIL_LENSES` → no verdict can flip). Gates: security-audit
  + code-review on the v1.2 prompt.
