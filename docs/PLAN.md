# PLAN 064 — `concept-extraction`: definitions that COMPLEMENT the source, without garbage

**Spec**: `docs/TASK.md`.

## What shipped

### 1. The mechanisms (`scripts/wiki_skills/wiki_extract_concepts/`)

| # | gate | code |
|---|---|---|
| **G0** | ★ **an empty extraction is a SUCCESS** — `_CANDIDATE_COUNT_MIN: 1 → 0` + an `action: no_candidates` exit-0 path that mutates nothing but `source_state` | — |
| G1 | the definition must **complement**: never empty, never a copy of the quote, never markdown | `FIELD_TOO_SHORT` · `DEFINITION_IS_QUOTE` · `DEFINITION_NOT_PROSE` |
| G2/G3 | the quote receipt is **load-bearing**: a word floor, NFC-normalised compare, and **the env-var escape hatch DELETED** — along with the refusal string that taught it | `FIELD_QUOTE_NOT_IN_BODY` |
| G4 | a **person** is not a concept — on **both** writers (the article grammar leaked for a year) | `ENTITY_TYPE_NOT_ALLOWED` |
| G5 | near-duplicates — **ADVISORY** (see the reversal below), surfaced in `prepare` **and** `wiki-lint` | warning |
| G6 | two candidates may never become one file | `IN_BATCH_SLUG_COLLISION` |
| G7 | never overwrite an existing concept page (was: **data loss reported as success**) | `CONCEPT_PAGE_EXISTS` |
| G8 | the slug is **derived by the layout**; `prepare` now emits `slug_strategy` | `SLUG_NOT_DERIVED_FROM_NAME` |
| G9 | `source_span` is **verified against the body**; L1 = the file's first line | `SOURCE_SPAN_OUT_OF_RANGE` · `SOURCE_SPAN_QUOTE_MISMATCH` |
| G10 | refuse to write pages a layout **cannot see** | `LAYOUT_CANNOT_INDEX_CONCEPTS` |
| G11 | a concept may not **evict the source note** from the index | `SLUG_COLLIDES_WITH_PAGE` |

### 2. The contract (`skills/concept-extraction/SKILL.md`)

Rewritten as a **deterministic procedure a weak model can execute**: the three durability
questions, the theme-vs-prop table, the "true with the source deleted" test, the named junk
classes, a self-check, the H-6 sentinel armor — and an **honesty ledger** naming the three rules
no mechanism backs.

### 3. The evals (`skills/concept-extraction/evals/`, `tests/test_concept_extraction_evals.py`)

11 graded fixtures × 3 layouts, each with a counterexample and a `why`. Counterexamples the code
**accepts** are marked `graded_by_census_only` — the set never pretends a mechanism exists.

### 4. The weak-model measurement

**Haiku 4.5: 9/11** (floor recorded in `evals/README.md`). Both misses are under-extraction; zero
junk, zero invalid payloads.

---

## ★ THE TWO REVERSALS — both found by adversarial review, both after "green"

### R1 — the gates BROKE `wiki-import`, and 2812 passing tests could not see it

`wiki-import` has no concept writer: it **shells out** to `wiki-extract-concepts apply`. The new
floors and the `person` refusal rejected its payloads — **zero concept pages, exit 6** — while all
three import test modules **monkeypatch `_file_concepts`**. The suite was green over a broken
shipped path.

**This is the project's signature failure mode, reproduced inside the machinery written against
it.** Fixed at the producer (`derive_candidates` now drops `person` on **all** grammars, emits
multi-line-aware spans, and routes floor violations into `skipped[]` instead of failing the batch)
and pinned by `tests/test_import_concepts_contract.py` — a **real subprocess, no stubs**, plus
`test_the_stub_free_seam_is_real`, which fails if anyone re-introduces the stub.

### R2 — the near-duplicate gate was **anti-correlated with meaning**

Shipped as a refusal at similarity ≥ 0.88. Re-measured: `type-i-error`/`type-ii-error` scores
**0.960** — a *harder* duplicate than the live pair `бессрочный-фьючерс`/`бессрочные-фьючерсы`
(0.927) it was built for. The bands overlap completely; **no scalar cutoff exists.** And its
refusal *instructed* the model to file `decentralized-exchange` as a mention of
`centralized-exchange` — **the anti-duplicate gate manufactured false knowledge.**

Demoted to an advisory, surfaced in `prepare` (where it is actionable) and in `wiki-lint` (so the
existing 720-page corpus is finally a `wiki-merge` work queue). The real defence moved to SKILL
STEP 3, and the honesty ledger says so.

---

## Gates

`2829 passed, 14 skipped` · `mypy --strict scripts/`: clean · mutation-tested (6 mutations, each
re-introducing an original defect — all caught red).

## Deferred

- `entities.definition` is never populated, so **no lint rule or health check can ever inspect a
  definition** (it is reachable only via FTS, which means a bad one is *retrieved and cited*).
- `wiki-lint`'s near-duplicate scan is O(n²) — 0.6 s at 720 concepts, ~32 s at 5 000.
- `derive_candidates` treats `derive_concept_slug`'s `identity` sentinel as "invalid slug"; latent
  only (the shipped caller substitutes `preserve-unicode`), but a footgun for a future one.
