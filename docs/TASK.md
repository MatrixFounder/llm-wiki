# TASK 066 — DF-064-4: the weak-model recall gap, and the instrument that can prove it closed

## 0. Meta Information

| | |
|---|---|
| **Tracks** | [[df-064-4-weak-model-extraction-recall-gap\|DF-064-4]] (SEV-3, open) — the **HEAD** of ROADMAP **R-23** |
| **Status** | **v2** — after a blocking task-review (4 critical, 4 major, 3 minor; **every one verified against the code, every one applied**) |
| **Baseline** | `2848 passed, 14 skipped` · `mypy --strict scripts/` clean |
| **★ v2 headline** | **R-23 Phase B is CUT** — its threshold was refuted by measurement (§5). **Q-066-2(b) is CUT** — it is already in the SKILL and already failed (§4). |

---

## 1. The problem

`skills/concept-extraction/SKILL.md` scores **9 / 11** on **Haiku 4.5**. Both misses are
**under-extraction** — *recall, not junk*:

| fixture | miss |
|---|---|
| **03** ui-chrome-and-primitives | found **1 of 2** durable concepts (dropped «Параметризованный запрос»); emitted **no** junk |
| **09** two-candidates-one-file | extracted only **«Падёж»**, under its **bare** name — the second concept dropped, and the bare name is **item 1 on that fixture's own `forbidden` list** (`09-two-candidates-one-file/grading.json:6`) |

**Nothing counts what was left behind.** No validator, no lint rule, no health check sees a concept
the extraction *dropped* — one of the three rules the SKILL's honesty ledger names as having **no
mechanism at all**. The eval set is the only instrument that can observe it.

> ⚠️ **The published baseline under-reports itself.** `evals/README.md:117` calls that run *"Zero
> junk"*. It emitted a **forbidden** name. The count is **≥ 1, not 0**, and this task corrects the
> README in the same change (M-4) — a baseline that flatters itself cannot be improved against.

---

## 2. ★★ THE BLOCKER — the harness does not exist

DF-064-4's own fix sketch reads: *"any change must be re-run through the Haiku harness before it is
believed."* **THAT HARNESS DOES NOT EXIST AS CODE.**

Verified, and independently re-verified by the reviewer: `grep -rl "haiku|anthropic|messages.create"`
over `tests/`, `scripts/`, `skills/`, `bin/` returns **only the Decision-17 gates** — the tests
asserting an LLM client is *absent*. `tests/test_concept_extraction_evals.py` grades the **static
`expected.json`**, never a model run. The README's "Re-running it" is **four sentences of prose**.

The 9/11 was produced **by hand**. It is therefore not reproducible, not defensible against
regression, not vendor-agnostic, and **not a gate**.

### ★ C-3 — and §2's own indictment must be discharged, not repeated

v1 said *"not a gate"* and then required only a **runnable** harness — leaving the floor
unenforceable, exactly as condemned. Worse, `pytest.ini:2` sets `testpaths = tests`, so a harness
under `skills/` **is not collected by `pytest tests/` at all**, while R-066-9's `xfail` tripwires
exist only inside pytest. Two incompatible readings of one deliverable.

**So the deliverable SPLITS, following a precedent already in this repo**
(`skills/wiki-verify/evals/reports/*.json` — recorded eval runs are *already committed here*):

| | |
|---|---|
| **(1) the live harness** | an **opt-in dev instrument**, outside `tests/`, that calls the model and **writes each fixture's raw output to a committed artifact**: `skills/concept-extraction/evals/reports/<model>-<date>.json` |
| **(2) the gate** | a **deterministic pytest test in `tests/`** that grades those **recorded** outputs through the real validators + census + `forbidden` list, and carries the `xfail(strict=True)` tripwires |

(2) is offline, deterministic, CI-safe, **and it can go red.** It catches every regression except
model drift; model drift is caught by re-running (1) and committing the new artifact.

---

## 3. ★ THE PERVERSE INCENTIVE — verified in the code

`_validation.py:259-268` — `check_in_batch_collisions` iterates **only over `candidates`**. Two
candidates → one slug → refuse. **Drop one → `seen` never collides → clean pass.**

