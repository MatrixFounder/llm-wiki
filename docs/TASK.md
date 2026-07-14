# TASK 066 — DF-064-4: build the INSTRUMENT and establish an HONEST baseline. The fix is DEFERRED.

## 0. Meta Information

| | |
|---|---|
| **Tracks** | [[df-064-4-weak-model-extraction-recall-gap\|DF-064-4]] (SEV-3) — the HEAD of ROADMAP **R-23** |
| **Status** | **v3** — after **two** blocking task-reviews (8 critical total). **Every finding was verified against the code before it was applied, and three of them deleted requirements I had written myself.** |
| **Baseline** | `2848 passed, 14 skipped` · `mypy --strict scripts/` clean |

> ## ★★ THE HEADLINE: **THIS TASK SHIPS NO FIX — BECAUSE EVERY CANDIDATE FIX IS REFUTED.**
>
> v1 and v2 each proposed a mechanical fix for the recall gap. **Both were refuted by measurement,
> and so was the guard folded in from R-23 Phase B.** What remains is the honest position:
>
> **We do not currently know what to fix, and we do not have an instrument that could tell us.**
>
> §2 of this task's own v1 says: *"the instrument must exist before the fix is believed."* Shipping a
> guessed fix **in the same task** contradicts that sentence. This SKILL's history is **three edits,
> three precision/recall trades** (7/11 → 6/11 → 9/11). A fourth guess is not a fix; it is the
> pattern.

---

## 1. The problem

`skills/concept-extraction/SKILL.md` scores **9 / 11** on **Haiku 4.5** (`obsidian-personal`). Both
misses are **under-extraction** — *recall, not junk*: fixture **03** found 1 of 2 durable concepts;
fixture **09** extracted only «Падёж», under its **bare** name.

**Nothing counts what was left behind.** No validator, lint rule, or health check sees a concept the
extraction *dropped* — one of the three rules the SKILL's honesty ledger names as having **no
mechanism at all.**

---

## 2. ★★ THE INSTRUMENT DOES NOT EXIST — and that is the whole task

DF-064-4's fix sketch reads: *"any change must be re-run through the Haiku harness before it is
believed."* **THAT HARNESS DOES NOT EXIST AS CODE** (verified twice, independently: `grep` over
`tests/`, `scripts/`, `skills/`, `bin/` returns **only** the Decision-17 *absence* gates).

The 9/11 was produced **by hand**. It is not reproducible, not defensible against regression, and
**not a gate**.

### ★ M-1 — and the harness must NOT introduce this repo's first LLM client

`requirements.txt` carries **no `anthropic`** — the dependency was **deliberately removed by a
shipped task** (`docs/tasks/task-003-v3-10-drop-anthropic-dep.md`). The precedent I cited in v2
(`skills/wiki-verify/evals/`) ships **no client**: `grade.py` is a pure deterministic grader over
**recorded** `reports/*.json`. And `skills/concept-extraction/` is **symlinked into user installs** —
so an SDK there would ship to users, inside the rail whose defining invariant is *"no LLM client
here."*

**So the "live harness" IS THE ORCHESTRATOR** — which is exactly Decision-17 (*"the calling
orchestrator owns the reasoning step"*), not an exception to it. The deliverable splits in three:

| | | |
|---|---|---|
| **(1)** | **the runner** — a documented orchestrator procedure: one fresh context per fixture, given `SKILL.md` + the **real** `prepare` envelope + the body in the H-6 sentinel | **no SDK, no new dependency, nothing new shipped** |
| **(2)** | **the recorder** — deterministic Python that writes each fixture's raw output to `skills/concept-extraction/evals/reports/<model>-<date>.json`, **stamped with `skill_sha256` + per-fixture `input_sha256`/`grading_sha256` + `model`/`temperature`/`K`** | pure I/O |
| **(3)** | **the gate** — a deterministic pytest test in `tests/` grading the **recorded** artifact through the **real** validators + census + `forbidden` list | offline · CI-safe · **can go red** |

★ **(2)'s hashes are load-bearing** (v2's C-2): without them the gate goes **green forever on a stale
artifact** — and since **`SKILL.md` IS the artifact under test**, a contributor could rewrite it and
the gate would keep grading a recording of the old skill. The repo already owns this idiom one file
away (`wiki_extract_concepts/__init__.py:449-450` — `source_hash` + `check_idempotency`).

