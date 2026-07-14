# TASK 064 — `concept-extraction`: definitions that COMPLEMENT the source, without garbage

## 0. Meta Information

- **Task ID**: 064
- **Slug**: concept-extraction-anti-garbage
- **Origin**: Operator request — *"Создай high graded скилы для skills/concept-extraction. Цель —
  получить определения к ключевым концепциям, которые дополняют исходную страницу без мусорных
  данных"*, plus a follow-up requirement: **"убедись, что скилл будет работать эффективно со слабыми
  моделями"**.
- **Type**: Feature (the missing mechanisms) + Skill/Eval hardening
- **Effort**: M
- **Schema**: **zero DDL** (`user_version` 7). No new columns, no new indexes.
- **Depends on**: TASK 003 (v3.1 rail), TASK 047 (mentions ledger), TASK 063 (the sibling rail whose
  anti-fabrication mechanisms this task PORTS).

---

## 1. The problem, stated mechanically

**`wiki-extract-concepts` is the only extraction rail in the repo where fabrication is the cheapest
path to a green run.** This is not an interpretation; it is three lines of code:

| # | mechanism | consequence |
|---|---|---|
| 1 | `_validation.py:67` — `_CANDIDATE_COUNT_MIN = 1`, checked with **no empty short-circuit** anywhere on the apply path | an honest `[]` on a source with no concepts is **exit 4**. The model's only green route is to **invent one**. |
| 2 | `skills/concept-extraction/SKILL.md` — *"Identify **3-10** key concepts"*, frozen behind a "DO NOT REWORD" banner | a **quota with a floor of three**, stacked on top of (1). |
| 3 | nothing anywhere checks whether a concept is **worth a page**, or whether its definition **says anything** | `definition: ""` and `definition == source_quote` are both **ACCEPTED** today. |

The sibling rail **diagnosed this file by name and refused to clone it**
(`wiki_extract_decisions/__init__.py:138-143`):

> `CANDIDATE_COUNT_MIN = 0` — *"The precedent (`wiki_extract_concepts._validation._CANDIDATE_COUNT_MIN`)
> is 1; cloning it here would make 'no decisions in this note' an exit-4 failure and **hand the model a
> reason to fabricate one**."*

It routed around the defect and **never came back to fix it.** That is this project's signature
failure mode — the unenumerated surface — recurring inside the machinery written to prevent it.

### 1.1 The damage is measured, not hypothesised (operator's live vault, 720 concept pages)

| class | real pages the current contract minted |
|---|---|
| UI chrome | `тултип`, `hex-код-цвета`, `индикатор-прогресса`, `текстовый-виджет` — all from **one** Dune tutorial |
| Language / tool primitives | `coalesce`, `left-join`, `row_number`, `group-by`, `having` — knowledge *of SQL*, not of the domain |
| Schema identifiers | `block_number`, `prices-usd`, `erc20_ethereum-evt_transfer` |
| **People** | `уоррен-баффет`, `гарри-марковиц`, `хейли`, `hassan-и-de-filippi` (12+) — the operator's standing rule already forbids these |
| **Permanent graph splits** | `виталик-бутерин`/`vitalik-buterin` · `сатоши-накамото`/`сатоси-накамото` · `бессрочный-фьючерс`/`бессрочные-фьючерсы` · `eth`/`ethereum-eth` · two CPPI pages created **the same day** |

`wiki-lint --strict` is **green** over all of it. Its only duplicate check is *exact-slug,
**cross**-vault, severity `info`* — it catches **0 of the 5** splits. And `coalesce.md` has since
accreted **six** inbound mentions: the TASK-047 derived ledger makes junk look well-connected and
important, and `wiki-query` will cite it as knowledge. **Garbage here compounds.**

### 1.2 Three holes that make the existing guarantees hollow

- **The verbatim-quote receipt is forgeable.** `_validation.py:316` is a bare substring test with **no
  minimum length**: `"source_quote": "и"` grounds against any Russian body.
- **The refusal message teaches the bypass.** `_validation.py:322` ends with *"(set
  `WIKI_EXTRACT_NO_QUOTE_CHECK=1` to skip)"* — a fabrication tutorial delivered to the model at the
  exact moment it is stuck. The env var is read with bare truthiness, so `=0` and `=false` **also**
  disable the check.
- **`source_span` is fiction.** Shape-validated three times, verified against the body **zero** times.
  `L9999-L9999` on a 3-line body is accepted at **exit 0** and written into
  `page_entity_refs.line_start/line_end` as provenance.

### 1.3 Why the weak-model requirement makes this urgent, not cosmetic

