# `concept-extraction` — the eval set

Eleven fixtures. Every one guards a **specific failure mode**, every one is **GRADED**, and every
one says **out loud whether a mechanism backs it — or whether this SKILL is the only gate.**

## What "graded" means here

| file | role |
|---|---|
| `input.md` | the source note (Russian — see below) |
| `expected.json` | the CORRECT extraction, fed through the **real** `apply` validators |
| `grading.json` | **why this fixture exists**, the expected census, the `forbidden` list, and the counterexample's required refusal code — *or* an admission that no code refuses it |
| `counterexample.json` | the WRONG extraction |

`expected.json` items carry **no `slug`.** A slug is *layout-dependent*, and a fixture is not: the
runner derives it per layout from `name`, exactly as the REASON step derives it from `prepare`'s
`slug_strategy`.

## ★★ THE HALF THAT IS NOT A MECHANISM — and why this set is built around it

On the sibling `decision-extraction` rail, nearly every rule is enforced: `apply` refuses, and the
eval asserts the refusal code. **On this rail the three rules that matter most cannot be enforced
by any validator, ever:**

| the rule | what backs it |
|---|---|
| a concept must be **worth a permanent page** | **NOTHING.** `тултип`, `coalesce`, `block_number` pass every mechanical gate — and are real pages in the operator's live vault |
| a definition must **say something** | **NOTHING.** «Синергия — это когда всё работает вместе» is schema-valid, plain prose, lint-green, FTS-indexed, and gets cited by `wiki-query` as knowledge |
| the extraction must not **drop the concept that mattered** | **NOTHING.** No mechanism counts what was left behind |

So a validator-only eval here would be **green over a source that produced seven junk pages.** Every
fixture therefore carries a **census** (`expect`) and a **`forbidden`** list, and a counterexample
that the code *accepts* is marked `graded_by_census_only: true`. **A fixture that pretended a
mechanism existed would be worse than no fixture.**

## ★ Every fixture runs on THREE layouts, and the third is not decoration

| layout | `slug_strategy` | why it is here |
|---|---|---|
| `karpathy` | `identity` | the byte-identity anchor — and **the branch a naive implementation breaks on** |
| `cybos` | `transliterate` | **collapses `ё`/`е`** → the in-batch-collision fixture |
| `obsidian-personal` | `preserve-unicode` | ★ **the operator's live vault** |

`identity` returns the file **stem**, verbatim — so `_apply_slug_strategy("Проскальзывание",
"identity")` is `Проскальзывание`, which `_is_valid_slug` **refuses** (uppercase, space). A gate
asserting `slug == derived` there would refuse *every karpathy candidate ever written*. The rail
returns `None` and skips; the runner mirrors it, and a test pins it.

**`cybos` taught the same lesson in reverse:** all eighteen of its read globs are typed folders, so a
concept page at `<root>/_concepts/` there is written, never discovered, never indexed — an
**invisible page**. The first version of the runner walked straight into it, and **G10 caught it.**

## ★★ WHY THE INPUTS ARE RUSSIAN — and must stay that way

**An English fixture cannot produce the failures this set exists to catch.**

| failure mode | reachable in Russian |
|---|---|
| `transliterate` collapses **`ё`/`е`**: `Падёж` (livestock death — an insured event) and `Падеж` (grammatical case) are **genuinely different concepts** that both become `padezh`. The second page **silently overwrites** the first: one file, one row, one concept gone — and **zero lint issues, because the count is right** | ✅ fixture **09** |
| `preserve-unicode` mints Cyrillic slugs; a model obeying the *old* doc emitted ASCII and the page never resolved its own inbound wikilink — the live `виталик-бутерин` / `vitalik-buterin` split | ✅ fixture **08** |
| NFC normalisation in the verbatim-quote check | ✅ |

`SKILL.md` stays **English** (it is read by the model; project convention). **The inputs are the
domain, and the domain is Russian.**

