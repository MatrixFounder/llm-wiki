---
id: DF-064-4
type: known-issue
status: open
opened_at: 2026-07-14
category: quality
severity: SEV-3
slug: df-064-4-weak-model-extraction-recall-gap
---

# `concept-extraction` on a weak model under-extracts: 9/11 on Haiku 4.5, and the two misses are RECALL, not junk

- **Symptom**: the TASK-064 eval set, run on **Haiku 4.5** (one fresh context per fixture, given only
  `SKILL.md` and what `prepare` really emits, graded through the real validators + census), scores
  **9 / 11**. The floor is recorded in `skills/concept-extraction/evals/README.md`.

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

- **Fix sketch** — and it must be **measured, not reasoned**:
  1. Fixture **09** is the harder one: two concepts whose names differ by a single letter, in
     different sections. Likely needs an explicit *"walk the source's sections; a headed section
     usually carries at most one concept"* instruction — but the last two SKILL edits each traded one
     failure class for another, so **any change must be re-run through the Haiku harness before it is
     believed.**
  2. Consider promoting these to **`expected_fail` xfail tripwires** carrying `tracks: df-064-4`
     (the `skills/wiki-import/evals/` convention), so an unexpected **xPASS** signals the gap closed
     and the floor can be re-baselined — instead of the misses quietly becoming the norm.

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
  real 685, scoring information carried *beyond the concept's own name*. Garbage scores **4.6–22.0**;
  the corpus's **worst** definition scores **29.3**. Clean separation, no overlap.
- ⚠️ **STATED BOUNDARY**: an IDF measure calibrated on its own corpus cannot see garbage that is
  *typical of that corpus*. The zero holds for the canonical failure shapes, not for every
  conceivable one.

**So the write-time guard must be calibrated the same way** — on a measured population, never on the
example that motivated it. That is the 0.88 lesson, and it is the reason this issue leads the theme
instead of a corpus sweep that would have reported clean and taught nothing.
