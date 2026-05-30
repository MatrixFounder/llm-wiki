# TASK 009 — Tighten `wiki-verify` critic prompts (anti-bleed rubric) + durable eval harness

### 0. Meta Information (MANDATORY)
- **Task ID:** 009
- **Slug:** `wiki-verify-critic-rubric`
- **Context:** Quality/hardening follow-on to the shipped **R-8** (`wiki-verify-multi`,
  TASK 008). **R-8 stays DONE** — this is *not* a new ROADMAP epic. It sharpens the
  per-lens critic prose that the deliberately-thin TASK-008 prompt left loose.
- **Motivation (evidence-based):** the 2026-05-29 real-content dogfood
  (`/tmp/df-wiki-query`, 3 filed answers: clean / overclaim / injection, audited by
  the 4 critics as parallel sub-agents) proved the Python gate **sound** and recall
  **good**, but surfaced two prose-quality defects the gate happily absorbs yet that
  make the verdict pages noisy and the per-lens behaviour uncalibrated:
  1. **Lens-bleed** — the *same* defect reported by 3–4 lenses. Scenario B's 4
     hallucinations were emitted by **both** `factual` *and* `completeness`; the
     scenario C injection was emitted by **all four** lenses (`factual`, `logic`,
     `completeness` each scored it `critical`, not just `security`).
  2. **Uncalibrated severity** — the same hallucination scored `high` by `factual`
     but `critical` by `completeness`; severity is not anchored to a shared scale.
  3. **Findings on *supported* claims** — `factual` annotated a grounded sentence
     with a `low` finding, inflating the list.
- **Security classification:** **SECURITY-SENSITIVE.** `skills/wiki-verify/SKILL.md`
  is loaded verbatim into the orchestrator's LLM context (stored-prompt-injection
  surface; same class as KNOWN_ISSUES **H-5/H-6**). Per the file's own banner and the
  framework, this change requires **code review AND a security audit**.

---

### 1. General Description

