---
id: DF-064-1
type: known-issue
status: fixed
opened_at: 2026-07-14
category: class-b-integrity
severity: SEV-2
slug: df-064-1-entities-definition-never-populated
---

# `entities.definition` is never populated — so a concept's definition is invisible to every automated check, while `wiki-query` cites it as knowledge

- **Symptom**: `entities.definition TEXT` exists in the schema (`sql/wiki-index-v2.sql`) and is
  **never written**. `upsert_entity` has no `definition` parameter
  (`wiki_extract_concepts/_db.py`), and `wiki-reindex --full` rebuilds entity rows from
  `_concepts/` **frontmatter** — where the definition does not live (it is the page **body**).
  The column is **NULL forever**.

  Consequence: **no SQL query, no `wiki-lint` rule, and no `wiki-health` check can ever inspect a
  concept definition.** It is reachable only via FTS over the page body — which means a bad
  definition does not sit quietly. It is **retrieved by `wiki-search` and cited by `wiki-query` as
  knowledge**, then re-summarised downstream. Garbage here **compounds**.

- **Why this matters more than it looks**: the definition **IS** the concept page
  (`_pages.py` renders the body as `# {name}\n\n{definition}\n\n{mentions}`), and it is
  **permanent** — the first source to mention a concept owns its definition forever; a `mention`
  discards the candidate's `name`/`definition` entirely. So the one field the whole rail exists to
  produce is simultaneously (a) write-once, (b) un-improvable, and (c) **un-inspectable**.

- **What TASK 064 could and could not do about it**: the enforceable slice shipped —
  `DEFINITION_IS_QUOTE`, `DEFINITION_NOT_PROSE`, and a word floor refuse a definition that is
  empty, a copy of the quote, or markdown. But *"is this definition TRUE, or merely well-formed?"*
  has **no mechanism and cannot have one at write time**. `skills/concept-extraction/SKILL.md`'s
  honesty ledger says so in those words. **Detection is impossible while the column is dead**, so
  prevention (the SKILL) is currently the only lever — which is precisely the posture ADR-006
  exists to move away from.

- **Root cause**: the Class-A → Class-B projection for `_concepts/` pages carries frontmatter only.
  The body — the payload — is projected into FTS but not into a structured column. A concept page's
  most load-bearing field never crosses the A→B boundary as data.

- **FIXED (TASK 065 — ROADMAP R-23 Phase A)**, zero-DDL. The column was never a schema gap; it was
  a **projection** gap, and it is now closed on both sides:

  1. **Write** — `upsert_extracted_entity` stores the definition, and the DAL (`upsert_entity`)
     carries it.
  2. **Read back** — `reindex_full` parses it out of the page **body** (`out.body_text`, the RAW
     markdown — *not* `page.body_excerpt`, which is the FTS-normalised text). **Class A is the
     source of truth**, so a definition an operator has hand-edited is the one that lands.
  3. **One parser, shared** — `_common.definition_from_concept_body`, so the writer and the
     rebuilder cannot drift into two readings of the same page.

- **★ THE TRAP, AND WHY THE ACCEPTANCE CRITERION IS THE ROUND-TRIP, NOT THE COLUMN.**
  `write_concept_page` puts the **sanitized** definition into the body (markdown-actives are
  escaped: `*args` → `\*args`). The rebuilder reads *that* back. A writer storing the **raw**
  candidate would round-trip to a **different value** — and every existing test would still pass,
  because each side is internally consistent. The first `wiki-reindex --full` would then silently
  **change** the column, and ADR-002 §D8 (Class B is a 100%-rebuildable cache of Class A) would be
  false. So the gate is `tests/test_definition_projection.py::
  test_the_definition_ROUND_TRIPS_byte_identically`, whose fixture definition deliberately begins
  with a markdown-active character. **Mutation-tested both ways** (writer stores raw → RED;
  rebuilder stops reading → RED).

- **Still open — Phase B (`wiki-health definitions`).** Detection is now *possible*; it is not yet
  *shipped*, and the reason is deliberate. A first sweep over a 4-page corpus already flagged the
  stub (`тултип` — 1 content word) but **missed the tautology** («Синергия — это когда есть
  синергия и всё работает вместе») because a naive stop-list does not contain `работает`/`вместе`.
  That is precisely the class of decision that produced the 0.88 near-duplicate cutoff — a
  threshold calibrated on the examples that motivated it. **Phase B must measure a false-positive
  population before it ships a verdict.** Tracked in ROADMAP **R-23**.
