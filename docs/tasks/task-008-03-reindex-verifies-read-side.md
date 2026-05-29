# Task 008-03: reindex read-side — `type=verification` `verifies:` → `ref_type='verifies'` (the §D8 durability fix)

> **strict-TDD** (high-assurance — this is the durability spine; UC-26 fails without it).

## Use Case Connection
- UC-26: Durability round-trip (the binding §D8 acceptance gate).

## Task Goal
Extend `wiki-reindex` so a `type=verification` page's `verifies:` frontmatter (one `project/slug`) is re-materialised as a `ref_type='verifies'` `page_entity_ref`, and its optional `cites:` as `'cited'` refs — the read-side that lets the verdict→query edge survive a full DB rebuild from Class A markdown alone. This is **R-8.5e**, the exact analog of R-6.5e. Generalise the existing query-page helper into one `_frontmatter_refs(db_type, …)` (DRY — C-6), keeping the `type=query` `cites:` branch working.

**Critical mechanism (Arch M-1):** the new refs land in the **same** `page_entity_refs` table reindex Step 2 rebuilds via one `replace_refs(...)` call (delete-all-for-the-page then insert). So they **must be unioned into the page's `out.refs` set BEFORE the single Step-2 `replace_refs`** — never a second `replace_refs` (which would clobber the body-`mentioned` refs). Apply in **both** `reindex_full` **and** `reindex_delta` (delta-symmetry — the TASK 007 vdd-multi round-2 lesson).

## Changes Description

### Changes in Existing Files

#### File: `scripts/wiki_index/reindex.py`
- **Generalise** `_cited_refs_from_frontmatter(updated_fm, vault_id, page_slug, page_project, …)` → `_frontmatter_refs(db_type, updated_fm, vault_id, page_slug, page_project, report) -> list[PageRef]`:
  - For `db_type == "query"`: parse `cites:` → `ref_type='cited'` (unchanged behavior).
  - For `db_type == "verification"`:
    - parse `verifies:` (a **single** `"<project>/<slug>"` string) → one `PageRef(entity_slug=<query-slug>, ref_type="verifies", line_start=None, line_end=None, source_quote=None, trust_level="medium")`. **Note:** as with `cited`, the cited target's *project* is parsed for shape-validation only — the ref row keys by `entity_slug` only (parity with body-`mentioned`), so the `apply`-written ref (008-07) and this reindex-rebuilt ref are byte-for-byte identical (008-09 cross-checks).
    - parse `cites:` (optional) → `ref_type='cited'` refs (reuse the `query` path).
  - **Skip-and-report** malformed/empty `verifies:`/`cites:` entries by appending to the reindex `skipped`/warnings report (never silent-drop, never raise). A `verification` page with no/blank `verifies:` is reported (it is malformed — `apply` always writes one), but the page still indexes.
  - De-dup within the page on `(entity_slug, ref_type)`.
- In **both** the `reindex_full` Step-2 loop (~line 349-356) **and** the `reindex_delta` loop (~line 236-243): call `_frontmatter_refs(db_type, …)` and **extend `out.refs`** before the single `repo.replace_refs(vault_id, out.page_slug, out.project, out.refs)`. The existing `if db_type == "query":` branches become `if db_type in ("query", "verification"):` (or call the generalised helper unconditionally — it returns `[]` for other types).
- Confirm **Step 2.5 (AM-3)** (~line 455-492) canonicalizes the new `verifies`/`cited` rows: it rewrites `entity_slug` through the alias map for every ref regardless of `ref_type` and never touches `ref_type` — so a `verifies:` target that is a registered alias re-points to canonical, and the row stays `'verifies'`. No change needed in Step 2.5; **add an assertion-style test**.

#### File: `scripts/wiki_skills/wiki_query.py` — RENAME FANOUT, MUST land in this bead (adversarial-plan finding CMP-2/DEC-1/DUR-1)
- `_index_query_page` **imports** `_cited_refs_from_frontmatter` (~line 311) and **calls** it (~line 325) with the old signature `(updated_fm, vault_id, out.page_slug, out.project, [])`. Update the import + call to `_frontmatter_refs("query", updated_fm, vault_id, out.page_slug, out.project, report)`. **Without this edit in the SAME bead, `wiki-query apply`'s self-index raises `ImportError` (apply dies) + mypy --strict fails — a green-throughout break at a strict-TDD boundary.**

#### File: `tests/test_reindex_cites.py` — RENAME FANOUT, MUST land in this bead
- Update the **module-top import** (~line 16) + **all 4 call sites** (~lines 150/164/171/172) from `_cited_refs_from_frontmatter(fm, …)` to `_frontmatter_refs("query", fm, …)`. The module-top import is a **collection-time** dependency — a stale name reds the **whole** pytest suite, not one test.

