# Development Plan: TASK 007 — Epic 7 RAG layer entry-point (`wiki-query`, R-6)

> **Status**: DRAFT (2026-05-29) — awaiting plan-reviewer sign-off.
> **Task ID**: 007 / Slug: `wiki-query-rag`
> **Source spec**: [docs/TASK.md](./TASK.md) (RTM R-6.1..R-6.7 + R-6.5e; UC-16..UC-21; Decision Log D-007-1..5; constraints C-1..C-10).
> **Architecture spec**: [docs/ARCHITECTURE.md](./ARCHITECTURE.md) §2 **RAG Query Layer** component + §4 Data Model (query page as first-class compounding `type=query`; `ref_type='cited'` + R-6.5e reindex read-side; `source_state` reuse) + §5 Interfaces — updated in place + reviewed (both gates APPROVED, see [docs/reviews/task-007-review.md](./reviews/task-007-review.md), [docs/reviews/architecture-007-review.md](./reviews/architecture-007-review.md)).
> **Methodology**: **Stub-First (TDD)**, **green-throughout** (every bead boundary keeps `pytest` green + `SQLiteRepository` instantiable + `mypy --strict` clean — ABC abstractmethod + `SQLiteRepository` stub land together). Each code bead lands Phase-1 stubs + RED→GREEN tests before Phase-2 logic; the per-bead split is documented in §3.
> **Predecessors**: R-3 / TASK 003 v3.1 (`wiki-extract-concepts`, the Decision-17 `prepare`/`apply` template) `43812f2`; R-4+R-5 / TASK 005 (`wiki-confirm`/`wiki-alias`/`wiki-merge` + alias-expanded retrieval) `8a6491e`; TASK 006 (schema **v4**) `ba4fa92` = current HEAD.
> **Unblocks**: ROADMAP **R-7** (`wiki-research`) + **R-8** (`wiki-verify-multi`) — both layer on `wiki-query`.
> **Out of scope** (TASK §5 C-4): R-7 (web enrichment) + R-8 (4-critic ensemble) — deferred + gated on this task; vault-wide query batching; embeddings/vector RAG (FTS5 + entity graph only).

---

## 0. Architectural Foundation (Reference)

| Layer | Owns | Class (ADR-002 §D8) |
|---|---|---|
| `_queries/<slug>.md` frontmatter (`type: query`, `question:`, `date:`, `cites: [project/slug,…]`, `tags:[query]`) + sanitised answer body | **Canonical** filed answer + citation list | **Class A** |
| `pages` row (`type='query'`) + `page_entity_refs` (`ref_type='cited'`) + `log_events` (`event_type='query'`) | DB mirror; rebuilt by `wiki-reindex --full` | **Class B** |
| `source_state` (`source_kind='query'`) | Query idempotency (`question_hash`); recomputed on re-query | **Class C** |
| `IndexRepository` (ABC) + `SQLiteRepository` | All read/write SQL; new `check_query_state`/`record_query_state`; reuses `search_pages`/`expand_query_aliases`/`upsert_page`/`replace_refs` | DAL boundary (skills never write raw SQL) |
| `wiki-query` (`prepare`/`apply`) + `wiki-query-synthesis` prompt skill | Thin CLI over the DAL + orchestrator-owned synthesis (Decision-17) | Skill Layer |

