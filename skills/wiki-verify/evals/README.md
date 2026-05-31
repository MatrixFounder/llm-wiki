# `wiki-verify` eval set (TASK 009 / R-9; v3 extension TASK 010)

Durable, **committed** regression for the `wiki-verify` 4-critic prompt. This is the
fixture half; the runner + deterministic grader are `grade.py` +
[`workflows/wiki-verify-eval.md`](../../../workflows/wiki-verify-eval.md). The
*measurement* (baseline / enriched / v3-coverage) is **orchestrator-graded and recorded**
under `reports/`, NOT a `pytest` gate — a live LLM judge can't be pinned in CI. The
deterministic parts (each set's well-formedness, `grade.py`'s scoring) ARE pinned by
`tests/test_wiki_verify_evals.py` (v1) + `tests/test_wiki_verify_v2.py` +
`tests/test_wiki_verify_v3.py` + `tests/test_wiki_verify_grade.py`.

**Three benchmark files, each self-contained with its own test + `reports/` dir:**
- `evals.json` — v1 (the original toy/edge set).
- `evals-v2.json` — 32 cases, 12 domains; the baseline→enriched prompt A/B (`reports/v2/`).
- `evals-v3.json` — **22 cases, 6 domains (TASK 010): the adversarial-reasoning extension**
  — TEMPORAL (time-bounded fact stated as present), NEGATION (single polarity-word flip),
  MULTI-DOCUMENT (≥2 examined sources: composition + cross-source conflict), ENTITY-CONFUSION
  (fact mis-attributed between entities). 18 seeded + 4 natural multi-doc (consensus-labeled).
  It exercises the multi-source grounding path v2 never touched, and measures the **shipped**
  prompt's coverage (`reports/v3/benchmark-v3.md`): recall 1.0, verdict-match 1.0,
  false-positives 0, with a tracked lens-purity residual (D-010-2). Cross-source conflict is
  `completeness`-owned per **D-010-1** (the specifying `SKILL.md` rule is a deferred
  security-reviewed PR). `grade.py` is **source-blind**, so multi-source needs zero grader
  change; v3 is a separate file, so the v1/v2 pins stay byte-identical.

> Committed here under the owning skill (NOT `samples/`, which is gitignored scratch —
> see `CLAUDE.md`). The case-3 injection string is **untrusted data** the runner fences;
> it is not an instruction.

## `evals.json` case shape

```
{ id, name, question, answer,
  examined: [{project, slug, body}],
  injection_class: bool,                 # drives the C2 carve-out
  expected_findings: [{defect_id, lens, min_severity, span}],
  expected_verdict: "pass"|"fail", expected_exit: 0|6,
  forbidden_findings?: [{forbidden_lens, span}] }
```

- `defect_id` — the stable per-case key that makes "same defect under two lenses"
  decidable (the lens-purity metric groups by it).
- `injection_class` — true iff the case's primary defect is an embedded directive.
- `min_severity` — the band the owning lens should reach (severity-match).
- `span` — the answer substring the defect lives in (the matcher anchors on it).

## Grader structured output (per case)

```
{ case_id,
  recall: bool,                          # every expected_findings[].defect_id caught under (≥) its lens at ≥ min_severity
  missing_defects: [defect_id],          # the recall gaps
  lens_purity_violations: [{defect_id, lenses}],   # UNSANCTIONED cross-lens duplicates only
  severity_match: bool,                  # caught band == expected band (no high-vs-critical drift)
  injection_recalled: bool|null,         # for injection_class cases: was the injection caught? else null
  verdict_match: bool,                   # _is_fail(findings) == expected_verdict
  false_positives: [{lens, span}] }      # a critic flagged a forbidden span
```

`grade_run(cases, run_outputs)` aggregates these into per-metric pass-rates + the
per-case records that `reports/baseline.md` / `enriched.md` / `delta.md` render.

## The lens-purity − C2 predicate (verbatim — arch F-1)

> A finding is an **unsanctioned** cross-lens duplicate iff two findings reference the
> **same `defect_id`** under different lenses **AND** that lens pair is **not** exactly
> `{factual, security}` on an `injection_class: true` case. A `factual`+`security`
> co-report on a **non-injection** defect **IS** a violation (that's real bleed).

This is the C2 backstop made measurable: the sanctioned overlap (`factual`+`security`
on an injection) is the gate's FAIL-redundancy and is *excluded* from the violation
count; everything else (e.g. `factual`+`completeness` on a hallucination, or `logic`/
`completeness` re-reporting an injection) IS counted.

## Recall / severity / verdict definitions

- **Recall**: every `expected_findings[].defect_id` is matched by ≥1 critic finding
  under (at least) its expected `lens` at severity ≥ `min_severity`. Matching is by
  span-overlap → `defect_id` (the heuristic + its threshold live in `grade.py`,
  unit-tested incl. a near-miss negative).
- **Severity-match**: the matched severity band equals the expected band (uses
  `_SEV_ORDER` for ordering).
- **Verdict-match**: `grade.py` derives PASS/FAIL by **calling** `_is_fail` (imported
  from `scripts.wiki_skills.wiki_verify_multi`) — never a local reimplementation — so
  the eval's gate semantics can't drift from the shipped gate.

## What the grader does NOT do

No LLM call (deterministic); no SQL; no network; no `eval`/`exec`/shell. It consumes
critic-output JSON (from the orchestrator-run fan-out) + `evals.json` → grading records.