> **Alternative (minimal-risk, equally acceptable):** instead of touching the two external callers, keep a one-line back-compat shim in `reindex.py` — `_cited_refs_from_frontmatter = functools.partial(_frontmatter_refs, "query")` (or a thin wrapper def). Either approach is fine; **the bead MUST do exactly one of them** so the 008-03 boundary stays green. (Grounded inventory: 2 imports + 5 call sites — `wiki_query.py:311/325` + `test_reindex_cites.py:16/150/164/171/172`.)

### Component Integration
The `verifies`/`cited` refs join the body-wikilink `mentioned` refs in `out.refs`, all written by the existing single `replace_refs`. A verdict page may carry `verifies` (→query) + `cited` (→source) + a body `## Sources` `[[wikilink]]` `mentioned` ref to the same target — the composite PK `(vault_id, page_slug, page_project, entity_slug, ref_type)` keeps them distinct. Entity-registration is gated on `_concepts`/`_entities` rel-parts, so a `_verifications/` page never creates an `entities` row (C-10).

## Test Cases

### End-to-end Tests
1. **TC-E2E-01 (durability core, full + delta):** Fixture vault with `_verifications/v.md` (`type: verification`, `verifies: _vault_/q`, body containing `[[bar]]`). Run `reindex_full` → `page_entity_refs` has `(v, q, 'verifies')` **and** `(v, bar, 'mentioned')` (the `verifies` ref created, the body `mentioned` ref **not clobbered**, Arch M-1). Repeat the assertion after `reindex_delta` (delta-symmetry).
2. **TC-E2E-02 (AM-3, ref_type preserved):** `verifies: _vault_/old-q` where `old-q` is a registered alias of canonical `new-q`. After reindex: `(v, new-q, 'verifies')` — `entity_slug` canonicalized, `ref_type` still `'verifies'` (AM-3; no degradation to `'mentioned'`).
3. **TC-E2E-03 (optional cites):** `verifies: _vault_/q` + `cites: [_vault_/foo]` → both `(v, q, 'verifies')` and `(v, foo, 'cited')` written.
4. **TC-E2E-04 (skip+report):** `verifies: ""` (blank) or `cites: ["", "no-slash"]` → malformed entries appear in the reindex `skipped`/warnings report; the page still indexes; valid entries written.
5. **TC-E2E-05 (query regression):** a `type=query` page with `cites:` still produces `'cited'` refs (the generalisation didn't break R-6.5e).

### Unit Tests
1. **TC-UNIT-01:** `_frontmatter_refs("verification", {"verifies":"_vault_/q"}, …)` → `[PageRef(entity_slug="q", ref_type="verifies", trust_level="medium", line_start=None, source_quote=None)]`.
2. **TC-UNIT-02:** `_frontmatter_refs("query", {"cites":["_vault_/foo"]}, …)` → `'cited'` ref (unchanged).
3. **TC-UNIT-03:** malformed `verifies:` (non-str, no `/`, empty) → `[]` + recorded.

### Regression Tests
- Non-query/non-verification pages reindex unchanged (helper returns `[]`).
- `test_reindex_cites.py` (the R-6.5e suite) — its import + 4 calls updated to `_frontmatter_refs("query", …)` (or left untouched if the back-compat shim is used); stays green either way.
- **`wiki-query apply` self-index still imports + works** post-rename (regression for the fanout): a `wiki-query apply` e2e still files + indexes a query page with `cited` refs.
- The AM-3 / merge durability tests (`test_entity_resolution_durability.py`, `test_reindex_alias_mirror.py`) stay green.

## Acceptance Criteria
- [ ] `type=verification` page's `verifies:` → `ref_type='verifies'` ref, unioned into the single Step-2 `replace_refs` (NOT a second call), in **both** `reindex_full` and `reindex_delta`.
- [ ] Optional `cites:` on a verdict page → `'cited'` refs (reused path).
- [ ] Body `mentioned` refs survive (not clobbered); AM-3 canonicalizes with `ref_type` preserved.
- [ ] Malformed entries skip-and-report (no silent drop, no raise); the page still indexes.
- [ ] `type=query` `cites:` regression green; non-target pages unchanged; full `pytest` green; `mypy --strict` clean.
- [ ] **Rename fanout handled IN THIS BEAD** — `wiki_query.py` self-index + `test_reindex_cites.py` updated to `_frontmatter_refs("query", …)` OR a back-compat shim added; `wiki-query apply` still imports/works; the suite is green at the 008-03 boundary (no `ImportError`/collection failure).

## Notes
Strict-TDD: write TC-E2E-01..05 RED first (they fail because the helper returns nothing for `verification`), then implement. Depends on 008-01 (schema admits the ref) + 008-02 (`TYPE_MAPPING` so the page indexes at all). This is the load-bearing fix the arch-review M-1 demanded be explicit in the plan.