A small model obeys a quota **more** literally than a large one. On a thin source, a strong model
argues with the instruction and emits two concepts; a weak model dutifully pads to three. **Prose in a
SKILL cannot fix a mechanism that pays for invention.** Per `skills/wiki-import/evals/README.md:41-45`
— *"a strong model's priors can mask weak skill text"* — the skill must therefore be **measured on a
weak model**, not asserted to work on one.

---

## 2. Requirements Traceability Matrix

| ID | Requirement | Verified by |
|---|---|---|
| **R-064-1** | An empty extraction is a **SUCCESS** — `[]` ⇒ `action: no_candidates`, exit 0, and it mutates nothing but `source_state` (the existing sources' mention ledgers survive). | `tests/test_extract_concepts_gates.py` (end-to-end through `main()`) · eval fixture **02** |
| **R-064-2** | The definition must **complement** the source: never empty, never a copy of the quote, never markdown. | `FIELD_TOO_SHORT` · `DEFINITION_IS_QUOTE` · `DEFINITION_NOT_PROSE` · fixture **06** |
| **R-064-3** | The verbatim-quote receipt is **load-bearing**: min length enforced, no env-var escape hatch, and **no refusal reason may name a bypass**. | `FIELD_QUOTE_NOT_IN_BODY` · fixture **07** · a test asserting no env var appears in any reason string |
| **R-064-4** | A **person** is never a concept on this rail. | `ENTITY_TYPE_NOT_ALLOWED` · fixture **04** |
| **R-064-5** | A near-duplicate of an existing concept is **refused with its nearest slugs**, so the repair turns a `create` into a `mention`. | `NEAR_DUPLICATE_SLUG` · fixture **05** · a test that **re-measures** the cutoff on the real live pairs |
| **R-064-6** | Two candidates may never become one file. | `IN_BATCH_SLUG_COLLISION` · fixture **09** |
| **R-064-7** | The rail **never overwrites** an existing concept page (today: data loss reported as success). The TASK-053/R3 ghost-row self-heal survives. | `CONCEPT_PAGE_EXISTS` + classification change · regression test |
| **R-064-8** | The slug is **derived by the layout**, not chosen by the model; `prepare` **emits `slug_strategy`**. | `SLUG_NOT_DERIVED_FROM_NAME` · fixture **08** (tri-layout) |
| **R-064-9** | `source_span` is **verified against the body**, and the line-origin convention is **stated** (L1 = the file's first line). | `SOURCE_SPAN_OUT_OF_RANGE` / `_QUOTE_MISMATCH` · fixture **10** |
| **R-064-10** | The rail refuses to write concept pages a layout **cannot see**. | `LAYOUT_CANNOT_INDEX_CONCEPTS` (port of the TASK-063 G4 preflight) |
| **R-064-11** | Every refusal is **zero-file, exit 4**, and the batch is atomic. | a test asserting no `_concepts/*.md` and no DB open on every refusal path |
| **R-064-12** | The SKILL is a **deterministic procedure a weak model can execute**, and it is **honest** about the three rules no mechanism backs. | eval fixtures **01/02/03/11** (census-graded) + **a measured Haiku 4.5 run** |
| **R-064-13** | Every rule the SKILL teaches has a fixture; every fixture has a `why` naming the failure mode it guards. | `tests/test_concept_extraction_evals.py` (globbed population, `why` length asserted) |

### The honesty ledger (R-064-12) — rules with **no** mechanism behind them

These three cannot be enforced by any validator, and the SKILL must say so **in those words**:

| claim | backed by |
|---|---|
| "Only durable domain concepts earn a page." | **NOTHING.** The SKILL is the only gate. (`тултип` passes every mechanical check.) |
| "The definition must be true, not merely well-formed." | **NOTHING.** A confident tautology is lint-green, FTS-indexed, and cited. |
| "You did not drop the concept that mattered." | **NOTHING.** No mechanism counts what was left behind. |

---

## 3. Scope

**In scope**: `scripts/wiki_skills/wiki_extract_concepts/` (the gates + the `prepare` envelope);
`skills/concept-extraction/SKILL.md` (the REASON contract); `skills/concept-extraction/evals/` (the
graded set); `tests/` (the gate suite + the eval runner).

**Out of scope, tracked**: the `wiki-lint` near-duplicate rule that would surface the **existing** 720-page
corpus (the gate above only protects the future — `wiki-merge` still has no work queue); the
`wiki-import` article-grammar person leak; back-filling `entities.definition` so a definition is
inspectable at all.

---

## 4. Non-goals

- No DDL. No new columns, no new indexes (P-5).
- No `import anthropic` (Decision-17). This is a **contract**, not a call.
- No change to the karpathy byte-identity anchor: `identity` imposes **no** slug derivation, and
  R-064-8 must not pretend otherwise.