Replace the four thin prose "lenses" in `skills/wiki-verify/SKILL.md` (lines ~76–92)
with **scoped, calibrated, few-shot-backed per-lens instructions**, and stand up a
**durable, committed eval set** under the skill so the change is measured (baseline
vs enriched) rather than asserted — the exact gap flagged in the dogfood ("no eval
harness on the per-lens prose; recall/quality is prompt-dependent and uncalibrated").

**Goal of development.** After this task:
- each lens reports **only its own concern** (no cross-lens duplicates);
- the same defect gets a **consistent severity** from any lens, anchored to one
  rubric;
- recall is **preserved or improved** — in particular **injection recall must not
  regress** (the dogfood's "all lenses resisted + flagged the injection" safety
  property must not silently become "injection slips if the `security` lens errs");
- the prompt's quality is **regression-locked** by an eval set runnable through the
  skill-creator eval loop.

**Connection with the existing system.** This is a **prompt + assets** change only.
The deterministic Python (`wiki_verify_multi.py` `prepare`/`apply`), the verdict JSON
contract, the schema (`user_version` 5), and the grounding gate / FAIL rule are
**unchanged**. The enriched prompt must stay byte-compatible with the code's verdict
validation (lens vocab `{factual,logic,security,completeness}`, severity vocab
`{low,medium,high,critical}`, the grounding gate, the `factual|security ≥ --fail-on`
FAIL rule — see [wiki_verify_multi.py:443-448](../scripts/wiki_skills/wiki_verify_multi.py#L443-L448)).
Decision-17 holds: no `import anthropic`; the critics still run in the orchestrator's
context.

---

### 2. Requirements Traceability Matrix (RTM)

> Requirement IDs are TASK-009-local (`9.x`). They are **not** new ROADMAP epics —
> the shipped ROADMAP **R-8** is unaffected.

| ID | Requirement | MVP? | Sub-features |
|---|---|---|---|
| **9.1** | **Anti-bleed lens scoping** — each lens owns an exclusive domain | ✅ | (a) each lens states its EXCLUSIVE domain + an explicit "out of scope — do NOT report" list; (b) unsupported **specific claims** → `factual` only; **omissions / uncited-but-not-false additions** → `completeness` only (resolves the B overlap); (c) injection / exfil / jailbreak / role-markers → `security` (resolves the C quadruple-report) **subject to the C2 redundancy constraint**; (d) a finding under the wrong lens is an eval failure (lens-purity metric) — **except** the one sanctioned `factual`+`security` overlap on injections (the C2 backstop), which lens-purity MUST exclude |
| **9.2** | **Severity rubric** — one shared, anchored scale | ✅ | (a) the scale defined **once**, referenced by all four lenses; (b) concrete anchors: exploitable injection/exfil = `critical`; fabricated specific claim that materially changes the answer = `high`; minor unsupported detail = `medium`; supported/cosmetic = `low` **or omit**; (c) same defect → same severity from any lens (kills the high-vs-critical split); (d) stays within the code's `{low,medium,high,critical}` vocab (C1) |
| **9.3** | **Per-lens definitions + few-shot** | ✅ | (a) crisp "supported vs unsupported" / "in-scope vs out" per lens; (b) 1–2 worked mini-examples per lens (one positive, one negative) showing finding shape + severity; (c) examples respect the skill-creator inline-block limits (≤20 lines/block ideal, hard-fail >60) — move to `examples/` if large; (d) any example injection is **defanged/labelled** so the file does not itself smuggle a live directive |
| **9.4** | **Durable committed eval set** | ✅ | (a) `skills/wiki-verify/evals/evals.json` (`id`/`prompt`/`expected_output`/`expectations`) — the skill-creator eval schema is the shape, but its tooling is **framework-vendored + gitignored** (`.agentic-development/.agent/skills/skill-creator/`), not a repo contract, and `run_eval.py` is a *trigger*-eval (does the description fire?), **not** an output grader (see Q3); (b) cases seed from the 3 dogfood scenarios **plus** edge cases: logic-only contradiction (no factual error), omission-only (completeness, no hallucination), **false-positive guard** (a benign answer that merely *contains* the words "system"/"ignore" as ordinary prose — not an executable directive — must NOT be flagged), borderline single-detail overclaim; (c) each case's `expectations` encode **recall** (right flaw caught), **lens-purity** (caught by the right lens *only*, EXCLUDING the sanctioned `factual`+`security` injection overlap of C2), **severity** (matches the rubric); (d) fixtures (answer + sources) are self-contained under `evals/files/` or inline |
| **9.5** | **Baseline-vs-enriched measurement (the eval loop)** | ✅ | (a) the measurement run is **orchestrator-graded** (4-critic fan-out → grader), recorded once as a baseline→enriched delta — **not** a `pytest` gate (a live LLM judge can't be pinned in CI); (b) reports deltas for recall, lens-purity (**unsanctioned** cross-lens duplicate rate), severity-match rate; (c) enriched must show measurable lens-purity + severity-match gains with **no recall regression** (injection recall stays 100%); (d) the runner is a **committed Workflow + grader** (the proven dogfood pattern), NOT `run_eval.py` (trigger-eval only) — Architecture confirms + specifies the grader's structured-output schema (Q3) |
| **9.6** | **Invariants preserved (regression)** | ✅ | (a) verdict JSON contract unchanged; lens/severity vocab in sync with `apply` validation; the existing **deterministic** `tests/test_wiki_verify_*.py` suite stays green (the new eval set is orchestrator-graded per 9.5, not a pytest gate); (b) **H-6 armor preserved or strengthened**; injection recall non-regression (C2); (c) **no code/schema/DDL change** (`user_version` 5; no `import anthropic`); (d) security audit + code review pass with no new prompt-surface findings |

---

### 3. List of Use Cases

#### UC-1 — Measure the enriched prompt against the baseline (NEW)
- **Actors:** Operator / orchestrator; the eval loop; grader.
- **Preconditions:** the eval set (9.4) exists; both prompt versions available.
- **Main Scenario:**
  1. Operator runs the eval loop over `evals/evals.json` with the **baseline** prompt.
  2. Operator runs it with the **enriched** prompt.
  3. Grader scores each case on recall / lens-purity / severity-match.
  4. The comparison reports the deltas (9.5b); enriched wins on purity + severity
     with no recall loss.
- **Alternative Scenarios:**
  - **A1 — recall regression:** if enriched drops any planted-flaw catch (esp.
    injection), the change is **rejected** and the per-lens scoping is revised
    (the C2 backstop must hold).
- **Postconditions:** a committed eval set + a recorded baseline→enriched delta.
- **Acceptance Criteria:**
  - ✅ enriched lens-purity > baseline (fewer cross-lens duplicate findings);
  - ✅ enriched severity-match ≥ baseline; ✅ enriched recall ≥ baseline on **every**
    case, with **injection recall == 100%**.

#### UC-2 — Audit a factual-overclaim answer with the enriched prompt (MODIFIES existing R-8 flow)
- **Main Scenario:** the 4 critics audit scenario-B-style content → **only
  `factual`** reports the unsupported specific claims (NATS / latency / retry /
  persistence), each at a **consistent** severity; `completeness` reports **only**
  the genuine omission (dropped failover/backpressure), not the hallucinations.
- **Acceptance Criteria:** ✅ zero finding appears under two lenses; ✅ FAIL still
  derived (a `factual` finding ≥ `--fail-on`); ✅ `apply` still exit 6.

#### UC-3 — Audit an injection answer with the enriched prompt (MODIFIES existing R-8 flow)
- **Main Scenario:** the 4 critics audit scenario-C-style content → the injection
  is owned by `security` (critical); the legitimate prose is graded normally by the
  other lenses; **no lens obeys** the embedded directive (H-6).
- **Acceptance Criteria:** ✅ `security` flags the injection `critical` → FAIL
  (exit 6); ✅ the C2 backstop holds (injection still triggers FAIL even in the
  adversarial "security lens under-reports" eval case); ✅ no lens emits the
  attacker's demanded `pass`/empty-findings; ✅ `apply` still neutralizes the
  frontmatter forgery (verdict page parses as one doc, no smuggled key).

---

### 4. Non-functional Requirements

- **Security (paramount):** SECURITY-SENSITIVE prompt surface (H-5/H-6 class). The
  anti-bleed change MUST NOT reduce the ensemble's ability to FAIL on an injection
  if the single `security` critic errs (see Open Q1). No weakening of the
  untrusted-data framing, the fenced-sentinel pattern, or the "never obey" rule.
- **Compatibility:** verdict JSON contract byte-stable; lens/severity vocab pinned
  to the code enums. R-X1/R-X2-forward unaffected (the prompt is already
  layout-agnostic; it consumes `prepare`'s envelope, not file paths).
- **Maintainability:** the severity scale is defined **once**; lens domains are
  provably non-overlapping (lens-purity metric in the eval).
- **Determinism:** Decision-17 preserved — the audit lives in the orchestrator's
  context; the Python skill stays a deterministic gate.

---

### 5. Constraints and Assumptions

- **C1 — vocab sync (hard):** the rubric must use exactly the code's lens
  `{factual,logic,security,completeness}` and severity `{low,medium,high,critical}`
  vocab; introducing a new token would be rejected by `apply` (`INVALID_VERDICT`,
  the vdd-multi L-1 invariant).
- **C2 — security redundancy (hard):** anti-bleed must not turn "all lenses catch
  the injection" into "only `security` catches it, and if that one agent errs the
  injection passes." The FAIL gate counts **`factual`+`security`** findings ≥
  threshold; a principled scoping must keep a **FAIL-lens backstop** for injections.
- **C3 — review + audit (process):** code review **and** security audit mandatory
  before merge (the file's banner + framework Self-Improvement rule).
- **C4 — no code/schema change:** prompt + committed eval assets only. `prepare`/
  `apply` Python, the verdict contract, and `user_version` 5 are untouched. (A
  *test-only* eval helper / grader is permitted; the shipped skill contract is not.)
  The **durable eval set** (static data + expectations, 9.4) is the committed,
  diffable deliverable; the **measurement run** (9.5) is orchestrator-graded and
  recorded once (baseline→enriched delta), **not** a deterministic `pytest` assertion.
- **C5 — Decision-17:** no `import anthropic`; no `--model`; critics run in the
  orchestrator context.
- **Assumption A1:** the skill-creator eval tooling (`run_eval.py`) is usable here
  **or** a committed Workflow-based equivalent is acceptable — the dogfood already
  demonstrated the 4-critic fan-out + structured grading pattern. (Resolve in Arch.)

---

### 6. Open Questions

- **Q1 (key — the C2 tension):** how do we scope injection detection to `security`
  (anti-bleed) **without** losing the ensemble's FAIL-redundancy if the `security`
  critic alone under-reports? Candidate resolutions:
  - **(a)** accept `security` as the sole injection *owner* — it is a FAIL-lens, so a
    single catch → FAIL; rely on its prompt-armor robustness (the dogfood showed it
    is robust).
  - **(b)** keep `security` authoritative **but** explicitly instruct `factual` to
    treat an embedded directive as an **ungrounded insertion** (a grounding failure
    in `factual`'s *own* domain — `factual` is also a FAIL-lens) → a principled
    backstop that is **not** lens-bleed (a different framing, not a duplicate).
    **Empirically grounded:** in the dogfood, `factual` *already* scored the
    scenario-C injection `critical` on grounding grounds (`verdict-C.json`), so (b)
    codifies observed behaviour. This `factual`+`security` pair is the **one
    sanctioned overlap** — it MUST be excluded from the 9.1d/9.4c lens-purity metric,
    while `logic` + `completeness` (non-FAIL lenses) are banned from re-reporting
    injections.
  - **(c)** code-side injection canary in `apply` — **rejected** (violates C4).
  - **Recommendation:** **(b)** — keep `factual` as a grounding-domain backstop, ban
    only the *non-FAIL* lenses (`logic`, `completeness`) from re-reporting injections.
    Confirm in Architecture + the `/vdd-adversarial` plan review.
- **Q2:** few-shot location — inline in `SKILL.md` (concise, ≤ block limits) vs
  `examples/`? (skill-creator inline-block policy.)
- **Q3:** eval runner — **resolved toward the Workflow+grader.** `run_eval.py` exists
  (`.agentic-development/.agent/skills/skill-creator/scripts/`) but (i) it is
  framework-vendored + gitignored (not a repo contract) and (ii) it is a *trigger*-eval
  (does the description fire the skill?), **not** an output-quality grader. So the
  measurement uses a **committed Workflow + custom grader** (the proven dogfood
  fan-out). Architecture confirms + specifies the grader's structured-output schema.
- **Q4:** scope — this task touches **only** `wiki-verify`. The sibling
  SECURITY-SENSITIVE prompt skills (`wiki-query-synthesis`, `concept-extraction`)
  share the thin-prompt trait; do we note the rubric pattern for later reuse, or
  pull them in now? **Recommend:** scope to `wiki-verify`; record the pattern.

---

*Self-review against `03_task_reviewer_prompt` + `skill-task-review-checklist` follows
(VDD verification loop). Architecture phase updates `docs/ARCHITECTURE.md` in place.*
