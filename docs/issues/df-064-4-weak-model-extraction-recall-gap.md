---
id: DF-064-4
type: known-issue
status: partially-fixed
opened_at: 2026-07-14
category: quality
severity: SEV-3
slug: df-064-4-weak-model-extraction-recall-gap
---

# `concept-extraction` under-extracts on a weak model — RECALL, not junk (span defect FIXED; residual is model-breadth, not code)

> ## ★ RESOLUTION (2026-07-15) — read this first; the sections below are the audit trail
>
> This issue was worked to conclusion over TASK 066. The arc, and why nothing more is scheduled:
>
> 1. **The number was never measured** — the "9/11 on Haiku" was produced BY HAND. TASK 066 built
>    the instrument (`skills/concept-extraction/evals/harness.py` + `tests/test_concept_extraction_
>    weak_model.py` + a stamped, committed artifact) and re-ran it: the real score was **7/11**, with
>    **2 forbidden names** the "zero junk" claim had missed.
> 2. **The dominant cause was NOT recall** — it was `source_span`: **9 of 13** failing runs were a
>    bad line-range. The model was doing arithmetic on line numbers. `apply` now DERIVES the span from
>    the already-verbatim quote (`source_span` is OPTIONAL). Result: **7/11 → 10/11**, CLEAN subset
>    **2/3 → 3/3**, forbidden unchanged.
> 3. **The residual recall gap is REAL but it is not a code defect.** A live go/no-go (Haiku vs Opus
>    on 10 real notes) measured **~40% recall loss** — but it is **BREADTH** (a weak model finds fewer
>    concepts across the board), **not** the look-alike case the original fix sketch aimed at. **No
>    mechanical lever applies** (§"LIVE-CORPUS MEASUREMENT" shows the collision lever fires on almost
>    none of the misses). The practical lever is **model choice**, and the instrument now *measures
>    any model before it is trusted* — that IS the deliverable.
>
> **DECISION: no further code work is scheduled. Status stays `partially-fixed`, and the "partial" is
> PERMANENT, not pending** — the actionable defect (span) is fixed and measured; the residual is a
> property of the model that runs the rail, documented, not a bug awaiting a patch. The original
> **"Fix sketch" below is REFUTED** (annotated in place). Anyone reopening it must clear the bar in
> §"LIVE-CORPUS MEASUREMENT": a lever must be *measured on the harness*, against BOTH the fixtures and
> a live-note sample — prompt text alone is refuted (fixture 09 already carries its answer in the
> SKILL and the model still fails it).

- **Symptom** *(original filing — the number is superseded; see RESOLUTION)*: the TASK-064 eval set,
  run on **Haiku 4.5**, was reported at **9 / 11** by hand. The instrument later measured **7 / 11**
  (and **10 / 11** after the span fix). The floor is recorded in
  `skills/concept-extraction/evals/README.md`.

  | fixture | miss |
  |---|---|
  | **03** ui-chrome-and-primitives | found **1 of 2** durable concepts (dropped «параметризованный запрос») |
  | **09** two-candidates-one-file | extracted only «Падёж», under its **bare** name; «Грамматический падеж» dropped entirely |

- **Both failures are UNDER-extraction.** Zero junk was emitted in either: no `тултип`, no
  `coalesce`, no `block_number`, no person page. **Zero invalid payloads** across all 11 fixtures.
  For the operator's stated goal (*definitions without garbage*) this is the **correct side to err
  on** — which is why the skill shipped at this score rather than being tuned further under time
  pressure.

- **Why it is a real gap anyway**: **nothing counts what was left behind.** No validator, no lint
  rule, and no health check can see a concept the extraction *dropped* — it is one of the three
  rules named in the SKILL's honesty ledger as having **no mechanism at all**. A recall gap is
  therefore permanently invisible outside this eval set, which is exactly what makes the eval set
  the only instrument that can observe it.

- **What is already known about the cause** (measured across three Haiku runs — see the README):
  the **durability bar** and the rule *"the source does not have to DEFINE the term"* are **coupled**.
  Tightening one collapses the other, and a weak model does not hold the balance a strong one holds
  silently:

  | SKILL state | Haiku | failure |
  |---|---|---|
  | *"extract only what the source EXPLAINS"* | 7/11 | returned `[]` on an incident report — the notes the rail exists for |
  | that rule removed | 6/11 | **over**-extracted: 6 concepts where 2 belong (`Ретраи`, `Обработчик`, `Платёжный шлюз`) |
  | + theme-vs-prop table + count smell test | **9/11** | under-extracts on 03 / 09 |

