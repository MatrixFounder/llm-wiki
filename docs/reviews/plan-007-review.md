# Plan Review — TASK 007 (`wiki-query` RAG layer / Epic 7 R-6)

- **Date:** 2026-05-29
- **Reviewer:** Plan Reviewer (Planning→Execution gate, VDD mode)
- **Status:** ✅ **APPROVED WITH COMMENTS** (0 CRITICAL / 2 MAJOR / 4 MINOR) — all comments folded into PLAN.md + the bead files (see Resolution Log).
- **Checklist:** `plan-review-checklist` v1.0 + six scrutiny axes + code-ground-truth spot-check.

## General Assessment

Exceptionally strong, traceable plan. Spine-first decomposition is correct: the
§D8 durability gate (UC-20) is the binding acceptance criterion and the plan
lands its load-bearing dependencies (007-01 layout → 007-02 reindex read-side;
007-03 query-state DAL) before the skill chain. **All three highest-value
prior-gate constraints are encoded correctly and verified against code ground
truth.** All 10 per-bead files exist and match the PLAN.md links (10/10). RTM
coverage is 1-1 (no orphan requirement, no feature-grouped bead). No CRITICAL.

## Load-bearing mechanism fidelity — PASS (verified against code)

| Constraint | Plan encoding | Code ground truth | Verdict |
|---|---|---|---|
| 007-02 union `cited` into the single Step-2 `replace_refs`, NOT a 2nd call | §0 inv. 2, Risk R-1, bead-02 + TC-E2E-01 (body `mentioned` survives) | `replace_refs` IS delete-all-then-insert (`sqlite_repository.py:381-385`) | ✅ |
| AM-3 preserves `ref_type` | bead-02 + TC-E2E-02; inv. 3; Risk R-2 | Step 2.5 `UPDATE … SET entity_slug=?` only (`reindex.py:391-409`) | ✅ |
| 007-06 self-index via direct `upsert_page`+`replace_refs`, NOT `index_from_manifest`/`main(argv)` | §0 inv. 6, Risk R-7, bead-06 + TC-E2E-05 (call-count guard) | H-PERF-3/P-8 ban confirmed | ✅ |
| 007-05 grounding key = full `project/slug` | §0 inv. 5, Risk R-5, bead-05 step 3 + TC-E2E-04 (cross-project same-slug) | matches `pages` UNIQUE `(vault_id, slug, project)` | ✅ |

Extraction/lift targets also verify: `_expand_query`/`_fts_quote` at
`wiki_search.py:32,37` (007-04); `_sanitize_markdown_text` at
`wiki_extract_concepts.py:485` + the raw-SQL `source_state` precedent it
improves on (007-03 NFR-2 claim accurate).

## RTM / UC / Stub-First / DAG — PASS

RTM 1-1 (every R-6.x + R-6.5e + AM-3 → ≥1 bead; every code bead → `[R-6.x]`
tag). All 6 UCs map (UC-20→07-08; the rest→07-09). §3 Stub-First table concrete
+ per-bead; 007-03 lands ABC abstractmethod + `SQLiteRepository` stub together
(green-throughout); strict-TDD on 007-02/05/08. DAG acyclic, spine-first, no
missing edge. Beads 0.25–1.0 day. All 10 files exist, names match links.

## Comments

### 🟡 MAJOR
- **M-1 — 007-08's stated dependency list omits 007-05.** It lists `007-01,
  007-02, 007-06`; filing a page needs the write-side (007-05) too. The
  transitive edge (007-06 → 007-05) keeps build order correct, but the stated
  set could mislead a developer parallelizing the DAG. **Fix:** add 007-05.
- **M-2 — no bead asserts the Arch Q-A9(b) consumer-safety half** (that
  `find_orphan_links` + backlink consumers tolerate a target reachable via two
  `ref_type`s). Plan covers Q-A9(a) (dual-ref shape) thoroughly; (b) only
  implicit in "full pytest green". **Fix:** extend 007-09 TC-E2E-19 with the
  assertion (cheapest home — it already queries `get_backlinks`).

### 🟢 MINOR
- **m-1 —** state explicitly that the cited target's *project* is not persisted
  in the ref row (only `entity_slug`), so 007-02 and 007-06 produce byte-identical
  rows.
- **m-2 —** pin the exact current `pytest` baseline count at 007-01 start rather
  than "546+".
- **m-3 —** in bead-07's body (not just Notes), distinguish the gated
  `wiki-query-synthesis` skill (`init_skill.py`) from the conventionally-authored
  `skills/wiki-query/` product skill.
- **m-4 —** 007-09 TC-E2E-17b: assert a concrete `--force` observable
  (`changed:true` / fresh log event), not "rewrites (or re-stamps)".

## Resolution Log (PLAN + bead files rev 2)

- **M-1 → FIXED:** PLAN §1 007-08 dependency line + bead-08 Notes now list 007-05
  (and explain the transitive-edge accuracy point).
- **M-2 → FIXED:** bead-09 TC-E2E-19 extended with the Q-A9(b) dual-ref
  consumer-safety assertions (`get_backlinks` correctness + `find_orphan_links`
  no-false-flag).
- **m-1 → FIXED:** bead-02 + bead-06 now state the cited target's project is
  parsed-for-validation only, not persisted; 007-02/06 symmetry called out.
- **m-2 → FIXED:** PLAN §7 baseline reworded to "exact count captured at 007-01
  start (≈546 post-TASK-006)".
- **m-3 → FIXED:** bead-07 body distinguishes the gated synthesis skill from the
  product CLI skill.
- **m-4 → FIXED:** bead-09 TC-E2E-17b now asserts `changed:true` / fresh log event.

## Final Decision

**APPROVED — proceed to Execution (`/vdd-develop-all`).** No CRITICAL/BLOCKING;
the plan faithfully encodes all three load-bearing prior-gate constraints
(verified against `reindex.py`, `sqlite_repository.py`, and the extraction/lift
targets), RTM is 1-1, Stub-First is per-bead + green-throughout, the DAG is
acyclic and spine-first, and all 10 per-bead files are concrete (relative paths,
signatures, real test assertions). The 2 MAJOR + 4 MINOR were accuracy/coverage
gaps, now folded in. Start with **007-01** (layout `_queries`); **007-03** runs
in parallel; **007-02** unlocks after 007-01.
