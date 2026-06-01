# TASK 011 — `wiki-verify` eval-v4 (deep multi-hop extension)

### 0. Meta Information (MANDATORY)
- **Task ID:** 011
- **Slug:** `wiki-verify-eval-v4`
- **Context:** Coverage follow-on to the R-9 eval harness (TASK 009) and its v3 extension
  (TASK 010). **R-8/R-9 stay DONE** — not a new ROADMAP epic. Addresses **front 2a** from
  the external v3 audit (which rated the suite 9.7/10): deep multi-hop reasoning.
- **Motivation (evidence-based):** v3's max chain is **3 `examined` sources** (one natural
  case, `nat-globex-portfolio`); every other multi-document case is a **2-hop join**. No case
  exercises a **4–5-source dependency chain**, and none tests the signature deep-multihop
  failure — an answer whose **endpoints are correct but a middle link is fabricated**, making
  the conclusion unsupported. A verifier that only checks the endpoints would wrongly PASS
  such an answer; that blind spot is currently **unmeasured**.
- **Security classification:** the **dataset + test are NOT security-sensitive** — v4 does
  **not** touch the live prompt (`skills/wiki-verify/SKILL.md`) or `grade.py`. Eval bodies are
  untrusted data fenced by the runner (H-6). Any prompt fix triggered by the measurement is a
  separate SECURITY-labeled PR (out of scope).

---

### 1. General Description

Add `skills/wiki-verify/evals/evals-v4.json` — a **self-contained** deep-multi-hop benchmark
of ~13 cases over **3 dependency chains of 4–5 synthetic source articles each** (one link per
source), in 3 new fictional domains. Exercise the previously-untested **4–5-hop traversal**
path and the **broken-middle-hop** failure class. Stand up `tests/test_wiki_verify_v4.py`
(well-formedness + 2 deep-chain invariants + reproducibility pin, mirroring
`test_wiki_verify_v3.py`), record an orchestrator-run measurement of the **shipped** prompt
under `reports/v4/`, and document it in `benchmark-v4.md` with the headline **broken-middle-hop
recall**.

**Goal of development.** After this task:
- the deep-chain (≥4 source) traversal path is **exercised**;
- the shipped prompt's ability to **catch a fabricated middle link** (vs only checking the
  endpoints) is **measured** — surfacing any endpoint-bias as a tracked finding;
- the new set is **regression-locked**, and the v1/v2/v3 pins stay **byte-identical**.

**Connection with the existing system.** Fixtures + test + recorded measurement. `grade.py`
is **source-blind** (zero `examined[]` references) → **zero grader change**; deep chains are
free for the deterministic scorer. The shipped prompt, verdict contract, schema
(`user_version` 5), and FAIL rule are **unchanged**. v4 is a **separate file** → v1/v2/v3
reproducibility pins cannot move.

---

### 2. Requirements Traceability Matrix (RTM)

> IDs are TASK-011-local (`11.x`). R-8/R-9 unaffected.

| ID | Requirement | MVP? | Sub-features |
|---|---|---|---|
| **11.1** | **Deep chains (4–5 sources)** | ✅ | (a) 3 chains, each ≥4 `examined` sources forming an unambiguous dependency chain (uniqueness clauses keep ground-truth objective); (b) 3 new fictional domains (ip-provenance, estuary-ecology, build-dependency); (c) self-contained inline bodies, plain ASCII |
| **11.2** | **Clean-traversal PASS + FP-guards** | ✅ | (a) 1 clean correct traversal per chain → empty `expected_findings`, verdict pass; (b) `forbidden_findings` on the most flaggable correct hops + the final composed conclusion (guard against "panic on a long chain") |
| **11.3** | **Broken-middle-hop (signature)** | ✅ | (a) ≥4 FAIL cases: correct endpoints, ONE fabricated MIDDLE link **absent from every source** → conclusion unsupported; (b) break **different positions** (hop2/hop3/hop4) across chains; (c) `factual`/high → fail/exit 6; span = the answer's fabricated-link sentence |
| **11.4** | **Wrong-terminus + unsupported-leap** | ✅ | (a) ≥2 wrong-terminus FAIL (a broken hop → wrong final entity / fabricated CVE id); (b) ≥1 unsupported-leap FAIL (answer asserts A↔E directly, skipping the middle); all `factual`/high → fail |
| **11.5** | **Natural deep-traversal cases** | ✅ | (a) ~3 `construction:"natural"` cases: organic `wiki-query` traversal over a chain; (b) ground-truth = consensus of 2 blind labelers (v3 methodology); PASS if correct (realistic-answer FP-guards on the deep-chain path) |
| **11.6** | **Well-formedness + reproducibility test** | ✅ | (a) `tests/test_wiki_verify_v4.py` mirrors v3 (count/domains/ids/construction; per-case span⊂answer+bodies, unique `(defect_id,lens)`, `_is_fail(expected)==verdict`, exit codes; vocab pinned to the gate); (b) **2 new invariants**: `test_v4_exercises_deep_chains` (≥5 cases with `len(examined)≥4`) + `test_v4_has_broken_middle_hop_group` (≥4 `*broken-middle*` FAIL cases, each one `factual`/high); (c) reproducibility pin `grade_run(cases, committed-run)==committed-grading` |
| **11.7** | **Recorded measurement (headline: broken-middle recall)** | ✅ | (a) orchestrator-run 4 critics over all cases via `workflows/wiki-verify-eval.md` (critics blind to `expected_findings`, H-6-fenced; `4×N≈52` sub-agents); (b) `reports/v4/` = run-outputs + grading (CI pin) + `benchmark-v4.md` per-group rollup; (c) headline = **broken-middle-hop recall** isolated from wrong-terminus recall (endpoint-bias diagnostic); misses are tracked findings, not fixed here |
| **11.8** | **Invariants preserved (regression)** | ✅ | (a) v4 separate file; `grade.py` + committed v1/v2/v3 run-outputs untouched → v1/v2/v3 pins **byte-identical**; (b) **no code/schema/prompt change** (`user_version` 5; no `import anthropic`); (c) full `pytest tests/` green (≥715 + v4) and `mypy --strict scripts/` unaffected; (d) any endpoint-bias fix is a **deferred** SECURITY PR gated by a full-corpus v1+v2+v3+v4 no-degradation A/B |

---

### 3. List of Use Cases

#### UC-1 — Measure broken-middle-hop recall of the shipped prompt (NEW)
- **Actors:** orchestrator; 4-critic fan-out; deterministic grader.
- **Main Scenario:** load the deep-chain cases → fan out 4 critics/case (blind, H-6-fenced) →
  `grade_run` → record `reports/v4/`; compute broken-middle recall vs wrong-terminus recall.
- **Outcome:** a reviewable endpoint-bias diagnostic; misses tracked, not fixed.

#### UC-2 — Exercise the ≥4-source traversal path (NEW)
- **Main Scenario:** a chain case supplies 4–5 `examined` sources; critics must verify each hop.
- **Outcome:** the deep-chain audit path gains standing regression coverage.

---

### 4. Non-Goals / Out of Scope
- Any prompt fix triggered by measured endpoint-bias (separate SECURITY PR + full-corpus A/B).
- Front 2b (source-reliability conflict — needs a source-authority model + contract change).
- A v3+v4 merged file; merge of this branch to `main` (separate user-confirmed step).
