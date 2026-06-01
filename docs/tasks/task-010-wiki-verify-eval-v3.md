# TASK 010 — `wiki-verify` eval-v3 (adversarial reasoning extension)

### 0. Meta Information (MANDATORY)
- **Task ID:** 010
- **Slug:** `wiki-verify-eval-v3`
- **Context:** Coverage follow-on to the **R-9** durable eval harness (TASK 009).
  **R-8 / R-9 stay DONE** — this is *not* a new ROADMAP epic. It widens the committed
  `wiki-verify` benchmark from "single-sentence, single-source" defects to four
  adversarial reasoning classes the suite never exercises.
- **Motivation (evidence-based):** an external audit of `evals-v2.json` (32 cases,
  ~9.3/10) confirmed against the data that **every** v2 case has exactly **one**
  `examined` source and the defect taxonomy is number-mutation / fabrication /
  injection / omission / logic / borderline / fp-guard — with **no temporal, no
  polarity-flip, no entity-swap, no cross-source** case. Yet `wiki-verify`'s whole
  design (the `examined[]` array, the `FINDING_SOURCE_NOT_EXAMINED` grounding gate,
  cite-by-`project/slug`) is built for **multi-source** audit, so that path is
  measured by **zero** cases. The verifier could be silently broken on cross-source
  or temporal/negation reasoning and the green dashboard would not know.
- **Security classification:** the **dataset + test** are NOT security-sensitive —
  v3 does **not** touch the live prompt (`skills/wiki-verify/SKILL.md`). The deferred
  cross-source-conflict lens rule (which DOES touch `SKILL.md`) is **out of scope**
  for TASK 010 and ships as its own code-review + security-audit PR. The eval
  `answer`/`examined` bodies (incl. any injection strings) remain **untrusted data**
  fenced by the runner (H-6).

---

### 1. General Description

Add `skills/wiki-verify/evals/evals-v3.json` — a **self-contained extension** benchmark
of **22 cases** (18 seeded + 4 natural multi-document) across **6 new fictional
domains**, exercising four defect classes v2 omits: **temporal**, **negation /
polarity-flip**, **multi-document** (composition + cross-source conflict), and
**entity-confusion**. Stand up `tests/test_wiki_verify_v3.py` (well-formedness +
reproducibility pin, mirroring `test_wiki_verify_v2.py`), record an orchestrator-run
measurement of the **shipped** prompt's coverage of the new classes under
`reports/v3/`, and document it in `benchmark-v3.md`.

**Goal of development.** After this task:
- the multi-source audit path is **exercised** (≥2 `examined` sources per multi-doc case);
- temporal / negation / entity-confusion / composition defects are **measured** against
  the shipped prompt, surfacing any coverage miss as **data** (a tracked finding), not
  assumption;
- the new set is **regression-locked** by a deterministic well-formedness + reproducibility
  test, and the v1/v2 pins stay **byte-identical** (additive-only).

**Connection with the existing system.** This is a **fixtures + test + recorded
measurement** change. The deterministic grader (`skills/wiki-verify/evals/grade.py`)
is **source-blind** (never reads `examined[]`) → **zero grader change**; multi-source
is structurally free. The shipped prompt, the verdict contract, the schema
(`user_version` 5), and the FAIL rule are **unchanged**. v3 is a **separate file**, so
the committed v1/v2 reproducibility pins cannot move.

---

### 2. Requirements Traceability Matrix (RTM)

> Requirement IDs are TASK-010-local (`10.x`). Not new ROADMAP epics — R-8/R-9 unaffected.

