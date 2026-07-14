# PLAN 065 — R-23 Phase A + DF-064-3

**Spec**: `docs/TASK.md`.

## What shipped

| # | change | file |
|---|---|---|
| 1 | `definition_from_concept_body` — **the ONE parser** both sides of the round-trip use | `wiki_skills/_common.py` |
| 2 | DAL: `upsert_entity(..., definition=None)` — additive, INSERT + ON CONFLICT | `wiki_index/repository.py`, `sqlite_repository/_entities.py` |
| 3 | **Write**: `upsert_extracted_entity` stores the **SANITIZED** definition — the bytes the *page* got, not the bytes the model sent | `wiki_extract_concepts/_db.py` |
| 4 | **Read back**: `reindex_full` parses it out of `out.body_text` (the RAW markdown — *not* `page.body_excerpt`, which is FTS-normalised) | `wiki_index/reindex.py` |
| 5 | **DF-064-3**: `layout_derives_slugs` + `mint_concept_slug` — the gate's question and the producer's question, split | `wiki_extract_concepts/_gates.py`, `wiki_import_article/_authoring.py` |

## The gate (R-065-1) — and the mutations that prove it is not theatre

`tests/test_definition_projection.py` (9 tests):

| mutation | result |
|---|---|
| the writer stores the **raw** candidate instead of the sanitized text | **RED** (1 test) |
| `reindex` stops reading the definition back | **RED** (3 tests) |

Both are the *plausible* implementations. Either would have shipped green without this gate, because
each side is internally consistent — the divergence only appears when the two are made to meet.

## Verification

`2838 passed, 14 skipped` (+9) · `mypy --strict scripts/`: clean.

DF-064-3 verified on the issue's own reproduction: under `identity`, `derive_concept_slug` → `None`
for every name (**correct** — there is no rule to check against) while `mint_concept_slug` yields
`sharpe-ratio` / `diversification` / `виталик-бутерин`.

## The payoff, demonstrated

A definition-quality sweep **in SQL** — impossible before, because the column was NULL for every
row. On a 4-page corpus it correctly flagged the stub (`тултип`, 1 content word).

**And it missed the tautology** («Синергия — это когда есть синергия и всё работает вместе»), because
a naive stop-list lacks `работает`/`вместе`. That miss is **the argument for the Phase A / Phase B
split**, not a defect in Phase A: the projection is exact and gated; the *verdicts* are a threshold
decision that must be measured against a false-positive population first. Shipping them together
would have made a regression un-attributable — and would have repeated the 0.88 near-duplicate
mistake in a new unit.

## Next

**R-23 Phase B** — `wiki-health definitions` (tautology · stub · source-local deixis), with a
measured FP population as the entry condition, not an afterthought. Prototype:
`tests/test_concept_extraction_evals.py::_is_tautology`.
