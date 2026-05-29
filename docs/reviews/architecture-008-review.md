# Architecture Review — TASK 008 `wiki-verify-multi` (R-8)

**Date:** 2026-05-29
**Reviewer:** architecture-reviewer (VDD gate, independent subagent)
**Status:** APPROVED WITH COMMENTS → all comments resolved in place (see Dispositions)

## General Assessment

A high-quality, deeply-grounded design that correctly reuses the TASK 007
`wiki-query` machinery (Decision-17 `prepare`/`apply` split, `source_state`
idempotency, direct-DAL self-index, the egress sanitiser, and the R-6.5e reindex
read-side) rather than reinventing it. Every load-bearing grounded fact was
independently confirmed in `sql/wiki-index-v2.sql` and
`scripts/wiki_index/{reindex,layout,normalization,repository,models}.py`:

- `pages.type` (162-164) lacks `verification`; `ref_type` (194-196) lacks
  `verifies`; `event_type` (225-230) lacks `verify`; `index_meta` (393-402)
  filters `type IN ('summary','concept','query')`; `pages_fts_*` (371-386) index
  **every** row with no `type` filter; `PRAGMA user_version = 4` (452). → v4→v5
  DDL claim + "FTS-searchable automatically" claim both correct.
- `Page.file_path` (models.py:96) is schema `NOT NULL` (sql:166) → populated for
  all page types → the layout-agnostic source-access claim is sound.
- Composite PK `(vault_id, page_slug, page_project, entity_slug, ref_type)`
  (sql:201) makes `verifies` + `cited` + `mentioned` to the same target
  collision-free; no-FK-on-`entity_slug` (sql:203) means a verdict→query page→page
  edge is structurally identical to TASK 007's `cited` page-ref precedent.
- Entity-registration in `reindex_full` is gated on `rel_parts ∩ {_concepts,
  _entities}` (reindex.py:367) → a `_verifications/` page **never** upserts an
  `entities` row → C-10 holds structurally, not by convention.

Design is internally consistent across all five chunks; RTM traceability complete
(every UC-22..28 + R-8.1..R-8.10 + C-8/NFR-7 maps to a section); migration story
matches the ADR-002 §D8 v2→v3→v4 precedent; security envelope mirrors `wiki-query`.

## Findings

### 🔴 CRITICAL
None. No data-model flaw, security hole, or incompatibility. Schema deltas
correct + minimal; migration is the documented no-ALTER rebuild; multi-vault
scoping and C-10 structurally enforced.

### 🟡 MAJOR

**M-1 — `TYPE_MAPPING["verification"]` / `_PATH_TYPE_FALLBACK` (the load-bearing
half of R-8.5e) was absent from the architecture chunks. [FIXED]** Same shape as
the TASK 007 C-1 "layout.py alone is insufficient" bug: `db_type` is the return
of `normalize_frontmatter`, which raises `UnmappedTypeError` for any `type` not
in `TYPE_MAPPING` (normalization.py:155-159). Without the mapping addition, every
`_verifications/<slug>.md` page is silently swallowed into the reindex `skipped[]`
(reindex.py:245/429-430) — found by `discover_pages` but never **indexed** — so
the `verifies:` read-side never runs and UC-26 §D8 fails before R-8.5e is reached.
The TASK's §1.1 DDL #1 named the fix, but the architecture (the contract Planning
decomposes against) omitted it.
**Disposition — FIXED in place:** added the `normalization.py` addition
(`TYPE_MAPPING["verification"] = ("verification", None)` +
`_PATH_TYPE_FALLBACK[VERIFICATIONS_SUBDIR] = "verification"`) to (a) the
Verification Layer R-8.5e function note, (b) the §D8-durability invariant
(now states the **three-part** `layout.py` + `normalization.py` + `reindex.py`
change must land together), (c) data-model.md §4.4 v4→v5 code-side list (change
#2 of three), and (d) the verification-map R-8.5/R-8.5e rows.

### 🟢 MINOR

**N-1 — ADR-002 §D8 not amended for v4→v5. [FIXED]** Added an "Amendment (TASK
008, schema v4→v5)" block to ADR-002 §D8 mirroring the v3→v4 block, noting this is
the **first amendment relaxing a CHECK enum** and that SQLite cannot ALTER-relax a
CHECK on a populated table → the `CREATE TABLE IF NOT EXISTS` reseed +
`wiki-reindex --full` rebuild is mandatory; the DB stays Class B rebuildable via
the R-8.5e read-side; `source_state` verify-idempotency is Class C.

