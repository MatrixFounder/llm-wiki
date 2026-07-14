# TASK 065 — R-23 Phase A: the concept `definition` becomes inspectable · DF-064-3

## 0. Meta Information

- **Task ID**: 065
- **Slug**: definition-projection-and-slug-sentinel
- **Origin**: the two TASK-064 follow-ups the operator chose to pair — the quick isolated fix
  (**DF-064-3**) and the one that unlocks a capability (**DF-064-1** → ROADMAP **R-23**).
- **Type**: Bugfix (DF-064-3) + Enabler (R-23 Phase A)
- **Effort**: S
- **Schema**: **zero DDL** (`user_version` 7). `entities.definition` already exists — this closes a
  **projection** gap, not a schema gap.

---

## 1. The problem

### 1.1 DF-064-1 — the column nothing ever wrote

`entities.definition` has been in the schema since v2 and was **never written**. It stayed NULL
forever, so **no SQL query, no `wiki-lint` rule and no `wiki-health` check could inspect the one
field a concept page exists to carry** — while `wiki-search` retrieved it from FTS and `wiki-query`
**cited it as knowledge**. The `entity_cards` VIEW already selects `definition AS tldr`: it was
serving NULL to every consumer.

The definition is also **write-once** (the first source to mention a concept owns it forever) and
**un-improvable**. TASK 064 shipped every gate that can run at *write* time and then had to write
into the SKILL's honesty ledger, in those words, that *"is this definition TRUE?"* has **no
mechanism and cannot have one**. That admission is a direct consequence of this defect:
**detection is impossible while the column is dead.**

### 1.2 DF-064-3 — one function answering two questions

`derive_concept_slug` returns `None` for two unrelated reasons: *"this layout declares no name→slug
rule"* (`identity`) and *"the derivation is degenerate"*. `wiki-import`'s `derive_candidates` read
the first as the second and skipped the candidate as `invalid-slug` — so a caller passing
`layout.slug_strategy` straight through would file **zero concepts on every karpathy vault, at exit
0**, reporting `invalid-slug` for perfectly valid names. It never fired only because the *caller*
happened to substitute `preserve-unicode` first — i.e. a fix the **next** caller would not inherit.

---

## 2. Requirements Traceability Matrix

| ID | Requirement | Verified by |
|---|---|---|
| **R-065-1** | ★ The definition **round-trips byte-identically**: `apply` writes it, `wiki-reindex --full` rebuilds it from the markdown **alone**, and the two agree. | `tests/test_definition_projection.py::test_the_definition_ROUND_TRIPS_byte_identically` — **mutation-tested both directions** |
| **R-065-2** | Class A is the source of truth: the definition is read from the page **body** (raw markdown), not re-derived from the candidate, so a **hand-edited** definition is the one that lands. | the parser's parametrised cases (no H1 · no AUTO block · multi-paragraph) |
| **R-065-3** | A full rebuild **alone** populates the column — the existing corpus becomes inspectable with no re-extraction, only re-indexing. | `test_a_full_rebuild_ALONE_populates_the_definition` |
| **R-065-4** | The derived mentions ledger (Class B) never leaks into the definition. | `test_the_AUTO_block_is_NOT_swallowed_into_the_definition` |
| **R-065-5** | The gate and the producer ask **different questions**, and neither can be mistaken for the other. | `layout_derives_slugs` / `mint_concept_slug`; `identity` now mints valid slugs |

### ★ The acceptance criterion is the ROUND-TRIP, not the column

`write_concept_page` puts the **sanitized** definition into the body (markdown-actives escaped:
`*args` → `\*args`). The rebuilder reads **that** back. A writer storing the **raw** candidate would
round-trip to a *different value* — **and every existing test would still pass**, because each side
is internally consistent. The first `wiki-reindex --full` would then silently **change** the column,
and ADR-002 §D8 (*Class B is a 100%-rebuildable cache of Class A*) would be **false**.

That is why the gate's fixture definition deliberately begins with a markdown-active character, and
why "the column is populated" was never allowed to be the exit criterion.

---

## 3. Scope

**In**: `wiki_skills/_common.py` (the shared parser) · `wiki_index/repository.py` +
`sqlite_repository/_entities.py` (DAL) · `wiki_extract_concepts/_db.py` (write) ·
`wiki_index/reindex.py` (read-back) · `wiki_extract_concepts/_gates.py` +
`wiki_import_article/_authoring.py` (DF-064-3) · `tests/test_definition_projection.py`.

**Out, and deliberately so — R-23 Phase B (`wiki-health definitions`)**. Detection is now
*possible*; it is not yet *right*. A first sweep flagged the stub (`тултип`) but **missed the
tautology** («Синергия — это когда есть синергия…») because a naive stop-list lacks
`работает`/`вместе`. That is the same class of decision that produced the 0.88 near-duplicate cutoff
— **a threshold calibrated on the examples that motivated it is not calibrated.** Phase B must
measure a false-positive population before it ships a verdict, and bundling that decision with a
projection change would make a regression un-attributable.

---

## 4. Non-goals

- No DDL. No new columns.
- No behaviour change to what the extractor *writes to disk* — only to what the index *records
  about it*.