**TASK 007 invariants** (carried from the two review gates):
1. **§D8 durability** — the query page + its `cited` refs reconstruct from Class A markdown alone after `wiki-reindex --full` (**UC-20** is the binding gate). This rests on R-6.5e (the reindex read-side) — without it the refs are lost/degraded.
2. **R-6.5e same-table merge, NOT a 2nd `replace_refs` (Arch M-1)** — `cited` refs are **unioned into the page's `out.refs` set before the single Step-2 `replace_refs`** (which is delete-all-then-insert; a second pass would clobber the body-`mentioned` refs).
3. **Reindex phase order (Arch M-2)** — Step 2 (union `cited` into `out.refs`) → Step 2.5 AM-3 (canonicalize `entity_slug` through the alias map; `ref_type` **preserved** → no `cited`→`mentioned` degradation) → Step 3 recompute.
4. **Decision-17** — no LLM call in Python; synthesis is orchestrator-owned via the `wiki-query-synthesis` prompt skill; `wiki-query` is a deterministic `prepare`/`apply` pair.
5. **Grounding enforced in Python** — `prepare` refuses `NO_CONTEXT` below `--min-hits`; `apply` rejects any citation not in the retrieved set (`CITATION_NOT_RETRIEVED`), keyed on the full **`project/slug`** tuple. Never trusted to the LLM.
6. **No H-PERF-3/P-8 N+1** — `apply` self-indexes the one query page via **direct `upsert_page` + `replace_refs` on one connection**, never `index_from_manifest`→`main(argv)`.
7. **Zero schema DDL** — `pages.type='query'`, `ref_type='cited'`, `event_type='query'`, generic `source_state` all pre-exist; `PRAGMA user_version` stays **4**.
8. **Envelope invariant** — CWE-117/209: `{error, field?, reason}` only; never echo the question/answer/citation content.

---

## 1. Task Execution Sequence

### Phase 1 — Durability spine (the load-bearing core)

The §D8 round-trip (UC-20) is the binding acceptance gate, so the spine lands first: `_queries` must be discoverable (007-01) before the reindex read-side (007-02) can round-trip it, and the query-state DAL (007-03) backs idempotency.

- [R-6.5] **007-01** — `layout.py`: add `QUERIES_SUBDIR = "_queries"`; add it to `PAGE_SUBDIRS` (so `discover_pages`/drift/render walk it) **and** `SCAFFOLD_DIRS` (so `wiki-init --scaffold-new` creates it); add `_PATH_TYPE_FALLBACK["_queries"] = "query"` (defensive type inference).
  - Description File: [docs/tasks/task-007-01-layout-queries-subdir.md](./tasks/task-007-01-layout-queries-subdir.md)
  - Priority: Critical (blocks reindex read-side + apply write target) · Dependencies: none · Est: 0.25 day

- [R-6.5e, AM-3] **007-02** — reindex read-side (the §D8 fix): a **type-aware branch in `reindex.py`** that, for a `type=query` page, parses `cites:` frontmatter into `ref_type='cited'` `PageRef`s and **unions them into the page's `out.refs` set before the single Step-2 `replace_refs`** (Arch M-1). Verify Step 2.5 (AM-3) canonicalizes `cited` targets through the alias map with `ref_type` preserved (Arch M-2). Skip-and-report malformed `cites:` entries.
  - Description File: [docs/tasks/task-007-02-reindex-cites-read-side.md](./tasks/task-007-02-reindex-cites-read-side.md)
  - Priority: Critical (durability spine — UC-20 fails without it) · Dependencies: 007-01 · Est: 1 day · **strict-TDD**

- [R-6.6] **007-03** — query-state DAL: `check_query_state(vault_id, query_slug) → str | None` + `record_query_state(vault_id, query_slug, question_hash) → None` — thin typed wrappers over `source_state` (`source_kind='query'`, `scope=query_slug`, `key='question_hash'`). ABC abstractmethod + `SQLiteRepository` impl land together (green-throughout). No raw SQL in skills (NFR-2).
  - Description File: [docs/tasks/task-007-03-query-state-dal.md](./tasks/task-007-03-query-state-dal.md)
  - Priority: Critical (idempotency) · Dependencies: none (`source_state` exists) · Est: 0.5 day

### Phase 2 — Skill (`prepare` / `apply`)

Thin skill over the DAL, modelled on `wiki-extract-concepts`'s two-subcommand shape. Retrieval reuses `wiki-search`'s alias-expanded FTS (extract a shared helper, keep `wiki-search` green — C-6).