---

## 3. ★★ THE BASELINE IS CONTAMINATED — the 9/11 is not a number we may trust

**The census, RUN (not asserted):** every fixture's `expected.json` names, grepped against
`SKILL.md`.

| fixture | expected names printed in the prompt |
|---|---|
| **08** slug-is-derived | **1/1 — its NAME *and its exact expected SLUG***: `Проскальзывание` → `proskalzyvanie` is the SKILL's worked example **of the very derivation fixture 08 tests**. So its pass measures *"can the model copy the example"*, not *"can it derive a slug."* ⚠️ **CORRECTED:** v3 said "the entire candidate — name, slug, definition *and* quote." **That was repeated from the review and never checked. Measured: the definition and the quote are NOT in the SKILL.** An over-stated finding is as damaging as a missed one — and it is corrected here rather than quietly dropped, because this task exists precisely because a number was believed instead of measured. |
| **06** definition-is-not-the-quote | **2/2** |
| **09** two-candidates-one-file | **2/2** |
| 01 · 07 · 10 · 11 | 1 of each |
| **03 · 04 · 05** | **0 — CLEAN** |
| | **TOTAL: 9 of 19 expected names are in the prompt** |

Consequences, and the second is the one that decides this task:

1. **Part of the 9 is unearned.** Fixture **08** — whose whole six-key answer is the SKILL's STEP-4
   worked example — **passes**. The floor "≥ 9" is a **denominator with no census**.
2. ★★ **FIXTURE 09'S ANSWER IS PRINTED VERBATIM IN THE PROMPT — AND HAIKU STILL FAILS IT.**
   `SKILL.md:216-230` carries both expected names *and* an explicit *"And extract BOTH."*
   **The model is handed the answer and does not produce it.**

> **Therefore the recall gap is NOT a knowledge gap that better prompt text can close.** That is not
> an argument; it is a measurement. It refutes the entire class of SKILL-side fixes — including the
> one v2 was about to build.

---

## 4. ★★ WHY THE FIX IS DEFERRED — all three candidates are REFUTED

