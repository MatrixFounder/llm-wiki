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

### Baseline: **9 / 11** (Haiku 4.5, `obsidian-personal`, 2026-07-14)

**Zero junk. Zero invalid payloads.** Both remaining failures are **under**-extraction, which is the
correct side to err on:

| fixture | miss |
|---|---|
| **03** | found 1 of 2 durable concepts — but emitted **no** `тултип`, `coalesce`, or `block_number` |
| **09** | extracted only `Падёж`, under its **bare** name; the second concept (`Грамматический падеж`) was dropped |

**The floor is 9.** A change that drops below it — or that trades an under-extraction for a piece of
junk — regresses the skill, whatever the fixture count says.

### What the measurement earned (it is not ceremony)

Three defects in the SKILL were found **only** by running it on a weak model:

1. **A rule that read "extract only what the source EXPLAINS"** made Haiku return `[]` on an incident
   report — because incident reports *use* their vocabulary without defining it. Those are exactly
   the notes the rail exists for. Fixed: *the source does not have to define the term; the definition
   is what you ADD.*
2. **Loosening that rule then caused over-extraction** (6 concepts where 2 belong: `Ретраи`,
   `Обработчик`, `Платёжный шлюз`). The durability bar and the "no definition needed" rule are
   **coupled** — a weak model does not hold the balance a strong one holds silently. Fixed with the
   **theme-vs-prop** table and a count smell test.
3. **Mechanical traps**: `L12` instead of `L12-L12`, a capitalised slug, a transliterated slug on a
   `preserve-unicode` vault. Each is a one-line clarification a strong model never needed.

### Re-running it

One fresh agent per fixture. Give it: the full `SKILL.md`, the `prepare` envelope
(`slug_strategy`, `known_concepts`), and the source body wrapped in the H-6 sentinel. Collect the
candidates JSON, then grade it through the **real** validators plus this set's census and
`forbidden` lists — never by eye.