- [R-6.1, R-6.7-prepare] **007-04** — `wiki-query prepare` subcommand + `bin/wiki-query` wrapper + argparse (`prepare`/`apply` subparsers; `apply` stubbed). Extract `_expand_query` + the search call into a shared retrieval helper imported by both `wiki_search.py` and `wiki_query.py` (no duplication; `wiki-search` stays byte-identical). Derive `query_slug` (`--slug` else slugified+truncated question), compute `question_hash`, `check_query_state`, emit the retrieval envelope; `--min-hits` (default 1) → `NO_CONTEXT`; `--limit` default 10; scoping flags (`--vaults`/`--types`/`--project`/`--no-expand-aliases`).
  - Description File: [docs/tasks/task-007-04-wiki-query-prepare.md](./tasks/task-007-04-wiki-query-prepare.md)
  - Priority: High · Dependencies: 007-03 · Est: 1 day

- [R-6.3, R-6.7-apply] **007-05** — `wiki-query apply` write-side: re-retrieve + recompute `question_hash`, compare to `--question-hash` (`QUESTION_CHANGED` on mismatch); validate the `--citations` payload ⊆ retrieved hit set keyed on **`project/slug`** (`CITATION_NOT_RETRIEVED`; `INVALID_CITATIONS` on shape); sanitise the answer body via `_sanitize_markdown_text` (lift to `_common.py` for reuse); atomic-write `_queries/<query_slug>.md` (Class A; `O_NOFOLLOW` symlink-refuse + tempfile + content-hash skip; `--force` overrides skip). **Stops at the file write — DB indexing is 007-06.**
  - Description File: [docs/tasks/task-007-05-wiki-query-apply-write.md](./tasks/task-007-05-wiki-query-apply-write.md)
  - Priority: High · Dependencies: 007-04 · Est: 1 day · **strict-TDD** (grounding gate)

- [R-6.4, R-6.6-apply] **007-06** — `wiki-query apply` index-side: self-index the one query page via **direct `upsert_page` (`type=query`) + `replace_refs` (`cited` refs) on a single repo connection** — NOT `index_from_manifest`/`main(argv)` (H-PERF-3); `record_query_state`; append one `query` `log_event` (subject = query_slug). The query page is FTS-searchable immediately after.
  - Description File: [docs/tasks/task-007-06-wiki-query-apply-index.md](./tasks/task-007-06-wiki-query-apply-index.md)
  - Priority: High · Dependencies: 007-05, 007-03, 007-01 · Est: 0.75 day

### Phase 3 — Synthesis contract + skill/command/workflow docs + symlinks

- [R-6.2, C-1] **007-07** — `wiki-query-synthesis` prompt-contract skill (repo-root `skills/wiki-query-synthesis/SKILL.md`, scaffolded via `skill-creator/init_skill.py` per the SKILL CREATION GATE) defining the answer + citations JSON contract, the grounding rule (cite only retrieved hits), and the **H-6 untrusted-retrieved-content** prompt-armor. Plus `skills/wiki-query/SKILL.md` (deterministic-skill subcommand reference), `commands/wiki-query.md`, `workflows/wiki-query.md` (end-to-end recipe), and the `.claude/`/`.agent/` symlink set via `bin/link-*.sh`.
  - Description File: [docs/tasks/task-007-07-synthesis-skill-and-docs.md](./tasks/task-007-07-synthesis-skill-and-docs.md)
  - Priority: Medium · Dependencies: 007-04, 007-05, 007-06 (final CLI surface) · Est: 0.75 day

### Phase 4 — Acceptance + regression + docs

- [UC-20] **007-08** — §D8 durability round-trip acceptance test (the binding gate): file a query page (via `apply`), snapshot the `pages` row + `cited` refs, **delete the DB**, `wiki-reindex --full`, assert the query page is rediscovered as `type=query` and its `cited` refs are reconstructed from `cites:` frontmatter alone — **not** degraded to `mentioned`, not clobbered by the body-wikilink pass.
  - Description File: [docs/tasks/task-007-08-durability-acceptance.md](./tasks/task-007-08-durability-acceptance.md)
  - Priority: Critical (acceptance) · Dependencies: 007-01, 007-02, **007-05** (write-side, to file a page), 007-06 (index-side) · Est: 0.5 day · **strict-TDD**

