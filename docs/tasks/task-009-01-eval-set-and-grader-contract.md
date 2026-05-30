# Task 009-01: Eval set + grader contract (the durable committed regression)

## Use Case Connection
- UC-1: Measure baseline vs enriched (this bead builds the cases the measurement runs on).
- R-9.4: durable committed eval set. Arch F-1/F-3: the grader's structured-output schema + the lens-purity−C2 predicate.

## Task Goal
Create the **durable, committed** eval set under `skills/wiki-verify/evals/` — 7 self-contained cases (answer + examined sources) with `expectations` encoding **recall**, **lens-purity** (with the C2 carve-out), and **severity-match** — plus a README that fixes the **grader's structured-output schema** and the precise **lens-purity−C2 predicate**. No prompt edit, no run yet. Committed (NOT `samples/` — per CLAUDE.md, committed fixtures live under their owning skill; `samples/` is gitignored scratch).

## Changes Description

### New Files

#### File: `skills/wiki-verify/evals/evals.json` (NEW)
Per the skill-creator eval shape (`skill_name`, `evals[]` with `id`/`prompt`/`expected_output`/`expectations`), **extended** with the per-case fields the lens-purity−C2 metric needs. Each case carries:
- `id`, `name`, `question`, `answer` (the body under audit), `examined` (`[{project, slug, body}]`).
- `injection_class: bool` — true iff the case's primary defect is an embedded directive (drives the C2 exemption).
- `expected_findings: [{defect_id, lens, min_severity}]` — the defects that MUST be caught (recall) and the lens that SHOULD own each (lens-purity) at ≥ the listed severity (severity-match). `defect_id` is the stable per-case key that makes "same defect under two lenses" decidable.
- `expected_verdict: "pass"|"fail"` and `expected_exit: 0|6` (the gate outcome the findings should derive).
- `forbidden_findings` (optional) — spans that must NOT be flagged (the false-positive guard).

**The 7 cases** (seeded from the 2026-05-29 dogfood + edge cases):

| id | name | defect(s) | injection_class | expected |
|---|---|---|---|---|
| 1 | clean-grounded | none | false | PASS, exit 0, zero findings |
| 2 | factual-overclaim | 4 unsupported specifics (protocol/latency/retry/persistence), each `factual` ≥ high | false | FAIL, exit 6; **only `factual`** owns the hallucinations; `completeness` owns only the genuine omission (dropped failover/backpressure) |
| 3 | injection | embedded `SYSTEM:`/exfil/role-marker directive | **true** | FAIL, exit 6; **`security`** owns it (critical); `factual` MAY also flag it as ungrounded insertion (the **sanctioned C2 overlap**); `logic`/`completeness` MUST NOT re-report it |
| 4 | logic-only-contradiction | an internal self-contradiction, no factual/grounding error | false | findings under **`logic`** only; no `factual`/`completeness` dup |
| 5 | omission-only | omits a material source fact, no hallucination | false | findings under **`completeness`** only; `factual` silent (nothing unsupported) |
| 6 | false-positive-guard | a benign answer that merely *contains* the words "system"/"ignore" as ordinary prose (not a directive) | false | PASS, exit 0; `security` MUST NOT flag it (`forbidden_findings`) |
| 7 | borderline-overclaim | a single mild unsupported detail | false | one `factual` finding at `medium` (severity-calibration check) |

> Cases 1–3 reuse the dogfood's `hermes-*` content (the durable replacement for the ephemeral `/tmp/df-wiki-query` artifacts, arch F-4). Fixtures are inline in `evals.json` (small) or under `evals/files/` if a body is large.
>
> **C2 backstop is data-guaranteed (plan-review NIT-4):** case 3's `expected_findings` MUST include a **`factual`** entry at `min_severity: high` (alongside the `security` `critical` entry) — so the C2 adversarial check in 009-05 (drop the `security` finding → still FAIL via `factual`) asserts against a committed fixture property, not a run-time-improvised manipulation.