> **The collision gate REWARDS under-extraction.** The safest way for a weak model to survive it is
> to extract fewer concepts — which is the failure this task exists to fix.

### ★★ M-1 — and its CROSS-SOURCE twin is LIVE, SILENT, and WORSE

`_validation.py:689` classifies a candidate as a **`mention`** on **slug alone**, never on name:

```python
if item["slug"] in known_slugs:
    annotated["action"] = "mention"      # ← the candidate's `definition` is DISCARDED
```

So «Падеж» (grammatical case), extracted from a *later* note into a vault that already owns `padezh`
(«Падёж» — livestock death), is filed as **a mention of the livestock page**. Its definition is
thrown away. **A falsified provenance receipt, written at exit 0, with a correct-looking count.**

That is precisely the failure that got the near-duplicate *refusal* demoted — and fixture 09's own
`grading.json:2` already admits the sibling gap (*"G5 compares a candidate only against the vault's
EXISTING slugs, never against its in-batch siblings"*).

---

## 4. ★ C-2 — THE SKILL ALREADY CARRIES THE FIX, AND IT ALREADY FAILED

`SKILL.md:216-230` **already** contains fixture 09's exact expected names **and** an explicit
instruction to extract both:

```
✗  "Падёж"  and  "Падеж"       ← one letter apart …
✓  "Падёж скота"  and  "Грамматический падеж"
```
> **And extract BOTH.** Two look-alike terms in one source are two concepts, not one …

**Haiku failed 09 anyway.** Two consequences:

1. **Q-066-2(b) — "add a disambiguation rule to the SKILL" — is CUT.** It is not an open option; it
   is a **tried-and-failed** one. An implementer would burn a cycle re-adding text that is there.
2. ★ **Fixture 09's answer key is IN THE PROMPT.** Any fix that closes 09 by *strengthening that
   passage* is **teaching to the test** — the model would be copying names it was handed, and
   R-066-5 + R-066-P would both go green **on pure overfit** while the generalised gap is untouched.

**Therefore the primary fix must be MECHANICAL** (Q-066-2(a)), and a **held-out fixture is
mandatory** (R-066-5b).

---

## 5. ★★ C-1 — R-23 PHASE B IS **CUT**. Its threshold was REFUTED BY MEASUREMENT.

v1 claimed a *"clean separation"*: garbage **4.6–22.0**, live corpus **min 29.3**. The reviewer
demanded the missing half — a **false-positive control** — and it kills the requirement outright.

The SKILL itself blesses a short definition as **GOOD** (`SKILL.md:211`, verbatim: *"`Форк —
расхождение цепочки блоков.` is a good definition. Never pad to clear it."*). Measured against the
live 685:

| definition | class | IDF |
|---|---|---|
| **«Форк — расхождение цепочки блоков.»** | ★ **the SKILL's own example of a GOOD definition** | **12.8** |
| «Разница между ожидаемой и фактической ценой сделки.» | good | 28.1 |
| «Синергия — это когда есть синергия между командами.» | **GARBAGE** | **22.0** |
| «Тултип это тултип.» | GARBAGE | 4.6 |

**The definition the SKILL teaches scores BELOW the garbage it is meant to catch.** The bands do not
separate — they *interleave*. My "min 29.3" was an artifact: every definition in the live corpus is
**long** (80–320 chars), so the IDF **sum** was measuring **length**, not informativeness.

**Length-normalising does not rescue it** (measured): good **4.02–4.28**, garbage **4.40–4.58** — a
0.12 gap, **inverted**, on N=2 vs N=2. That is noise, and a threshold drawn from two examples is the
0.88 disease with a new hat.

> ### **NO SCALAR CUTOFF EXISTS. R-066-7 is CUT, and per this repo's own 0.88 precedent that is a SUCCESS, not a failure.**
>
> The calibration set had **N=2** in its garbage class, and **both were the examples that motivated
> the check.** *"Calibrated on the population"* was true of the 685 and **false of the band that set
> the threshold** — the exact shape the previous revision of R-23 warned against, committed by the
> author of that warning.

R-23 Phase B is closed as **refuted**. The remaining defence stays where TASK 064 put it: **STEP 3 of
the SKILL**, and the honesty ledger that says so out loud.

---

## 6. ★ C-4 — the baseline is a STOCHASTIC measurement, and v1 treated it as a scalar

v1 demanded the harness *"reproduce 9/11"* with *"the same two failures"* — pinning **no temperature,
no seed, no run count, no tolerance.** A *correct* harness can legitimately print 8/11 or 10/11 on
run 1. As written, that criterion either fails the task for noise or invites **re-running until it
prints 9** — p-hacking the baseline the whole task is measured against.

**Pinned:** `temperature = 0`, **K = 3** runs, score = **per-fixture majority**, and the baseline is
**re-measured and re-recorded** if it disagrees — *the number moves; the harness is never tuned until
it agrees.*

---

## 7. Requirements Traceability Matrix

| ID | Requirement | Acceptance (§8) | The gate that proves it |
|---|---|---|---|
| **R-066-1** | ★ **THE LIVE HARNESS** — one **fresh context per fixture**, given only `SKILL.md` + the **real** `prepare` envelope + the body in the H-6 sentinel. **Vendor-agnostic** (pluggable provider). Writes each fixture's raw output to `evals/reports/<model>-<date>.json`. | A-2 | manual run + the committed artifact |
| **R-066-2** | ★ **THE OFFLINE GATE** — a pytest test in `tests/` grading the **recorded** artifact through the **REAL** validators **+** `expect` census **+** `forbidden` list. **Never by eye.** | A-3 | `tests/test_concept_extraction_weak_model.py` |
| **R-066-3** | ★ **THE GATE MUST BE PROVEN ABLE TO FAIL — with a TARGETED mutation whose blast radius is PREDICTED IN ADVANCE.** Blanking `SKILL.md` proves only that the harness reads a file. Remove **one named rule** (the theme-vs-prop table, credited with the 6/11 → 9/11 jump) and the drop must land **on the fixtures that rule guards, named before the run.** | A-4 | mutation, RUN and recorded |
| **R-066-4** | The baseline is **9/11 at `temperature=0`, K=3, per-fixture majority**, failures **03** and **09** — **and its `forbidden`-emission count is RECORDED (it is ≥ 1, not 0)**. `evals/README.md:117` is corrected in the same change. | A-5 | the committed artifact + `test_the_baseline_is_recorded_honestly` |
| **R-066-5a** | Close **fixture 03**: 2 of 2, zero `forbidden`. | A-6 | the offline gate |
| **R-066-5b** | ★ **HELD-OUT COLLISION FIXTURE (12)** — a ё/е (or й/и) pair appearing **NOWHERE in `SKILL.md`**. **Without it, closing 09 cannot be distinguished from memorising the answer key that is already in the prompt (§4).** | A-7 | the offline gate + a grep proving the names are absent from `SKILL.md` |
| **R-066-6** | ★ **THE MECHANICAL FIX (Q-066-2(a))** — `prepare` deterministically computes, from the source body + `known_concepts` + `slug_strategy`, the names that **would collide**, and surfaces them. **Zero LLM calls; fully gradeable offline.** | A-8 | `tests/test_concept_extraction_collisions.py` |
| **R-066-7** | ★ **THE CROSS-SOURCE TWIN (M-1)** — a candidate whose slug matches a known page whose **NAME differs** (NFC-normalised) must **not** be silently filed as a `mention` with its definition discarded (`_validation.py:689`). | A-9 | `tests/…::test_a_slug_match_with_a_DIFFERENT_name_is_not_a_mention` |
| **R-066-8** | Any miss that remains ships as **`xfail(strict=True)`** carrying `tracks: df-064-4` — an unexpected **xPASS** signals the gap closed and forces a re-baseline. | A-10 | pytest `xfailed` count, asserted |
| **R-066-P** | ★ **THE PROPERTY — a CONJUNCTION.** `(majority score ≥ 9)` **AND** `(forbidden emissions ≤ baseline, and 0 on the held-out fixture)`. *The floor catches REGRESSION; the forbidden list catches the TRADE.* **Half 1 alone is satisfied by changing NOTHING** (today's score is 9) — half 2 is not (the baseline emits a forbidden name). Verified: the conjunction bites. | A-11 | the offline gate |

**~~R-066-7 (v1) — the tautology/stub write-time guard~~ — CUT (§5, refuted by measurement).**
**~~Q-066-2(b) — a SKILL-side disambiguation rule~~ — CUT (§4, already present and already failed).**

---

## 8. Acceptance criteria

- [ ] **A-1** `pytest tests/` ≥ 2848 passed, **0 failed**, `xfailed: N` **stated**. `mypy --strict
      scripts/` clean **AND** `mypy --strict skills/concept-extraction/harness/` clean *(m-1: the
      shipped contract covers `scripts/` only — harness code would otherwise be type-unchecked by
      construction)*.
- [ ] **A-2** The live harness runs from a clean checkout and **commits its artifact**.
- [ ] **A-3** The offline gate grades that artifact — and **fails** if the artifact is missing.
- [ ] **A-4** ★ **THE TARGETED MUTATION IS EXECUTED.** The predicted fixtures are named **before**
      the run; the drop lands on them. Score recorded.
- [ ] **A-5** Baseline **9/11** (K=3, majority, `temperature=0`), failures **03** + **09**, forbidden
      count **recorded**. A different 9 is a different skill — say so and re-baseline.
- [ ] **A-6** Fixture **03**: 2/2, zero forbidden.
- [ ] **A-7** Fixture **12** (held out): 2/2 — **and a grep proves its names appear nowhere in
      `SKILL.md`.**
- [ ] **A-8** `prepare` surfaces the collision warning. Tested with **zero** model calls.
- [ ] **A-9** The cross-source `mention` bug is closed, with a test that goes RED without the fix.
- [ ] **A-10** Every remaining miss carries an `xfail(strict=True)` tripwire.
- [ ] **A-11** **R-066-P holds.**
- [ ] **A-12** **Decision-17 survives — ASSERTED, not assumed.** The three gates and their real
      scopes: `tests/test_extract_decisions_dispatch.py:126-135` (roots at `scripts/wiki_skills`, an
      **enumerated six-target allowlist**), `tests/test_concept_extraction_evals.py:516` (greps
      **`SKILL.md` only**), `:551` (AST env-read gate, globs **the `wiki_extract_concepts` package
      only**). A harness at `skills/concept-extraction/harness/` trips **none** — and the census above
      is the proof, not the claim.
- [ ] **A-13** **Zero DDL** — `user_version` stays 7. **`git diff sql/` empty.**

---

## 9. Out of scope

- **`wiki-health definitions` as a corpus sweep** — the corpus is measured EMPTY (0 stubs, 0
  tautologies over 685). It would fire on nothing.
- **A scalar definition-quality cutoff of ANY kind** — refuted in §5. Reopening it requires a
  measured population of **both** classes, ≥30 each, including short-but-good definitions.
- **DF-064-2** (the O(n²) near-duplicate scan) — independent. `wiki-lint --strict` measures **1.8 s**
  on the live vault (re-measured 2026-07-14 with a vacuity probe taken *from* the timed op — the
  first attempt read **125 ms**, because the CLI was failing into `/dev/null` and I was timing its
  crash).

---

## 10. Stated boundaries (m-2 — a boundary that is merely TRUE is the disease)

- `pytest.ini:2` — `testpaths = tests`. The harness under `skills/` is **not collected**. That is why
  the gate (R-066-2) and the tripwires (R-066-8) live in `tests/`.
- `--strict-markers` is on. Any new `live` / `llm` marker **must** be registered in `pytest.ini` or
  collection fails.
- `skills/concept-extraction/` is **symlinked into user installs** — so the harness **ships to
  users**. `evals/` already does; this is precedent, and it is a **stated choice**, not a side effect.
- The **live** harness needs network + an API key. It is **opt-in and never in the CI path** — that
  is the whole reason the gate reads a recorded artifact instead.

## 11. Open questions

**None blocking.** Q-066-1 (Decision-17) is **RESOLVED** by the three-gate census in A-12.
Q-066-2 is **RESOLVED**: (b) is cut (§4), (a) is R-066-6.