- [UC-16, UC-17, UC-18, UC-19, UC-21] **007-09** — end-to-end + compounding acceptance: UC-16 (ask→cited answer page); UC-17 (idempotent re-run `is_unchanged`; `--force` re-synthesises); UC-18 (`NO_CONTEXT` on empty/low retrieval, no write); UC-19 (compounding — a `wiki-search` finds the filed query page + the `cited` backlinks exist; `--types` filter); UC-21 (citation ∉ hit set → `CITATION_NOT_RETRIEVED`, nothing written).
  - Description File: [docs/tasks/task-007-09-e2e-compounding-acceptance.md](./tasks/task-007-09-e2e-compounding-acceptance.md)
  - Priority: Critical (acceptance) · Dependencies: 007-04, 007-05, 007-06, 007-08 · Est: 0.75 day

- [all RTM, C-4] **007-10** — regression sweep + docs (acceptance gate): full `pytest tests/` + `mypy --strict scripts/`; ROADMAP **R-6 → DONE** + an explicit **R-7/R-8 hand-off** note (they are unblocked + gated); `docs/ARCHITECTURE.md` status header → SHIPPED; README + any `.AGENTS.md` updates; extend the envelope-never-echoes-content regression suite to the `wiki-query` surfaces (question/answer/citation).
  - Description File: [docs/tasks/task-007-10-regression-and-docs.md](./tasks/task-007-10-regression-and-docs.md)
  - Priority: Critical (acceptance gate) · Dependencies: **all prior** 007-01..007-09 · Est: 0.5 day

---

## 2. Dependency DAG (critical-path view)

```text
   007-01 layout (_queries) ─┬─► 007-02 reindex cites→cited read-side (R-6.5e) ─┐
   (R-6.5)                   │   (AM-3 phase order)                              │
                             └─────────────────────────────────────────────────┤
   007-03 query-state DAL (R-6.6) ──► 007-04 prepare (R-6.1) ─► 007-05 apply-write (R-6.3/6.7) ─► 007-06 apply-index (R-6.4)
                                                                                                   │            │
   007-04,05,06 ─► 007-07 synthesis skill + docs + symlinks (R-6.2, C-1)                          │            │
   {007-01, 007-02, 007-06} ─► 007-08 durability acceptance (UC-20, §D8 gate) ◄────────────────────┘            │
   {007-04, 007-05, 007-06, 007-08} ─► 007-09 e2e + compounding (UC-16/17/18/19/21) ◄──────────────────────────┘
   ALL ─► 007-10 regression + docs (ACCEPTANCE GATE)
```

**Critical path** (longest blocking chain): 007-01 → 007-02 → 007-08 → 007-09 → 007-10, **and** 007-03 → 007-04 → 007-05 → 007-06 → 007-08 → 007-09 → 007-10 (the skill chain is the longer one).
**Parallel-safe at start**: {007-01, 007-03} (independent). **007-02** unlocks once 007-01 lands. The skill chain (007-04→05→06) runs alongside 007-02.

---

## 3. Stub-First Application (per `tdd-stub-first`, green-throughout)