- **~~Fix sketch~~ — ⛔ REFUTED by measurement (see RESOLUTION + §"LIVE-CORPUS MEASUREMENT").**
  Its own instruction — *"any change must be re-run through the Haiku harness before it is believed"*
  — was the right test, and when the harness (which did not exist) was finally built and run, it
  refuted the sketch:
  1. ~~Fixture 09 needs a "one concept per section" instruction.~~ **The SKILL already carries fixture
     09's exact expected names AND an explicit "extract BOTH", and the model fails anyway** — the
     answer is in the prompt and prose is not the lever. And the LIVE gap is **breadth**, not the
     look-alike case this bullet describes.
  2. `expected_fail` xfail tripwires — **superseded** by the stronger gate TASK 066 shipped:
     `tests/test_concept_extraction_weak_model.py` enforces a PER-FIXTURE floor against a stamped,
     committed baseline (no fixture that passes may regress), which does everything the xfail
     tripwire would and also catches junk-for-recall trades.

- **Do not "fix" this by loosening the census.** A fixture that lowers its own `expect` to match what
  the model produced is how a recall gap becomes permanent and green.

---

## ★ PROMOTED to the HEAD of ROADMAP R-23 (2026-07-14) — and R-23 Phase B folds in here

The live-corpus sweep that Phase A made possible (685 entities · 684 concept pages) came back:

| | |
|---|---|
| definitions present | **685 / 685 (100 %)** |
| **EMPTY / stub** | **0** |
| **TAUTOLOGICAL** | **0** |

**There is no garbage to clean.** `wiki-health definitions` over that corpus would fire on nothing —
a vacuous green, which is the one thing this project has learned not to ship. So R-23 Phase B's
tautology / stub detectors **move here, to the WRITE path**, and this issue becomes the theme's head.

**The reasoning is the point:** the corpus is clean **because a strong model wrote it.** That is not
a property of the code — it is a property of the model that happened to run. This issue *is* the
measurement of what happens when a weaker one does, and it already shows the loss (9/11). Detection
over a clean past is inert; prevention on the future is not.

**The zero was EARNED, and earning it took two attempts** — worth knowing before anyone reuses these
detectors:

- The prototype `_is_tautology` (stop-list + stem-subset) is **BLIND to the canonical case**:
  «Синергия — это когда есть синергия между командами» **PASSES** it, because no stop-list author
  thought of `есть`/`командами`. Its zero would have been meaningless. *A check that cannot fire on
  the example that motivated it cannot certify a corpus.*
- The sweep that produced the zero uses **no stop-list and no hand-picked threshold** — IDF over the
  real 685, scoring information carried *beyond the concept's own name*.

> ### ⛔ AND THE WRITE-TIME GUARD WAS **REFUTED** THE SAME DAY (TASK 066 review)
>
> This section originally claimed *"garbage 4.6–22.0, the corpus's worst 29.3 — clean separation,
> no overlap."* **The false-positive control was never run.** When it was:
>
> | definition | class | IDF |
> |---|---|---|
> | «Форк — расхождение цепочки блоков.» | ★ **the SKILL's OWN example of a GOOD definition** | **12.8** |
> | «Синергия — это когда есть синергия между командами.» | **GARBAGE** | **22.0** |
>
> **The definition the SKILL teaches scores BELOW the garbage the guard was built to catch.** The
> bands do not separate — they **interleave**. "Min 29.3" was an ARTIFACT: every live definition is
> **long** (80–320 chars), so the IDF *sum* was measuring **LENGTH**. Length-normalising does not
> rescue it either.
>
> **The IDF-SUM FAMILY is refuted; the general question is UNMEASURED.** (An earlier draft wrote
> *"no scalar cutoff exists"* — a universal negative from N=2 vs N=2, i.e. the very sin it condemns.)
> The measurement now ships as code: `evals/measure_definition_idf.py`, reproducible on a clean
> checkout. **R-23 Phase B is CLOSED AS REFUTED.**

**The lesson that survives:** a guard must be calibrated on a **measured population of BOTH
classes** — never on the examples that motivated it. That is the 0.88 lesson, and this issue
leads the theme precisely because a corpus sweep would have reported clean and taught nothing.


---

## ★★ TASK 066 (2026-07-15) — THE INSTRUMENT WAS BUILT, AND IT REFUTED THIS ISSUE'S OWN DIAGNOSIS

**This issue is filed as an under-extraction / RECALL gap. It was not — not mostly.**

The fix sketch above says *"any change must be re-run through the Haiku harness before it is
believed."* **That harness did not exist.** The 9/11 was produced by hand and was never
reproducible. TASK 066 built it (`evals/harness.py` + `tests/test_concept_extraction_weak_model.py`
+ a stamped, committed artifact), re-ran the set on **33 fresh Haiku contexts**, and graded the
recording through the **real** validators.

### It corrected the number

| | published (by hand) | measured |
|---|---|---|
| overall | 9/11 | **7/11** |
| "Zero junk" | claimed | **TWO forbidden names** |

### And then it named the actual cause

