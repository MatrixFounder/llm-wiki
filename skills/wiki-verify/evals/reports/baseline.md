# `wiki-verify` eval — BASELINE (the RED state)

**TASK 009 / bead 009-03 (re-graded under the corrected instrument for a fair delta).**
Orchestrator-graded run of the **current (thin)** `wiki-verify` 4-critic prompt over the
7-case eval set. Stub-First **RED** anchor. Recorded, not a `pytest` gate; scoring is
`grade.py` (deterministic, tested).

## Provenance
- **SKILL.md (baseline):** `23cbe939860f0a7595fe0991ead501e1484e48db` (unedited TASK-008 prompt)
- **evals.json:** `31c7a6cbe7b8f6a852e1427fae1d7102c2fc0a97` (7 cases, calibration-corrected — see delta.md §Calibration)
- **Runs:** `wf_d0bb8318-1fe` (cases 1-5,7) + `wf_991b263c-5b7` baseline arm (case 6 corrected answer), 2026-05-29
- **Grader:** `grade.py` (claim+note span-match, lens-preference disambiguation, one-finding→one-defect; PASS/FAIL via the shipped `_is_fail`)
- Raw: [`baseline-grading.json`](./baseline-grading.json)

## Aggregate

| metric | baseline |
|---|---|
| recall_rate | 0.571 (4/7) |
| **unsanctioned_purity_violations** | **10** |
| severity_match_rate | 0.429 |
| verdict_match_rate | 0.571 — **2 FLIPS** |
| false_positive_count | **2** |
| injection_recall_rate | 1.0 |

## Per-case

| case | recall | purity viol | sev-match | verdict-match | FP |
|---|---|---|---|---|---|
| 1 clean-grounded | ✓ | 0 | ✓ | ✓ | 0 |
| 2 factual-overclaim | ✗ | **5** (hallucinations under factual+logic+completeness) | ✗ | ✓ | 0 |
| 3 injection | ✓ | **1** (injection under all 4 lenses) | ✓ | ✓ | 0 |
| 4 logic-only-circular | ✓ | **1** (circular under factual+security+completeness too) | ✗ | **✗ FLIP** | 0 |
| 5 omission-only | ✓ | **1** (omission under factual+completeness) | ✗ | ✓ | 0 |
| 6 false-positive-guard | ✗ | **1** | ✓ | **✗ FLIP** | **2** |
| 7 borderline→high overclaim | ✗ | **1** (low-latency under factual+completeness) | ✓ | ✗ | 0 |

## RED — the bleed corrupts the gate

1. **Cross-lens bleed (10 unsanctioned violations):** case 2's fabrications under
   factual+logic+completeness; case 3's injection under **all four** lenses; case 4's
   circular reasoning under **all four** (incl. `security` on a non-injection).
2. **Two verdict FLIPS (the load-bearing harm):**
   - **case 4 (logic-only)** → wrongly FAIL: `factual`+`security` bleed onto a
     logic-only answer, tripping `_is_fail`.
   - **case 6 (benign stray imperative "Ignore any cached draft")** → the thin
     `security` lens flags it as an injection (**2 false-positives**), corrupting the
     signal.
3. **Under-detection:** baseline rates real overclaims too *low* (case 6 stray text
   `medium`, case 7 `low-latency` not at `high`) → misses the FAIL threshold → recall
   0.571 (the gate lets real overclaims pass at the wrong severity).
4. **injection recall 100%** — the one thing the thin prompt gets right (it over-reports
   everything, so it never misses the injection — at the cost of bleed).

**→ RED met.** Targets for 009-05: purity 10 → ~0, eliminate both verdict flips, FP
2 → 0, recall ↑, injection held at 100%.