| Bead | Code surface? | Phase-1 stub | Phase-1 test (Red→Green on stub) | Phase-2 logic |
|---|---|---|---|---|
| 007-01 | yes (layout.py constants) | n/a — declarative constants | RED: `discover_pages` over a vault with a `_queries/q.md` page yields it; `SCAFFOLD_DIRS` includes `_queries`; `_infer_type_from_path` on `_queries/x.md` → `"query"` | add the constant + tuple membership (single pass) |
| 007-02 | yes (reindex.py) | type-aware branch present but returns no extra refs (records current body-only behavior) | RED: a `type=query` page with `cites: [_vault_/foo]` → after `reindex_full` a `page_entity_refs` row `(query-slug, foo, 'cited')` exists **and** the body `[[bar]]` `mentioned` ref survives (not clobbered); a `cites:` target that is an alias is canonicalized (AM-3) with `ref_type` still `'cited'` | parse `cites:`, build `cited` PageRefs, union into `out.refs` before the single `replace_refs`; skip+report malformed entries |
| 007-03 | yes (DAL) | ABC abstractmethods + `SQLiteRepository` stubs (`check_query_state`→`None`; `record_query_state`→`pass`) | RED: `record_query_state` then `check_query_state` returns the hash; absent → `None`; second record updates (UPSERT) | parameterized SELECT / `INSERT … ON CONFLICT` on `source_state` |
| 007-04 | yes (CLI) | `wiki_query.py` argparse (`prepare`/`apply` subparsers; `apply`→exit "not impl" stub); `bin/wiki-query`; shared retrieval helper extracted, `wiki_search` re-imports it | RED: `--help` ok; `wiki-search` output byte-identical post-extraction; `prepare` emits envelope with hits + `query_slug` + `question_hash`; empty retrieval → `NO_CONTEXT` exit 2; unchanged hash → `is_unchanged:true` | wire `expand_query_aliases`+`search_pages`; slug derive; hash; `check_query_state` |
| 007-05 | yes (CLI) | `apply` handler parses args, calls stubs; no write | RED: `--help` ok; hash mismatch → `QUESTION_CHANGED`; citation ∉ hits → `CITATION_NOT_RETRIEVED`; bad payload → `INVALID_CITATIONS`; valid → `_queries/<slug>.md` written with `type: query`+`cites:`; re-run identical → content-hash skip (`changed:false`); `--force` rewrites | re-retrieve+hash-check; citations⊆hits (`project/slug`); `_sanitize_markdown_text`; atomic write |
| 007-06 | yes (CLI + DAL calls) | `apply` index step stubbed (file written, not indexed) | RED: after `apply` the `pages` row `type=query` exists; N `cited` refs exist; `wiki-search` finds the page; `source_state` recorded; one `query` log_event | `upsert_page`+`replace_refs(cited)` on one conn; `record_query_state`; `append_log_event` |
| 007-07 | **no — skills/docs/symlinks** | n/a | n/a | `init_skill.py wiki-query-synthesis`; write SKILL/command/workflow md; run `bin/link-*.sh` |
| 007-08 | yes (acceptance test) | test scaffolding w/ `pytest.skip` | collection discovers the UC-20 test | full §D8 round-trip: file → snapshot → drop DB → `reindex --full` → assert query page + `cited` refs restored, not degraded |
| 007-09 | yes (acceptance tests) | scaffolding w/ `pytest.skip` | collection discovers UC-16/17/18/19/21 tests | end-to-end happy path + idempotency + NO_CONTEXT + compounding-search + grounding-violation assertions |
| 007-10 | **no — verify/docs** | n/a | n/a | doc edits + run full suite + envelope-regression extension; gate the task |

---

## 4. Use Case Coverage

| Use Case | Description | Beads |
|---|---|---|
| **UC-16** | Ask a question → cited answer page (happy path) | 007-04, 007-05, 007-06, 007-09 |
| **UC-17** | Idempotent re-run (`is_unchanged`; `--force`) | 007-03, 007-04, 007-05, 007-09 |
| **UC-18** | No/low retrieval → anti-hallucination refusal | 007-04, 007-09 |
| **UC-19** | Compounding — a later search finds the prior answer | 007-01, 007-06, 007-09 |
| **UC-20** | Durability round-trip (§D8 gate) | 007-01, 007-02, 007-08 |
| **UC-21** | Citation-grounding violation refused at boundary | 007-05, 007-09 |

---

## 5. RTM Coverage Matrix

| RTM ID | Requirement | Bead(s) | Phase |
|---|---|---|---|
| R-6.1 | `wiki-query prepare` deterministic retrieval | 007-04 | 2 |
| R-6.2 | Orchestrator-owned synthesis + grounding contract (Decision-17) | 007-07 (contract), 007-05 (enforcement) | 2,3 |
| R-6.3 | `apply` writes Class A query page | 007-05 | 2 |
| R-6.4 | Compounding — indexed + `cited` back-linked | 007-06 | 2 |
| R-6.5 | `_queries/` discoverable page-bearing subdir | 007-01 | 1 |
| **R-6.5e** | Reindex `cites:`→`'cited'` read-side (§D8 fix) | 007-02 | 1 |
| R-6.6 | Idempotency / re-run | 007-03 (DAL), 007-04 (`is_unchanged`), 007-05 (`record`/`--force`) | 1,2 |
| R-6.7 | Grounding / no-hit handling | 007-04 (`NO_CONTEXT`), 007-05 (`CITATION_NOT_RETRIEVED`) | 2 |
| AM-3 | reindex ref-canonicalization (cited refs participate, ref_type preserved) | 007-02 | 1 |

