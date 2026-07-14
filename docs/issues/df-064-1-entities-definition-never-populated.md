---
id: DF-064-1
type: known-issue
status: open
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

- **Fix sketch** (zero-DDL — the column already exists):
  1. `upsert_extracted_entity` writes `definition` from the candidate.
  2. `reindex._entity_from_concept_page` reads the body's first paragraph back (the page shape is
     fixed and byte-stable), so `wiki-reindex --full` reproduces it — the Class-B rebuildability
     gate (ADR-002 §D8) must stay green.
  3. Then, and only then, a `wiki-health` check becomes possible: *tautology* (definition's content
     words ⊆ its own name), *stub* (under N words), *deixis* («те 20%, о которых договорились»).
     `tests/test_concept_extraction_evals.py::_is_tautology` is a working prototype of the first —
     it currently lives in the eval runner because the DB cannot answer the question.

- **Blocks**: ROADMAP **R-23** (concept-definition health).
