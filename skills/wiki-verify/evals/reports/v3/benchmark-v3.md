# `wiki-verify` prompt — BENCHMARK v3 (adversarial reasoning extension, 22 cases)

**TASK 010 — coverage extension.** `evals-v3.json` exercises four defect classes the
v2 set never tested: **temporal**, **negation/polarity-flip**, **multi-document**
(composition + cross-source conflict), and **entity-confusion**. Unlike v2 (a
baseline→enriched prompt A/B), v3 measures **coverage of the SHIPPED prompt** against
these new classes — a single recorded run, not an A/B. Same deterministic grader
(`grade.py`); the LLM 4-critic fan-out is orchestrator-run and recorded.

- **Cases:** 22 = **18 seeded** (mechanical planted defects, objective ground-truth) +
  **4 natural** multi-document (organic answers, consensus-labeled). 6 fictional domains.
- **Run:** shipped `SKILL.md` (git blob `9af0e7e9`); `evals-v3.json` sha256 `3721f473…`;
  run date 2026-05-31. `4 × 22 = 88` blind critic sub-agents (critics never see
  `expected_findings`); raw outputs committed (`reports/v3/shipped-run-outputs.json`) →
  reproducible via `grade.py` (`tests/test_wiki_verify_v3.py::test_v3_shipped_grading_reproducible`).

## Methodology (against author-bias)
- **18 seeded** — objective ground-truth *by construction*: a known defect is planted in
  the answer (drop-a-time-bound, flip-a-polarity-word, mis-join-across-sources,
  swap-a-number-between-entities, fabricate-a-third-value) or the answer is left clean
  (FP-guard). Zero author judgment in the ground-truth; every span is a verbatim substring
  and every verdict is derived from the **shipped** `_is_fail`.
- **4 natural** — organic answers produced by the `wiki-query` synthesis contract over the
  synthetic multi-source articles (no planting); ground-truth = the **consensus (intersection)
  of 2 INDEPENDENT labelers blind to the scoped prompt** (a fact-checker persona + a
  domain-reviewer persona). Both labelers returned PASS / no defects on all 4 — including a
  case where the synthesizer *naturally surfaced* a cross-source replication conflict — so the
  natural cases are **realistic-answer false-positive guards** on the multi-source path.
- **Multi-source path exercised:** 12 cases supply ≥2 `examined` sources — composition
  (39, 40, 41), cross-source conflict (42, 43, 44), the multi-source entity case (46), the
  multi-source entity-clean case (50), and all 4 natural (51–54) — the `examined[]` /
  grounding path v2 left entirely unexercised (all 32 v2 cases had exactly one source).

## Cross-source conflict (D-010-1)
An unreconciled conflict between examined sources that the answer hides is owned by
**`completeness`** (a material omission of a source fact) at `medium` → PASS under the
current FAIL rule (completeness doesn't move `_is_fail`). NOT `factual` (each value is
grounded in *a* source) and NOT `logic` (the inconsistency is across sources, not within
the answer). The `SKILL.md` sentence specifying this is a **deferred security-reviewed PR**
(KNOWN_ISSUES D-010-1); v3 ships the conflict *cases*, which here measure the unguided
prompt. Case 44 (a fabricated third value `384`) confirms the suite still **fails** a
conflict scenario when a genuine fabrication is present (`factual`/high → fail).

## Results — shipped prompt vs the four new classes

| group | n | recall | severity-match | verdict-match | false-pos | unsanctioned purity-viol |
|---|---|---|---|---|---|---|
| temporal | 4 | 1.000 | 1.000 | 1.000 | 0 | 2 |
| negation | 4 | 1.000 | 1.000 | 1.000 | 0 | 1 |
| composition | 3 | 1.000 | 0.667 | 1.000 | 0 | 1 |
| conflict | 3 | 1.000 | 1.000 | 1.000 | 0 | 1 |
| entity | 4 | 1.000 | 1.000 | 1.000 | 0 | 2 |
| **natural** | 4 | — | 1.000 | 1.000 | **0** | 0 |
| **OVERALL** | 22 | **1.000** | **0.955** | **1.000** | **0** | **7** |

(`recall` for the natural group is "—": consensus found no defects, so there is nothing to
recall; the natural cases score on false-positives + verdict, which they pass cleanly.)

**Headline:** the shipped prompt has **perfect recall (1.0), perfect verdict-match (1.0),
and ZERO false-positives** across temporal / negation / composition / conflict / entity —
and **zero FP on realistic multi-source answers** (the natural cases). The multi-source
grounding path now has standing regression coverage.

## Tracked finding — lens-purity residual on inversion defects (7 unsanctioned violations)

`unsanctioned_purity_violations = 7` (`substantive_purity_violations`: `total=7`,
`core=7`, `security_on_noninjection=0`). On 7 of the inversion-type FAIL cases (34, 37,
39, 44, 45, 46, 48) the `completeness` critic adds a "the answer omitted the true source
fact" finding alongside `factual`'s inversion finding; the grader matches the omission to
the same `defect_id` → a `factual`+`completeness` duplicate.

- **This is the SAME omission-conflation class already documented for v2** (KNOWN_ISSUES
  L-009-5 residual), now **more visible** because v3's defects are predominantly *inversions*
  — for an inversion, "the answer's claim is false" (`factual`) and "the answer omitted the
  true fact" (`completeness`) are two views of the *same* fact, so a rule-compliant
  completeness omission still overlaps the factual defect.
- **It does NOT affect the gate**: recall 1.0, verdict-match 1.0, FP 0 — purely lens-purity
  noise, not a correctness defect.
- **Not fixed here** (TASK 010 is dataset+measurement; the live prompt is untouched). It is
  the empirical "before" half for a future `completeness`-tightening / grader-attribution
  refinement, which would run the full-corpus v1+v2+v3 no-degradation A/B (PLAN
  §"Regression safety"). Recorded as KNOWN_ISSUES D-010-2.

The single severity-drift (composition, case 40) is the `logic` non-sequitur band on a
dual-finding case (factual/high still drives the correct FAIL). 1/22 → severity-match 0.955.

## Reproducibility
`grade_run(evals-v3.json, shipped-run-outputs.json) == shipped-grading.json`, pinned by
`tests/test_wiki_verify_v3.py`. v3 is a separate file; `grade.py` + the committed v1/v2
run-outputs are untouched, so the v1/v2 reproducibility pins stay byte-identical
(additive-only / non-regression).
