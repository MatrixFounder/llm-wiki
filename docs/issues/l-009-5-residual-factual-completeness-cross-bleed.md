---
id: L-009-5
type: known-issue
status: fixed
opened_at: 2026-05-30
category: logic
slug: l-009-5-residual-factual-completeness-cross-bleed
---

# residual factual↔completeness cross-bleed

- **Symptom**: after the v3 security fix, the dominant residual lens-bleed is a defect that
  `factual` flags AND `completeness` also touches (core bleed ≥2 of factual/logic/completeness
  at ≥medium: baseline 19 → enr-v2/v3 **13**, only −32%). The anti-bleed enrichment is real but
  far more modest than the toy set's "−70%".
- **Root cause**: two parts. (1) a real prompt residual — `completeness` still comments on
  spans near a factual defect. (2) a **grader artifact** — a `completeness` omission finding
  whose `claim` quotes the answer sentence that *also* carries the factual defect gets matched
  (by span overlap) to that factual defect → counted as `factual`+`completeness` bleed (the
  same omission-conflation class noted in v1). Plus `low`-severity *confirmation* findings
  ("this claim is fine, just noting") that `grade.py` counts as the lens flagging the defect.
- **Affected**: `skills/wiki-verify/SKILL.md` (`completeness` lens), `skills/wiki-verify/evals/grade.py`.
- **Fix plan (v4)**: (prompt) tighten `completeness` to quote the *omitted source phrase*,
  never the answer sentence carrying another lens's defect; (grader) attribute omission
  findings by their omitted-content span (not the quoted answer span) + exclude `low`-only
  single-lens confirmations from lens-purity. Then re-run `evals-v2.json`.
- **Resolution (v4, 2026-05-30)**: (prompt) added to the `completeness` lens in
  `skills/wiki-verify/SKILL.md` — "quote the MISSING SOURCE phrase (the content the answer
  left out), NOT the answer sentence … NEVER quote a sentence that carries a factual / logic
  / security defect". (grader) added the **additive** `grade.py::substantive_purity_violations`
  helper (≥medium cross-lens duplicates, excludes `low` confirmations + the sanctioned C2
  pair; does NOT change `grade_run`, so the committed v1/v2 grading pins still hold) +
  `tests/test_wiki_verify_grade.py::test_substantive_purity_excludes_low_confirmations_and_c2`.
  **Re-ran the benchmark (enr-v4)**: raw violations 12→**8** (cumulative baseline 19→8, −58%);
  severity 0.750→**0.812**; recall held (0.938) + injection 100% + FP 2. See
  `evals/reports/v2/benchmark-v2.md` + `enriched-v4-{run-outputs,grading}.json`. The v4 edit
  touches `completeness` only (zero security surface; contract test green). Residual ~8 raw
  violations = the irreducible borderline tail (diminishing returns).
