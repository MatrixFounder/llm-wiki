---
id: L-009-1
type: known-issue
status: open
opened_at: 2026-05-29
category: logic
severity: LOW
slug: l-009-1-completeness-is-the-leakiest-lens-3-residual-purity-violations
---

# `completeness` is the leakiest lens (3 residual purity violations)

- **Symptom**: after the anti-bleed enrichment, 3 unsanctioned cross-lens purity
  violations remain — all `completeness` re-touching a `factual`/`logic` defect span
  (case 2 `nats`, case 4 `circular`, case 7 `low-latency`). c2/c4 are partly a grader
  span-conflation artifact (completeness's omission/coverage findings quote the same
  answer sentence that carries the other lens's defect); c7 is a genuine completeness leak
  onto a factual overclaim.
- **Root cause**: `completeness` is the broadest lens (it comments on omissions +
  additions across the whole answer); the prose scoping reduced bleed 10→3 but didn't
  fully stop completeness from quoting spans owned by factual/logic.
- **Affected**: `skills/wiki-verify/SKILL.md` (completeness lens scoping); the eval grader's
  span-matcher (`skills/wiki-verify/evals/grade.py`).
- **Fix plan**: tighten the completeness lens ("report the *omitted* content, do NOT quote
  the answer's other-lens defects"), and/or sharpen the grader's omission-vs-quote
  attribution. A future enriched re-run could target violations → 0. Defer — 70% reduction
  is the shipped win; recall + FP + verdict-correctness all hit target.