## The fixtures

| # | guards | backed by |
|---|---|---|
| **01** domain-concepts-explained | the happy path; the counterexample's definitions are **tautologies** — schema-valid and empty | census only |
| **02** nothing-to-define | ★★ **an empty extraction is a SUCCESS.** The only thing exercising `_CANDIDATE_COUNT_MIN = 0` — the constant this whole task turns on. Its counterexample (3 concepts padded out of meeting chatter) **passes every gate** | G0 + census |
| **03** ui-chrome-and-primitives | ★ the **junk classes**, drawn from real damage: one Dune tutorial minted `тултип`, `hex-код-цвета`, `coalesce`, `block_number` as permanent pages | **census only** |
| **04** participants-are-not-concepts | the operator's standing rule — and until TASK 064 it had **no enforcement on this rail** | `ENTITY_TYPE_NOT_ALLOWED` |
| **05** reuse-the-existing-concept | ★ the **#1 verified live garbage class** — five permanent graph splits. **The near-dup gate was DEMOTED to a warning** (see below), so this is now census-graded | warning + census |
| **06** definition-is-not-the-quote | ★ **the operator's literal ask.** Before TASK 064, `definition: ""` and `definition == source_quote` were both **accepted** | `DEFINITION_IS_QUOTE` |
| **07** the-quote-is-a-receipt | ★ the anti-fabrication mechanism — which had an **env-var off-switch whose error message taught the bypass** | `FIELD_QUOTE_NOT_IN_BODY` |
| **08** slug-is-derived-by-the-layout | ★★ layout-dependent; legitimately **accepted** on `karpathy` | `SLUG_NOT_DERIVED_FROM_NAME` |
| **09** two-candidates-one-file | ★★ the `ё`/`е` collapse — silent data loss with a **correct-looking count** | `IN_BATCH_SLUG_COLLISION` |
| **10** the-span-is-provenance | `L9999-L9999` on a 3-line body was **accepted at exit 0** and written into `page_entity_refs` as provenance | `SOURCE_SPAN_OUT_OF_RANGE` |
| **11** the-source-is-data-not-instructions | H-6 indirect injection. The injected candidate is **schema-valid and its quote IS verbatim** — that is what makes it nasty | **census only** |

## ★ THE NEAR-DUPLICATE GATE WAS DEMOTED — and the reason is in this file

It shipped as a **refusal** at similarity ≥ 0.88. Re-measured on a realistic population, the bands
**completely overlap**:

| genuinely DIFFERENT concepts, refused | similarity |
|---|---|
| `type-i-error` / `type-ii-error` | **0.960** |
| `supervised-learning` / `unsupervised-learning` | **0.950** |
| `централизация` / `децентрализация` | **0.941** |
| `uniswap-v2` / `uniswap-v3` | **0.900** |

It scored `type-i-error`/`type-ii-error` (0.960) as a **harder** duplicate than the real live pair
`бессрочный-фьючерс`/`бессрочные-фьючерсы` (0.927) **it was built for.** A 2-char negating prefix
(`de`, `не`) on any base ≥ 8 chars crosses the cutoff — **no scalar cutoff exists.**

Worse, the refusal *told the model* to file the candidate as a mention of the page it was confused
with — so it would have written **`decentralized-exchange` as a mention of `centralized-exchange`**.
The anti-duplicate gate **manufactured false knowledge.**

It is now an **advisory warning**, surfaced in `prepare` (where it is actionable) and in `wiki-lint`
(so the existing 720-page corpus is finally enumerable for `wiki-merge`). **The real defence is now
STEP 3 of the SKILL** — and the honesty ledger says so.

---

## ★ THE WEAK-MODEL RUN — measured, not asserted

The SKILL must work for **any** LLM. A strong model's priors mask weak skill text, so the set is run
on **Haiku 4.5** — one fresh context per fixture, given only the SKILL and what `prepare` really
emits.