| candidate | why it is dead |
|---|---|
| **(a) strengthen the SKILL's disambiguation rule** | **§3.2.** The rule is already there, with the exact expected names, and the model fails anyway. Any fix that "closes" 09 by editing that passage is **teaching to the test** — and it could not even work, since the test's answers are already in the prompt. |
| **(b) a mechanical slug-collision detector in `prepare`** (v2's R-066-6) | **REFUTED TWICE.** (i) The 9/11 baseline was measured on **`obsidian-personal` = `preserve-unicode`** (`evals/README.md:114`, `layouts/obsidian-personal.yaml:27`), where `падёж` / `падеж` are **distinct slugs — there IS no collision.** Fixture 09's own `grading.json` says so: *"Under `preserve-unicode` … BOTH pages are correctly written."* (ii) Under-extraction emits **ONE** candidate; a collision needs **TWO**. **A collision detector cannot fix a recall gap** — it would fire on nothing, on the layout the failure was measured on. *This is the vacuous-green disease, inside the requirement I wrote to replace the one I cut for that same disease.* |
| **(c) the tautology / stub write-time guard** (R-23 Phase B) | **REFUTED by its own false-positive control.** The SKILL's *own* blessed short definition («Форк — расхождение цепочки блоков.», `SKILL.md:211`) scores **12.8** — *below* the garbage «Синергия» at **22.0**. The bands interleave. The IDF *sum* was measuring **LENGTH**: every live definition is 80–320 chars, which is where "min 29.3" came from. |

**Three refutations, and not one of them came from reasoning.** Each came from a measurement that the
review demanded and the author had not run.

### ⚠️ AND MY OWN REFUTATION (c) WAS OVER-CLAIMED — the correction is recorded here

v2 wrote *"NO SCALAR CUTOFF EXISTS"* into §5 and into `docs/ROADMAP.md`. That is a **universal
negative drawn from N=2 vs N=2** — the very sin it condemns. Worse: **the measurement that produced
12.8 / 22.0 / 4.6 / 28.1 exists in NO FILE.** §2 of this task indicts the 9/11 for being *"produced
by hand … not reproducible"* — and then v2 closed a ROADMAP phase on four hand-run numbers over four
strings.

> **One evidentiary standard for what I wanted to BUILD, a weaker one for what I wanted to CUT.**

**Corrected:** what is refuted is **the IDF-sum family**, on its first false-positive control. The
general question — *can any scalar separate a garbage definition from a good one?* — is **UNMEASURED**,
and reopening it requires ≥30 per class **including short-but-good definitions**. The measurement
ships **as committed code + a recorded artifact** (**R-066-7**), or the refutation is exactly the kind
of claim this task exists to stop accepting.

---

## 5. What survives as a code change — and its live population is ZERO

`wiki_extract_concepts/_validation.py:689` classifies a candidate as a **`mention`** on **slug alone,
never on name** — and a mention **discards the definition**. So «Падеж» (grammar), extracted into a
vault that already owns `padezh` («Падёж» — livestock), would be filed as **a mention of the livestock
page**: a falsified provenance receipt at exit 0.

**Real in the code. But the census, RUN:** across the live vault's **685 entities**, the number of
name-pairs that collapse to one slug is **0 under `preserve-unicode` AND 0 under `transliterate`.**

> **So a REFUSAL here would be a gate that fires on nothing** — and a refusal on a currently-exit-0
> path is precisely how the 0.88 near-duplicate gate came to **block correct work** and get demoted
> (`SKILL.md:167-183`). **It ships as a WARNING in `prepare`, not a refusal** (**R-066-6**), and it is
> a **bug-fix, not this task's headline.**

---

## 6. Requirements Traceability Matrix

| ID | Requirement | Acceptance | The gate that proves it |
|---|---|---|---|
| **R-066-1** | ★ **THE RUNNER** — a documented orchestrator procedure (one fresh context per fixture; `SKILL.md` + the real `prepare` envelope + the H-6-wrapped body). **No SDK. No new dependency. Nothing new shipped** (§2 M-1). | A-2 | the committed artifact exists |
| **R-066-2** | ★ **THE RECORDER** — deterministic Python writing `evals/reports/<model>-<date>.json`, **stamped with `skill_sha256`, per-fixture `input_sha256`/`grading_sha256`, `model`, `temperature`, `K`.** | A-3 | `tests/…::test_the_artifact_is_stamped` |
| **R-066-3** | ★ **THE OFFLINE GATE** — grades the recorded artifact through the **REAL** validators **+** `expect` census **+** `forbidden` list. **It FAILS when any stamped hash disagrees with the working tree** (*"the SKILL changed — re-run the harness"*). Without this the gate is green forever on a stale recording of a skill nobody runs. | A-4 | `tests/test_concept_extraction_weak_model.py` |
| **R-066-4** | ★ **THE GATE MUST BE PROVEN ABLE TO FAIL — with a TARGETED mutation whose blast radius is NAMED BEFORE THE RUN.** Blanking `SKILL.md` proves only that a file is read. Remove **one named rule** (the theme-vs-prop table, credited with the 6/11 → 9/11 jump) and the drop must land **on the fixtures that rule guards.** | A-5 | mutation, RUN and recorded |
| **R-066-5** | ★ **THE CONTAMINATION CENSUS IS A TEST** — every `expected.json` name is grepped against `SKILL.md`; the count is **asserted**, so it can never silently grow. Today: **9 / 19**. | A-6 | `tests/…::test_the_contamination_census` |
| **R-066-6** | ★ **THE HONEST BASELINE** — `temperature = 0`, **K = 3**, **per-fixture majority**. Reported **THREE ways**: overall · on the **CLEAN subset {03, 04, 05}** · on the **contaminated subset**. **Per-fixture, never as a scalar floor** — a scalar gets *easier* as fixtures are added, and it hides the **fixture × layout** axis (fixtures declare `layouts[]`; the population is pairs, not 11). The **forbidden-emission count is RECORDED** (it is **≥ 1**, not the 0 that `evals/README.md:117` claims — corrected in the same change). | A-7 | the artifact + `test_the_baseline_is_recorded_honestly` |
| **R-066-7** | The **cross-source `mention` bug** (§5): a candidate whose slug matches a known page with a **differing NFC-normalised name** raises a **WARNING in `prepare`** — **never a refusal** (live population = **0**; a refusal would fire on nothing and could block correct work). | A-8 | `tests/…::test_a_slug_match_with_a_DIFFERENT_name_WARNS` |
| **R-066-8** | ★ **THE IDF REFUTATION SHIPS AS CODE** — the ~20-line measurement + its recorded output, so §4(c) is **reproducible** rather than four hand-run numbers. `ROADMAP.md` R-23 is reworded from *"no scalar cutoff exists"* to *"the IDF-sum family failed its first FP control; the general question is UNMEASURED."* | A-9 | `skills/concept-extraction/evals/measure_definition_idf.py` + artifact |
| **R-066-P** | ★ **THE PROPERTY — a CONJUNCTION.** `(no fixture that PASSES at baseline may FAIL)` **AND** `(forbidden emissions ≤ baseline)`. *The first half catches REGRESSION; the second catches the TRADE — this SKILL's history is three trades.* **Neither half is a scalar floor**, so neither gets easier when the set grows. | A-10 | the offline gate |

**CUT in v3:** ~~a SKILL-side disambiguation rule~~ (§4a) · ~~a slug-collision detector~~ (§4b) ·
~~the tautology/stub write-time guard~~ (§4c). **All three refuted by measurement.**

---

## 7. Acceptance criteria

- [ ] **A-1** `pytest tests/` ≥ 2848 passed, **0 failed**, `xfailed: N` **stated**. `mypy --strict
      scripts/` clean **AND** `mypy --strict skills/concept-extraction/evals/` clean.
- [ ] **A-2** The runner procedure is documented and **executed**; its artifact is **committed**.
- [ ] **A-3** The artifact carries **every** stamp (skill + per-fixture input + grading + model +
      temperature + K).
- [ ] **A-4** ★ **The gate FAILS on a stale artifact.** MUTATION: touch one byte of `SKILL.md` ⇒ RED.
      **RUN IT.**
- [ ] **A-5** ★ **The targeted mutation is EXECUTED**, its blast radius **named before the run**, and
      the drop lands on the predicted fixtures.
- [ ] **A-6** The contamination census is a **test**; today's count (**9/19**) is asserted.
- [ ] **A-7** The baseline is recorded **three ways** + its forbidden count. **A different number is
      a fact, not a failure** — record it and re-baseline; **never tune the harness until it prints 9.**
- [ ] **A-8** The `mention` warning fires; a test goes RED without it. **No refusal is added.**
- [ ] **A-9** The IDF measurement runs from a clean checkout and reproduces §4(c)'s numbers.
- [ ] **A-10** **R-066-P holds.**
- [ ] **A-11** **Decision-17 survives — the census is DERIVED BY GREP AT TEST TIME, not hand-listed**
      (v2 hand-listed *three* `anthropic` gates; there are at least **five**). No new LLM client, no
      new dependency, nothing new in the shipped skill payload.
- [ ] **A-12** **Zero DDL** — `git diff sql/` empty.

---

## 8. Out of scope — **including the fix**

- ★ **THE RECALL FIX ITSELF.** All three candidates are refuted (§4). The next task is authored
  **from what the instrument says**, not from a fourth guess. *This is the whole point of §2.*
- **A scalar definition-quality cutoff of any kind** — reopening requires ≥30 per class, including
  short-but-good definitions.
- **`wiki-health definitions` as a corpus sweep** — the corpus is measured EMPTY (0 stubs, 0
  tautologies / 685).
- **DF-064-2** (the O(n²) near-dup scan) — independent; `wiki-lint --strict` = **1.8 s** live.

---

## 9. Stated boundaries

- `pytest.ini:2` — `testpaths = tests`. Anything under `skills/` is **not collected**; that is why the
  gate and the tripwires live in `tests/`.
- `pytest.ini:4` — `--strict-markers`. A new marker must be registered or collection fails.
- `skills/concept-extraction/` is **symlinked into user installs** — the recorder and the artifact
  **ship to users**. `evals/` already does; this is a **stated choice**, not a side effect.
- The runner needs a model and is **never in the CI path**. That is precisely why the gate reads a
  **recorded** artifact.
- **Fixture-level contamination is NOT fully removable.** A teaching SKILL legitimately shares
  vocabulary with same-domain fixtures. The census makes it **visible and bounded**; it does not
  eliminate it. **Stated, not hidden** — 7 fixtures remain contaminated by design.

## 10. Open questions

**None blocking.** The fix is out of scope *because the evidence says we do not yet know what it is* —
which is a finding, not an unknown.
