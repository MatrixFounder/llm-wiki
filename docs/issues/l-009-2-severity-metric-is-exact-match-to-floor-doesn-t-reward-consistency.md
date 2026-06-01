---
id: L-009-2
type: known-issue
status: open
opened_at: 2026-05-29
category: logic
severity: LOW
slug: l-009-2-severity-metric-is-exact-match-to-floor-doesn-t-reward-consistency
---

# severity metric is exact-match-to-floor, doesn't reward consistency

- **Symptom**: `severity_match_rate` is flat (0.429→0.429) across the delta even though the
  enriched run's severity is qualitatively better. The enriched misses (cases 4/5/6) are
  all a **single lens rating +1 band above the rubric floor** (consistent, conservative),
  whereas the baseline misses were **cross-lens inconsistency** (the same defect rated
  differently by different bleeding lenses). The exact-match-to-fixture-floor metric can't
  distinguish "consistent + slightly conservative" from "inconsistent".
- **Root cause**: `grade.py::grade_case` scores `severity_match` as caught-band == expected
  floor band; with the bleed gone, each defect is single-lens, so cross-lens disagreement
  (the real baseline harm) is no longer measurable by this metric.
- **Affected**: `skills/wiki-verify/evals/grade.py` (`severity_match`), `evals.json` floors.
- **Fix plan**: add a **cross-lens band-consistency** secondary metric (for defects caught
  by >1 lens, do the bands agree within ε?), which directly rewards the anti-bleed→
  consistency improvement; optionally allow a ±1-band tolerance on the exact-match. Defer —
  the headline metrics (purity/FP/verdict/recall) already capture the win.