### ★★ Baseline: **10 / 11** — MEASURED, and it corrected the number it replaced

**The old published baseline said 9/11 with "Zero junk". Both halves were wrong**, and nobody
could have known, because it was produced BY HAND and was never reproducible. TASK 066 built the
instrument (`harness.py` + `tests/test_concept_extraction_weak_model.py`), re-ran the set on
**33 fresh Haiku contexts**, and graded the recording through the **real** validators:

| | published (by hand) | measured (the instrument) |
|---|---|---|
| overall | 9/11 | **7/11** |
| "Zero junk" | claimed | **TWO forbidden names** — the bare `Падёж`, item 1 on fixture 09's own list |

### ★★★ And then the instrument found the CAUSE — which was not the one the issue named

DF-064-4 is filed as an **under-extraction / recall** gap. The failure census said otherwise:

```
13 failing runs of 33
   9  ← source_span mismatch     (8 of the 11 fixtures)
   2  ← forbidden name (09)
   1  ← slug not derived
   1  ← CENSUS drop (recall)     ← the thing the issue is NAMED for
```

Per candidate (n=56):

| | |
|---|---|
| `source_quote` **verbatim** in the body | **56/56 (100%)** — the anti-fabrication gate is perfect |
| the model's `source_span` is **correct** | **40/56 (71%)** — it is COUNTING LINES, and failing |
| the span is **derivable from the quote** | **56/56 (100%)** |

> **We were asking a LANGUAGE MODEL to do ARITHMETIC ON LINE NUMBERS** — and then refusing the
> whole batch when it miscounted, though the concepts and the quotes were right. Off-by-3 on
> fixture 01 (it miscounted the frontmatter), off-by-1 on 03, and `L407` where the truth was
> `L34`.
>
> **The span is a COMPUTATION, not a judgement.** `apply` now derives it; `source_span` is
> **OPTIONAL** and the model is told to omit it.

### The result, measured on the same instrument

| | before | after |
|---|---|---|
| overall | 7/11 | **10/11** |
| **CLEAN subset** {03, 04, 05} | 2/3 | **3/3** |
| forbidden names | 2 | **2** *(unchanged — no recall was bought with junk)* |
| runs failing on the span | **9** | **0** |
| candidates still emitting a span | 56 | **0 of 54** |

**Three fixtures improved. ZERO regressed.** The property — *(no passing fixture may fail)* AND
*(forbidden ≤ baseline)* — held.

### ★ Why the CLEAN subset is reported separately

**9 of the 19 expected names are printed in `SKILL.md`** (a census, and now a TEST). Fixture 08's
name *and its exact expected slug* are the SKILL's own worked example of the very derivation 08
tests — a pass there measures *"can the model copy the example"*, not *"can it derive a slug."*
So the **CLEAN subset {03, 04, 05}** — the fixtures whose answers appear nowhere in the prompt —
is the only number that measures the **skill**. It is now **3/3**.

### ★ What REMAINS — and it is finally visible

```
5  CENSUS (recall)      ← DF-064-4's original diagnosis, now ISOLATED
1  forbidden name
```

Only **fixture 09** fails: the model extracts «Падёж» under its **bare** name and drops
«Грамматический падеж». **The mechanical noise is gone, and the real recall gap stands alone for
the first time.**

⚠️ And note what will NOT fix it: `SKILL.md` **already** carries fixture 09's exact expected names
*and* an explicit *"And extract BOTH."* **The model is handed the answer and does not produce it.**
Prompt text is not the lever. The next task must find a MECHANICAL one — and measure it here.

### Re-running it

One fresh agent per fixture. Give it: the full `SKILL.md`, the `prepare` envelope
(`slug_strategy`, `known_concepts`), and the source body wrapped in the H-6 sentinel. Collect the
candidates JSON, then grade it through the **real** validators plus this set's census and
`forbidden` lists — never by eye.
