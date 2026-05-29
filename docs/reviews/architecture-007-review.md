# Architecture Review — TASK 007 (`wiki-query` RAG layer / Epic 7 R-6)

- **Date:** 2026-05-29
- **Reviewer:** Architecture Reviewer (Architecture→Planning gate, VDD mode)
- **Status:** ✅ **APPROVED WITH COMMENTS** (0 CRITICAL / 2 MAJOR / 4 MINOR) — all comments resolved in the architecture (see Resolution Log).
- **Checklist:** `architecture-review-checklist` v1.1 + anti-hallucination grounded-fact audit against schema/code ground truth.

## General Assessment

Strong, well-grounded design that correctly inherits the shipped
`wiki-extract-concepts` Decision-17 `prepare`/`apply` split and reuses the
`wiki-search` retrieval chain rather than reinventing it. **Every grounded fact
verified TRUE against the repo.** The **zero-DDL claim is correct**:
`pages.type` admits `'query'` (`sql/wiki-index-v2.sql:163`),
`page_entity_refs.ref_type` admits `'cited'` (`:195`), `log_events.event_type`
admits `'query'` (`:227`), `source_state` is the generic
`(vault_id, source_kind, scope, key)` table (`:341`), `user_version = 4`
(`:452`) stays put, and the composite PK (`:201`) permits the dual
`cited`+`mentioned` coexistence the design relies on. Security posture sound
(grounding in Python, `_sanitize_markdown_text` egress, H-6 prompt-armor,
atomic-write/`O_NOFOLLOW` reuse, CWE-117/209 envelope, H-PERF-3/P-8 manifest
self-index path explicitly banned). Scope cleanly fenced to R-6 (no R-7/R-8
leakage). No CRITICAL — the round-1 task-review CRITICAL (durability read-side)
is correctly designed via the mandatory R-6.5e. The two MAJORs are load-bearing
*mechanism* gaps in R-6.5e (now fixed) that the planner must not have to
rediscover at TDD time.

## Comments

### 🟡 MAJOR

**M-1 — `cited` refs land in the SAME `page_entity_refs` table that reindex
Step 2 rebuilds via delete-all-then-insert `replace_refs`; the "exactly mirroring
R-5.3" analogy breaks here.** R-5.3 mirrors `aliases:` into a *separate* table
(`entity_aliases`); R-6.5e's `cited` refs collide with the body-wikilink path.
`replace_refs` does `DELETE … WHERE (vault_id, page_slug, page_project)` then
insert (`sqlite_repository.py:381-399`), so a second `replace_refs` (or a write
before Step 2's) would clobber the body-`mentioned` refs. **Fix:** the R-6.5e
branch must **union the `cited` `PageRef`s into the page's `out.refs` set before
the single Step-2 `replace_refs` call**; qualify the R-5.3 analogy (table-separated
mirror vs same-table merge).

**M-2 — R-6.5e phase-ordering vs Step 2.5 (AM-3) ref-canonicalization
unspecified; `cited`-ref AM-3 participation undecided.** Step 2.5
(`reindex.py:372-409`) re-points every ref's `entity_slug` through the alias map.
`cited` refs written in Step 2 will be canonicalized too (desirable — a
merged-away cited target still resolves). AM-3 rewrites `entity_slug` only, never
`ref_type`, so UC-20's "must not degrade to `mentioned`" holds — but the design
should *say so*. **Fix:** state the phase order (Step 2 union → Step 2.5
canonicalize, ref_type preserved → Step 3 recompute) and confirm `cited` refs
participate in AM-3.

### 🟢 MINOR

- **m-1 — Q-A6 (idempotency hash content):** commit the binding default
  (`sha256(question ‖ ordered retrieved project/slug set)`) into the contract so
  Planning decomposes R-6.6 against a concrete shape.
- **m-2 — `cited` ref `trust_level` unspecified:** decide (recommend `'medium'`
  — rides an LLM-synthesised answer).
- **m-3 — `source_quote`/`line_start`/`line_end` for a `cited` ref undefined:**
  state they are `NULL` (no body line for a frontmatter `cites:` entry).
- **m-4 — verification-map UC-20 "RED until R-6.5e lands":** test-state phrasing
  doesn't belong in the living Verification Map; trim to coverage language.

## Checklist Confirmations (no findings)

Index-Mode integrity (~218-line index, 5 chunks resolve, updated in place, no
snapshot); traceability (UC-16..UC-21 + R-6.1..R-6.7 + R-6.5e all map; no
contradiction with concept-extractor/entity-resolver sections); security
(H-6 + grounding-in-Python + `project/slug` key + no-raw-SQL DAL methods);
scalability (direct self-index, bounded alias expansion + `cites:` parse);
YAGNI/Decision-17 (scope fenced, prepare/apply consistent, query pages never
create entities C-10). ✅

## Resolution Log (architecture rev 2 — all comments folded in)

- **M-1 → FIXED:** data-model.md PageEntityRef "Citation ref" + functional-architecture.md
  R-6.5e Function + RAG §D8 invariant now specify the `cited` refs are **unioned
  into the page's single Step-2 `replace_refs` ref-set** (never a second
  `replace_refs`), with `replace_refs`'s delete-all semantics called out; the
  "exactly mirroring R-5.3" claim is qualified (same-table merge vs table-separated
  mirror).
- **M-2 → FIXED:** data-model.md adds a "Reindex phase order for query pages"
  bullet (Step 2 union → Step 2.5 AM-3 canonicalize `cited` targets, `ref_type`
  preserved → Step 3 recompute); ARCHITECTURE.md Q-A9 records the resolution.
- **m-1 → FIXED:** data-model.md SourceState rule + ARCHITECTURE.md Q-A6 commit
  the binding hash-content default.
- **m-2 → FIXED:** `cited` ref `trust_level='medium'` stated in PageEntityRef.
- **m-3 → FIXED:** `line_start`/`line_end`/`source_quote` = `NULL` for `cited`
  refs stated in PageEntityRef.
- **m-4 → FIXED:** verification-map.md UC-20 row trimmed to coverage language.

## Final Recommendation

**APPROVED — proceed to Planning.** No CRITICAL/BLOCKING; the zero-DDL claim and
the durability spine are sound. M-1/M-2 (the load-bearing R-6.5e mechanism:
single-`replace_refs` union + Step-2/Step-2.5 phase order) and the four minors
have been folded into the architecture in place, so R-6.5e/R-6.6 can be
decomposed against a pinned mechanism. Carry Q-A7 (cites id format → `project/slug`),
Q-A8 (body citation rendering), and the residual Q-A9 sub-choice into Planning as
the open design points.