```
13 failing runs of 33
   9  ← source_span mismatch     (8 of the 11 fixtures)
   2  ← forbidden name (09)
   1  ← slug not derived
   1  ← CENSUS drop (RECALL)     ← the thing THIS ISSUE is named for
```

Per candidate (n=56): the `source_quote` was **verbatim 56/56 (100 %)**; the model's
`source_span` was correct **40/56 (71 %)**; the span was **derivable from the quote 56/56 (100 %)**.

> **We were asking a LANGUAGE MODEL to do ARITHMETIC ON LINE NUMBERS** — and then refusing the
> whole batch when it miscounted, though the concepts and the quotes were right.

**`apply` now DERIVES the span.** `source_span` is OPTIONAL; the SKILL tells the model to omit it.

### The result — measured on the same instrument

| | before | after |
|---|---|---|
| overall | 7/11 | **10/11** |
| **CLEAN subset** {03, 04, 05} | 2/3 | **3/3** |
| forbidden | 2 | **2** *(no recall bought with junk)* |
| span failures | 9 | **0** |

## ★ WHAT REMAINS — and it is finally ISOLATED

```
5  CENSUS (recall)   ← THIS issue, now standing alone
1  forbidden name
```

**Only fixture 09 fails.** The mechanical noise is gone and the recall gap is measurable for the
first time.

⚠️ **And what will NOT close it:** `SKILL.md` **already** carries fixture 09's exact expected
names *and* an explicit *"And extract BOTH."* **The model is handed the answer and does not
produce it.** Prompt text is not the lever — that entire class of fix is refuted by measurement.

**The next task must find a MECHANICAL lever, and measure it on this instrument.** A guess would
be the fourth precision/recall trade in this SKILL's history, and the first three all failed.

## Also closed by TASK 066

- **The cross-source `mention` hazard** (`_validation.py`: a candidate is filed as a `mention` on
  **slug alone**, discarding its definition). Real — but the population was MEASURED: across the
  operator's **685 live entities**, name-pairs collapsing onto one slug = **0** under BOTH slug
  strategies. So it ships as a **WARNING**, never a refusal: a refusal would fire on nothing, and
  that is exactly how the 0.88 near-duplicate gate came to block correct work.

---

## ★ LIVE-CORPUS MEASUREMENT (2026-07-15) — the gap is REAL but it is BREADTH, not look-alikes

The instrument (TASK 066) made a live go/no-go possible. Ran concept extraction on **10
knowledge-dense live notes** (a project-management learning zone — generic PM content, no
client material) through **Haiku vs Opus**, fresh context each, and compared the concept-name
sets (NFC + casefold + fuzzy pairing ≥0.8 to absorb «5 зачем»/«пяти зачем»-style variance).

| | |
|---|---|
| Opus concepts found | **37** |
| Haiku MISSED (of Opus's) | **15** → **recall 59%** |
| Haiku found beyond Opus | **10** |

**The recall gap is real and material — ~40% loss to a strong-model proxy.** Haiku dropped
genuine durable concepts: SCRUM, PMI, Crashing, Fast-track, метод набегающей волны, ИСР,
управленческие резервы, оценка снизу-вверх / сверху-вниз.

### ★★ BUT THE MEASUREMENT REFUTES THE PROPOSED MECHANICAL LEVER

The candidate fix (a confusable-term / collision detector, aimed at fixture 09's look-alike
case) targets the WRONG failure. The live gap is **broad under-extraction** — Haiku simply
finds fewer concepts, worst on long notes — NOT look-alike disambiguation. A collision
detector would fire on almost none of these 15 misses.

And `haiku-only = 10` shows it is **not** "Haiku is strictly worse": both models carry
variance (Haiku found Burndown Chart, Earned Value Analysis, Инициация проекта that Opus
missed). Opus is systematically **broader and more specific** (where Haiku gave a generic
«Резервы», Opus split it into «управленческие резервы» + «резервы на непредвиденные»).

### Caveats (stated, not hidden)

- **Opus is a strong-model PROXY, not ground truth.** A rigorous version needs a human judge.
- **K=1 per note** — the exact number is noisy; the direction and magnitude are not.

### DECISION

- **The collision/disambiguation lever (R-23 point 3, original scope) is NO-GO** — refuted by
  measurement, it aims at a failure the live corpus does not exhibit.
- **What survives:** recall is real, and **model choice dominates any prompt tweak.** The
  practical lever already shipped — the TASK-066 harness measures ANY model before it is
  trusted. An operator who needs full recall runs the rail on a strong model and can now
  *prove* the difference (this measurement is that proof).
- **If a general breadth lever is ever attempted**, it must be measured on this harness against
  BOTH the eval fixtures AND a live-note sample — not reasoned about. Prompt text alone is a
  weak lever here: fixture 09 already carries its answer in the SKILL and the model still fails.