| ID | Requirement | MVP? | Sub-features |
|---|---|---|---|
| **10.1** | **Temporal group** — time-bounded source fact vs present/permanent claim | ✅ | (a) ≥2 seeded fail cases (drop-the-bound + tense-shift), `factual`/`high`→fail; (b) ≥1 borderline PASS (bound correctly preserved) with a `factual` FP-guard; (c) new domains, none reused from v2 |
| **10.2** | **Negation group** — single polarity-word flip (cannot→can, prohibited→permitted) | ✅ | (a) ≥2 seeded fail cases, `factual`/`high`→fail; (b) ≥1 PASS (polarity preserved) with FP-guard; (c) spans scoped tightly to the polarity clause so `_overlap` matches only the intended clause |
| **10.3** | **Multi-document group** — ≥2 `examined` sources | ✅ | (a) **composition**: faithful answer joins A+B, defective mis-joins → `factual`/`high` (+ optional `logic` non-sequitur as a DISTINCT `defect_id`); (b) clean multi-source PASS (correct composition → no finding) proving N-source grounding doesn't spuriously fire; (c) **cross-source conflict** cases: A≠B, answer hides it → `completeness`/`medium` (PASS under the current gate; see the fork decision) + a conflict-surfaced PASS + a fabricated-third fail bridge |
| **10.4** | **Entity-confusion group** — ≥2 named entities, fact mis-attributed | ✅ | (a) single-source two-entity fail (number swapped between entities), `factual`/`high`→fail; (b) multi-source variant (entity A in source A, B's fact pinned to A); (c) clean PASS counterpart with FP-guard |
| **10.5** | **Natural multi-doc cases** — organic, consensus-labeled | ✅ | (a) ~4 `construction:"natural"` cases over the synthetic multi-source articles; (b) organic answers from `wiki-query`; (c) ground-truth = **consensus of 2 independent labelers blind to the scoped prompt** (v2 methodology), encoded in `expected_findings`/`expected_verdict`; `defect_id` = `nat-NNN-<lens>`; (d) satisfy the same well-formedness invariants as seeded |
| **10.6** | **Well-formedness + reproducibility test** | ✅ | (a) `tests/test_wiki_verify_v3.py` mirrors v2: `len==22`, domain count, ids unique, `construction ∈ {seeded,natural}`; (b) per-case invariants for BOTH constructions (lens/severity vocab; `span ⊂ answer + bodies`; unique `(defect_id,lens)`; `_is_fail([{lens,min_severity}…],"high") == (verdict=="fail")` & `exit==6/0`); (c) reproducibility pin `grade_run(cases, committed-run)==committed-grading` |
| **10.7** | **Recorded measurement (coverage of the shipped prompt)** | ✅ | (a) orchestrator-run 4 critics over all 22 cases via `workflows/wiki-verify-eval.md`, batched (echo `4×22=88`); critics **blind** to `expected_findings`; (b) `reports/v3/` = `shipped-run-outputs.json` + `shipped-grading.json` (CI pin) + `benchmark-v3.md` (per-group rollup, seeded vs natural broken out); (c) any class the shipped prompt misses is flagged as a tracked finding (NOT silently fixed here) |
| **10.8** | **Invariants preserved (regression)** | ✅ | (a) v3 is a separate file; `grade.py` + committed v1/v2 run-outputs **untouched** → v1/v2 pins byte-identical; (b) **no code/schema/DDL change** (`user_version` 5; no `import anthropic`); (c) full `pytest tests/` green (≥709 baseline + v3) and `mypy --strict scripts/` unaffected; (d) the `SKILL.md` conflict-lens rule + any miss-driven prompt fix are **deferred** to separate gated PRs (regression-safety protocol in PLAN §"Regression safety") |

---

### 3. List of Use Cases

#### UC-1 — Measure the shipped prompt's coverage of the new defect classes (NEW)
- **Actors:** Operator / orchestrator; the 4-critic fan-out; the deterministic grader.
- **Preconditions:** `evals-v3.json` exists & well-formed; the shipped `SKILL.md` on disk.
- **Main Scenario:** load 22 cases → fan out 4 critics/case (blind to expectations,
  H-6-fenced) → `grade_run` → record `reports/v3/` per-group rollup.
- **Outcome:** a reviewable coverage report; misses are tracked findings, not fixes.

#### UC-2 — Exercise the multi-source grounding path (NEW)
- **Actors:** the 4 critics over a ≥2-source case.
- **Main Scenario:** a composition/conflict/entity case supplies ≥2 `examined` sources;
  critics audit across the set and cite by `project/slug`.
- **Outcome:** the previously-unexercised multi-source audit path now has coverage.

#### UC-3 — Regression guard for a future prompt change (DEFERRED, documented)
- **Actors:** a later prompt-change PR (conflict rule / miss-driven fix).
- **Main Scenario:** full-corpus v1+v2+v3 A/B with the no-degradation gate (PLAN
  §"Regression safety") — v2 cases guard regression, v3 cases measure improvement.
- **Outcome:** "improve new without worsening old" is enforced by the harness, not by hand.

---

### 4. Non-Goals / Out of Scope
- The `SKILL.md` cross-source-conflict lens sentence (separate security-reviewed PR).
- Any prompt fix triggered by a coverage miss (recorded as a finding; fixed later if warranted).
- A v2+v3 superset / merged canonical file.