**N-2 — `question_hash:` frontmatter vs `answer_hash` envelope naming. [FIXED]**
Renamed the verdict-page frontmatter field `question_hash:` → **`answer_hash:`**
(it hashes the answer body, not the question) across the TASK (C-3, R-8.3b) and
the architecture (data-model.md Page rule, functional-architecture.md Outputs).
The `wiki-query` `source_state` `key='question_hash'` is untouched (correct — that
is R-6's key, a different thing).

**N-3 — two-hash separation worth a callout. [FIXED]** Added a "Two distinct
hashes (no conflation)" bullet to the Verification Layer Operational invariants:
`answer_hash = sha256(answer body)` is the TOCTOU guard (`ANSWER_CHANGED`);
`verify_hash = sha256(answer_hash ‖ ordered examined project/slug set)` (Q-008-b)
is the `source_state` idempotency key (`is_unchanged`).

## Adversarial checklist results (all PASS, M-1 now closed)

- **Migration safety:** no-ALTER-relax-CHECK → `CREATE TABLE IF NOT EXISTS` reseed
  + `wiki-reindex --full` is the correct, complete way to add CHECK enum values in
  SQLite; matches v2→v3 (PK) + v3→v4 (generated column) precedent; the
  `test_schema_v4.py` `executescript(_SCHEMA)` reseed pattern confirms the planned
  `test_schema_v5.py`. **PASS.**
- **Durability spine (R-8.5e):** the `_cited_refs_from_frontmatter` →
  `_frontmatter_refs(db_type)` generalisation, unioning into the **single** Step-2
  `replace_refs` in **both** `reindex_full` (349-356) and `reindex_delta`
  (236-243), Step 2.5 (455-492) rewriting `entity_slug` only — mirrors the proven
  R-6.5e pattern; structurally guarantees no `verifies`→`mentioned` degradation
  and no clobber. **PASS** (now unconditional, with M-1's `TYPE_MAPPING` fix).
- **Layout-agnostic (C-8/NFR-7):** reads via `pages.file_path` + `get_page`
  (NOT NULL all types); `_verifications` only in `HOST_ONLY_SUBDIRS`; grep-guard
  forbids `PAGE_SUBDIRS` literals; identical seam to `_queries`. **PASS.**
- **Security:** egress sanitiser, H-6 untrusted bodies, CWE-117/209 envelope,
  `O_NOFOLLOW`/`validate_inside_vault`/atomic-write, `wiki-verify`
  SECURITY-SENSITIVE — no missing control vs precedent; no new surface. **PASS.**
- **Scalability:** `prepare` reads N≤50 cited bodies (bounded); `apply` direct-DAL
  self-index (no manifest N+1); one extra reindex-walk dir (P-2 inherited); R-8.5e
  parse O(1)/page. **PASS.**
- **YAGNI:** dedicated `'verifies'` ref-type justified (the queryable point of
  R-8); optional `cites:` reuses existing machinery (zero new code); Layer-A
  Agent-fanout correctly scoped as *MAY* with the prompt-skill default. **PASS.**
- **Traceability:** complete; no orphan requirement, no uncovered UC. **PASS.**
- **Internal consistency:** `VERDICT_FAIL=6` distinct from 1/2/4; two-hash
  separation clean. **PASS.**

## Final Recommendation

**APPROVED.** The single MAJOR (M-1) and three MINOR items are all resolved in
place by the architect. The design proceeds to **Planning**, which should
decompose against the three-part code-side change (`layout.py` +
`normalization.py` + `reindex.py` read-side) as the durability spine, the v4→v5
schema bead, and the off-by-default `wiki-verify-multi` skill + `wiki-verify`
prompt-contract skill. The `/vdd-start-feature` workflow (Analysis + Architecture)
is complete.
