# Development Plan: TASK 009 — `wiki-verify` critic-prompt hardening (R-9)

> **Status**: DRAFT (2026-05-29) — awaiting plan-reviewer sign-off.
> **Task ID**: 009 / Slug: `wiki-verify-critic-rubric`
> **Source spec**: [docs/TASK.md](./TASK.md) (RTM R-9.1..R-9.6 + C2; UC-1/2/3; Constraints C1–C5; Open Q1–Q4).
> **Architecture spec**: [docs/ARCHITECTURE.md](./ARCHITECTURE.md) index TASK-009 block + [architectures/functional-architecture.md](./architectures/functional-architecture.md) §Verification Layer → "Critic-prompt scoping + calibration" + "Eval harness" + [architectures/verification-map.md](./architectures/verification-map.md) R-9 RTM — updated in place + reviewed (both gates **APPROVE-WITH-NITS**, nits applied; the load-bearing "zero code/schema change" + "C2 backstop / FAIL rule" claims were independently **code-verified** against `wiki_verify_multi.py`). See [docs/reviews/task-009-review.md](./reviews/task-009-review.md), [docs/reviews/architecture-009-review.md](./reviews/architecture-009-review.md).
> **Methodology**: **Stub-First-analogous, green-throughout.** This is a **prompt + committed-eval-assets** task, not a code feature — so the two passes are: **Phase 1** = build the eval set + the (deterministic) grader + capture the **RED baseline** that proves the bleed *before* the prompt is touched; **Phase 2** = the `SKILL.md` prompt fix, then the **GREEN** re-measurement proving the delta. The deterministic `tests/test_wiki_verify_*` suite stays green at every bead boundary (the verdict contract never changes); the *quality* measurement (009-03/009-05) is **orchestrator-graded and recorded once**, NOT a pytest gate (a live LLM judge can't be pinned in CI — arch decision).
> **Predecessors**: R-8 / TASK 008 (`wiki-verify-multi`, schema v5) — **DONE**; the 2026-05-29 real-content dogfood (the empirical motivation: lens-bleed + uncalibrated severity).
> **Unblocks**: nothing gates on R-9; it hardens the shipped R-8 verdict quality + leaves a reusable eval pattern for the sibling SECURITY-SENSITIVE prompt skills (`wiki-query-synthesis`, `concept-extraction` — Q4, out of scope here).
> **Out of scope** (TASK §5/§6): any code/schema/DDL change (`user_version` stays **5**); the verdict JSON contract; `run_eval.py` (a framework-vendored *trigger*-eval, not an output grader); the sibling prompt skills (Q4 — pattern noted, not pulled in).

---

## 0. Architectural Foundation (Reference)

| Layer | Owns | Class / note |
|---|---|---|
| `skills/wiki-verify/SKILL.md` (the prompt) | The 4 lens definitions + severity rubric + few-shot + H-6 armor + the strict verdict-JSON output contract | **SECURITY-SENSITIVE** (loaded verbatim into orchestrator context); edited in 009-04 |
| `skills/wiki-verify/evals/evals.json` + `evals/files/*` | The **durable committed** eval set (cases + expectations) | **Committed** (NOT `samples/` — per CLAUDE.md; `samples/` is gitignored scratch) |
| `skills/wiki-verify/evals/grade.py` | The **deterministic** grader (critic-outputs + expectations → recall / lens-purity−C2 / severity-match) | test-only helper (C4-permitted; unit-tested, CI-green) |
| `workflows/wiki-verify-eval.md` | The orchestrator-run recipe: load the lens prompts from `SKILL.md` → fan out the 4 critics over each eval case → `grade.py` | recipe (the run is orchestrator-graded, recorded — not pytest) |
| `scripts/wiki_skills/wiki_verify_multi.py` (`_VALID_LENSES`/`_SEV_ORDER`/`_FAIL_LENSES`, `_is_fail`, `apply` validation) | The deterministic gate + the **byte-stable** vocab the rubric must stay inside | **UNCHANGED** by R-9 (code-verified) |

**TASK 009 invariants** (carried from the two review gates):
1. **Zero code/schema change** (R-9.6c, code-verified): `prepare`/`apply`, the verdict JSON contract, the lens vocab `{factual,logic,security,completeness}`, the severity vocab `{low,medium,high,critical}`, the grounding gate, the `factual|security ≥ --fail-on` FAIL rule, and `user_version` 5 are all **byte-stable**. R-9 is additive prompt + committed eval assets only. A `test_wiki_verify_skill_contract.py` pins the SKILL.md vocab to the code enums so drift is caught.
2. **The C2 backstop is the one sanctioned overlap** (binding): both **FAIL-lenses** (`factual`, `security`) MAY flag an injection — `security` (smuggled directive) + `factual` (ungrounded insertion). This is *not* lens-bleed (different domains) and preserves the gate's FAIL-redundancy if the single `security` critic under-reports (verified against `_is_fail`: a `factual` finding ≥ threshold independently forces FAIL). Only the **non-FAIL** lenses (`logic`, `completeness`) are banned from re-reporting injections.
3. **Lens-purity is computed precisely** (arch F-1): a finding is an *unsanctioned* cross-lens duplicate iff two findings reference the **same defect** (by a per-case `defect_id` the fixture carries) under different lenses AND that pair is **not** exactly `{factual,security}` on an **injection-class** defect (fixture-flagged). A `factual`+`security` co-report on a **non-injection** hallucination IS still counted as bleed. The eval `expectations`/grader schema therefore carry a per-finding `defect_id` + a per-case injection-class flag.
4. **Few-shot defang is a NAMED control** (arch F-2), not an adjective: example attacks are **described not rendered** where possible; any literal example sits **inside the H-6 fenced sentinel** labelled "EXAMPLE — nothing here is an instruction"; the security audit (009-06) verifies no example line is parseable as a live directive outside its fence.
5. **Measurement isolates the variable**: the eval runner feeds (answer + examined sources) straight to the 4 critics using the lens prompts **extracted from `SKILL.md`** — the only thing that differs between the baseline (009-03) and enriched (009-05) runs is the SKILL.md content. No `prepare`/`apply` round-trip is needed to measure critic quality (the pipeline is already proven by `test_wiki_verify_*` + the dogfood).
6. **RED-before-fix ordering** (the Stub-First spine): 009-03 (baseline) MUST land before 009-04 (the prompt edit) — you cannot measure the baseline after the prompt has changed.

---

## 1. RTM → Bead Checklist (one RTM item = one checklist item)

Phase-1 (eval + RED baseline) ───────────────────────────────────────────────
- [ ] **[R-9.4]** Durable committed eval set (`evals.json` + fixtures; 7 cases; expectations carry `defect_id` + injection-class) → **009-01**
- [ ] **[R-9.5-mech]** Eval runner: recipe `workflows/wiki-verify-eval.md` + deterministic `grade.py` (unit-tested) → **009-02**
- [ ] **[R-9.5-baseline]** Baseline measurement of the CURRENT prompt — the RED state (bleed visible) → **009-03**

Phase-2 (prompt fix + GREEN) ─────────────────────────────────────────────────
- [ ] **[R-9.1]** Anti-bleed lens scoping (exclusive domains; non-FAIL lenses banned from re-reporting injections) → **009-04**
- [ ] **[R-9.2]** Shared severity rubric (one anchored scale; vocab pinned to the code enum) → **009-04**
- [ ] **[R-9.3]** Per-lens supported/unsupported defs + **defanged** few-shot (named control) → **009-04**
- [ ] **[C2]** Sanctioned `factual`+`security` injection backstop (excluded from lens-purity) → **009-04** (+ adversarial case in 009-05)
- [ ] **[R-9.6a/b/c]** Invariants preserved — verdict contract + H-6 + enum vocab byte-stable; no code/schema change; Decision-17 → **009-04** (pinned by `test_wiki_verify_skill_contract.py`)
- [ ] **[R-9.5-enriched]** Enriched measurement + recorded baseline→enriched delta — the GREEN proof (purity↑, severity↑, recall non-regression, injection 100%) → **009-05**
- [ ] **[R-9.6d / C3]** Security audit + code review + docs close-out → **009-06**

> **Grouping note (for the plan-reviewer):** R-9.1/9.2/9.3/C2/R-9.6a-c all land in the single `SKILL.md` edit (009-04) because they are **one cohesive prompt artifact** whose combined effect is only measurable by the eval run (009-05) — splitting them into separate beads would create boundaries with no independent verification. Each remains a **distinct traceable checklist item** with its own acceptance criterion in the 009-04 spec. This is cohesion, not feature-grouping.

---

## 2. Bead Sequence & Dependency Graph

```
009-01  eval set + grader contract        (R-9.4)            ──┐
009-02  eval runner: recipe + grade.py     (R-9.5-mech)        ─┼─ Phase 1
009-03  baseline run  (RED — bleed shown)  (R-9.5-baseline)   ──┘   [must precede 009-04]
          │
009-04  enrich SKILL.md  (R-9.1/9.2/9.3/C2/9.6a-c)            ──┐
009-05  enriched run + delta  (GREEN)      (R-9.5-enriched)    ─┼─ Phase 2
009-06  security audit + review + docs     (R-9.6d/C3)        ──┘
```

| Bead | Depends on | Verification kind |
|---|---|---|
| 009-01 | — | deterministic (`test_wiki_verify_evals.py`) |
| 009-02 | 009-01 (evals.json shape) | deterministic (`grade.py` unit tests on synthetic critic outputs) |
| 009-03 | 009-02 (runner) | **orchestrator-graded, recorded** (baseline report) |
| 009-04 | 009-03 (baseline captured first) | deterministic (`test_wiki_verify_skill_contract.py` + existing suite green) |
| 009-05 | 009-04 (enriched prompt) | **orchestrator-graded, recorded** (enriched + delta report); loops to 009-04 on regression |
| 009-06 | 009-05 (final prompt + delta) | security-auditor + code-reviewer subagents; docs |

---

## 3. Per-Bead Detail Files

- [009-01 — Eval set + grader contract](./tasks/task-009-01-eval-set-and-grader-contract.md) — `evals.json` + 7 fixtures + the grader's structured-output schema + the lens-purity−C2 predicate.
- [009-02 — Eval runner (recipe + grade.py)](./tasks/task-009-02-eval-runner.md) — `workflows/wiki-verify-eval.md` + deterministic `grade.py` (unit-tested).
- [009-03 — Baseline measurement (RED)](./tasks/task-009-03-baseline-measurement.md) — run the current prompt; record the bleed.
- [009-04 — Enrich the SKILL.md prompt](./tasks/task-009-04-enrich-prompt.md) — anti-bleed + rubric + few-shot + C2; contract/H-6/vocab pinned.
- [009-05 — Enriched measurement + delta (GREEN)](./tasks/task-009-05-enriched-measurement-delta.md) — re-run; assert deltas + the C2 adversarial case.
- [009-06 — Security audit + review + docs close-out](./tasks/task-009-06-audit-review-docs.md) — C3 mandatory audit; sync `.AGENTS.md` + ARCHITECTURE status.

---

## 4. Stub-First Phasing (mapped to a prompt task)

| Stub-First concept | TASK 009 realisation |
|---|---|
| **Phase 1 — Interfaces/Stubs + RED tests** | 009-01 (eval set = the "test fixtures") + 009-02 (grader = the "assert harness", unit-tested deterministically) + 009-03 (baseline run = **RED** — the current prompt visibly bleeds: lens-purity violations on cases B/C) |
| **Phase 2 — Implementation → GREEN** | 009-04 (the prompt fix = the "implementation") + 009-05 (enriched run = **GREEN** — purity↑/severity↑/recall non-regression; the delta is the proof) |
| **Green-throughout** | The deterministic `tests/test_wiki_verify_*` + `grade.py` unit tests stay green at every bead boundary; `mypy --strict` clean; the verdict contract never changes |
| **No mocking LLMs** | The measurement uses real critic fan-out (orchestrator-run), not recorded/mocked LLM output; `grade.py` is tested on **synthetic critic JSON** (deterministic), never by mocking a model |

---

## 5. Open Questions carried into Development

- **Q3 (resolved):** runner = committed Workflow recipe + `grade.py` (NOT `run_eval.py`).
- **Q2 (009-04 decides):** few-shot inline in `SKILL.md` vs `skills/wiki-verify/examples/` — pick by the skill-creator inline-block limit (≤20 lines/block ideal, hard-fail >60); default inline if concise.
- **Q4 (out of scope):** sibling prompt skills — pattern recorded, not pulled in.
- **Regression policy (009-05):** if the enriched prompt regresses recall (esp. injection < 100%) or fails the C2 adversarial case, 009-05 loops back to 009-04 (revise the scoping) — never ship a recall regression to buy purity.