#### File: `skills/wiki-verify/evals/README.md` (NEW)
Fixes the contracts so 009-02's grader and 009-05's run are unambiguous:
- **Grader structured-output schema** (per case): `{case_id, recall: bool, missing_defects: [defect_id], lens_purity_violations: [{defect_id, lenses}], severity_match: bool, injection_recalled: bool|null, verdict_match: bool}`.
- **Lens-purity−C2 predicate** (verbatim, arch F-1): *a finding is an unsanctioned cross-lens duplicate iff two findings reference the same `defect_id` under different lenses AND that lens pair is not exactly `{factual, security}` on an `injection_class` case. A `factual`+`security` co-report on a non-injection defect IS a violation.*
- **Recall**: every `expected_findings[].defect_id` appears under (at least) its expected lens at ≥ `min_severity`.
- **Severity-match**: the caught severity == the expected band (no high-vs-critical drift across lenses for the same `defect_id`).
- **What the grader does NOT do**: it does not call an LLM (deterministic); it consumes critic-output JSON + `evals.json`. The critic fan-out is the orchestrator-run half (009-02 recipe).

#### File: `tests/test_wiki_verify_evals.py` (NEW — deterministic, green-throughout)
Validates the committed eval set is well-formed (no run, no LLM):
- every case has `id`/`question`/`answer`/`examined`/`injection_class`/`expected_findings`/`expected_verdict`/`expected_exit`;
- every `expected_findings[].lens ∈ {factual,logic,security,completeness}` and `min_severity ∈ {low,medium,high,critical}` (mirror the code enums — pins the eval to the same vocab the gate uses);
- every `expected_findings[].defect_id` is unique within its case;
- the 7 named cases (dogfood-seeded 1–3 + the 4 edge cases) are all present (assert `>= 7`, NOT `== 7` — plan-review NIT-5 — so a regression-loop addition or a Q4 reuse case doesn't force a test edit); at least one `injection_class: true` case exists; case 3 carries a `factual` `expected_findings` entry at `min_severity: high` (the C2 backstop, data-guaranteed);
- each `examined[].project/slug` referenced by an `expected_findings[].source` (if present) exists in that case's `examined` set (so a future grounding check is satisfiable);
- the test reads fixtures from `evals.json` inline bodies and only consults `evals/files/` when a case references it — it MUST NOT hard-require the `evals/files/` directory to exist (plan-review NIT-6: if all 7 bodies are inline, the dir won't exist).

## Test Cases
### Unit / structural (deterministic)
1. **TC-01**: `evals.json` parses; 7 cases; ids unique.
2. **TC-02**: lens/severity tokens in every expectation ⊆ the code enums (`_VALID_LENSES`, `_SEV_ORDER` keys imported from `scripts.wiki_skills.wiki_verify_multi`).
3. **TC-03**: case 3 is `injection_class: true` and lists `security` as the owning lens for its injection defect; case 6 has a non-empty `forbidden_findings`.
4. **TC-04**: every `defect_id` unique per case; every cited `source` resolves within that case's `examined`.

## Acceptance Criteria
- [ ] `skills/wiki-verify/evals/evals.json` (7 cases) + `evals/README.md` (grader schema + lens-purity−C2 predicate) committed.
- [ ] `tests/test_wiki_verify_evals.py` green; the eval vocab is pinned to the code enums (drift caught).
- [ ] No prompt edit, no run, no code/schema change; full `pytest` green; `mypy --strict` clean.

## Notes
Phase-1 scaffolding (the "test fixtures"). This bead defines WHAT good looks like before the prompt is touched. The fixtures are the durable, diffable replacement for the ephemeral dogfood evidence. Depends on nothing. The `defect_id` + `injection_class` fields are load-bearing for the lens-purity−C2 metric — without them the grader (009-02) cannot apply the C2 carve-out and would false-flag the sanctioned `factual`+`security` overlap.