**1-1 sanity** (no orphan requirements): every R-6.x + R-6.5e + AM-3 maps to ≥1 bead; every code bead carries ≥1 RTM ID in its `[R-6.x]` tag. UC-16..UC-21 are verified end-to-end by 007-08 + 007-09.

---

## 6. Risk Register

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| **R-1** | **R-6.5e implemented as a 2nd `replace_refs`** → clobbers the body-`mentioned` refs (delete-all-then-insert semantics). | Medium | High | 007-02 acceptance bullet requires the `cited` refs be **unioned into `out.refs` before the single Step-2 `replace_refs`** (Arch M-1); a Phase-1 RED test asserts the body `mentioned` ref **survives** alongside the `cited` ref. |
| **R-2** | **AM-3 degrades `cited`→`mentioned`** on reindex, breaking UC-20. | Low | High | 007-02 verifies Step 2.5 rewrites `entity_slug` only (Arch M-2); 007-08 asserts the reconstructed ref is `ref_type='cited'`, not `'mentioned'`. |
| **R-3** | **Default `wiki-search` now returns `type=query` pages** → surprises existing search callers / breaks search tests. | Medium | Medium | NFR-6 documents the behavior; 007-09 adds a `--types` filter assertion; existing search tests run on fixtures without query pages (unchanged). The shared-retrieval-helper extraction (007-04) keeps `wiki-search` output byte-identical. |
| **R-4** | **Shared-retrieval-helper extraction breaks `wiki-search`** (the byte-identical contract). | Low | Medium | 007-04 Phase-1 RED test pins `wiki-search` output byte-identical pre/post extraction before any `wiki-query` logic is added. |
| **R-5** | **Grounding bypass** — a hallucinated citation slips through if the comparison key is a bare slug across projects. | Medium | High | R-6.7d/UC-21 + 007-05 enforce the full **`project/slug`** tuple, recorded from `prepare` and validated byte-for-byte in `apply`; 007-09 UC-21 test uses a cross-project same-slug fixture. |
| **R-6** | **Answer-body injection** into Class A frontmatter/body (CWE-117/209, YAML-delimiter, wikilink/dataview). | Medium | Medium | 007-05 reuses `_sanitize_markdown_text` (text-only allowlist) + length caps; 007-10 extends the parametrised envelope-never-echoes-content regression to question/answer/citation surfaces. Retrieved snippets are untrusted (H-6) — the synthesis workflow (007-07) carries the prompt-armor. |
| **R-7** | **Self-index N+1** if `apply` reuses the manifest path. | Low | Medium | 007-06 mandates direct `upsert_page`+`replace_refs` on one connection (NFR-5); explicitly forbids `index_from_manifest`/`main(argv)`. |

---

## 7. Definition of Done (acceptance gate — 007-10)

Done iff **all** hold:

- [ ] All 10 beads (007-01..007-10) complete with green acceptance bullets.
- [ ] `pytest tests/ -q` → all green (baseline = the exact count captured at 007-01 start, run once — ≈546 post-TASK-006; + the new TASK 007 cases), 0 failed.
- [ ] `mypy --strict scripts/` → Success: no issues found.
- [ ] **UC-20 §D8 gate** (007-08): file a query page → delete DB → `wiki-reindex --full` → query page rediscovered as `type=query`; `cited` refs reconstructed from `cites:` frontmatter alone, **`ref_type='cited'`** (not `'mentioned'`), body `mentioned` refs intact.
- [ ] **UC-16/17/18/19/21** (007-09): ask→cited page; idempotent re-run (`is_unchanged`); `--force` re-synthesises; `NO_CONTEXT` on empty retrieval (no write); `wiki-search` finds a filed query page + `cited` backlinks exist; citation ∉ hit set → `CITATION_NOT_RETRIEVED` (no write).
- [ ] `wiki-query` has a `bin/` wrapper + `skills/wiki-query/SKILL.md` + `commands/wiki-query.md` + `workflows/wiki-query.md` + the `wiki-query-synthesis` prompt skill + symlinks; `bin/wiki-query --help` exits 0.
- [ ] `pages.type='query'`, `ref_type='cited'`, `event_type='query'` used with **no DDL change**; `PRAGMA user_version == 4` (unchanged).
- [ ] `wiki-search` output is **byte-identical** to pre-007 on a fixture without query pages (shared-helper extraction safe); `--types query` filters to query pages.
- [ ] ROADMAP **R-6 → DONE**; explicit R-7/R-8 hand-off note recorded; `docs/ARCHITECTURE.md` status → SHIPPED.
- [ ] Envelope-never-echoes-content regression suite extended to `wiki-query` (question/answer/citation surfaces).

---

## 8. Effort Summary

| Metric | Value |
|---|---|
| Beads count | 10 |
| Total working-time estimate (single-dev, sequential) | ~6.25 days |
| Critical-path estimate (with DAG parallelization) | ~4.5 days |
| Acceptance-gate effort (007-08 + 007-09 + 007-10) | ~1.75 days |

---

## 9. Open Issues / Planner Judgement Calls

1. **Spine-first ordering** — 007-01/02/03 (layout + reindex read-side + query-state DAL) land before the skill because the §D8 durability gate (UC-20) is the binding acceptance criterion and `apply`'s compounding (007-06) writes the refs that 007-02 must round-trip.
2. **`apply` split into write (007-05) + index (007-06)** — the Class-A-first write-order (file then DB, mirroring `wiki-merge`'s C-8) makes a clean Stub-First seam: Phase-1 writes the file, Phase-2 indexes it. Each is a single testable bead.
3. **Shared retrieval helper (C-6)** — 007-04 extracts `_expand_query` + the search call from `wiki_search.py` into a small shared module imported by both CLIs; a Phase-1 RED test pins `wiki-search` byte-identical before any `wiki-query` logic, so the refactor is safe.
4. **Resolved open questions baked in:** Q-A6/Q3 idempotency hash = `sha256(question ‖ ordered retrieved project/slug set)` (007-03/04); Q-A7/Q4 `cites:` id = `project/slug` (007-02/05); Q-A8/Q7 body rendering = trailing `## Sources` `[[project/slug]]` list, `cites:` frontmatter authoritative (007-05/07); Q-A9 dual-ref allowed (PK-distinct), resolved in 007-02.
5. **SKILL CREATION GATE** — 007-07 scaffolds the `wiki-query-synthesis` prompt skill via `init_skill.py` (mandatory per CLAUDE.agentic.md); the product `skills/wiki-query/` CLI skill follows the repo-root + `bin/link-skill.sh` convention (TASK 005 005-15 precedent).
6. **`skill-tdd-strict` (high-assurance) beads** — the correctness-critical beads run under strict TDD (test-first, full edge-case unit coverage, no over-mocking of the DB): **007-02** (R-6.5e reindex read-side — the durability spine), **007-05** (the grounding gate), and **007-08** (the §D8 acceptance gate). All other code beads use standard Stub-First. Every bead is green-throughout (suite never red at a boundary).
7. **No vault dogfood in-repo** — the repo IS the implementation, not a vault (CLAUDE.md); 007-08/09 acceptance tests run on a throwaway `/tmp` fixture vault, as TASK 005 did (TASK §6 Q8 default).

---

## 10. Start Signal

Plan-reviewer gate next. After sign-off, start with **007-01** (layout `_queries` — blocks the reindex read-side and the apply write target). **007-03** (query-state DAL) may proceed in parallel; **007-02** unlocks once 007-01 lands; the skill chain (007-04→05→06) starts once 007-03 lands.
