# Task 007-02: reindex read-side — `type=query` `cites:` → `ref_type='cited'` (the §D8 durability fix)

> **strict-TDD** (high-assurance — this is the durability spine; UC-20 fails without it).

## Use Case Connection
- UC-20: Durability round-trip (the binding §D8 acceptance gate).

## Task Goal
Extend `wiki-reindex --full` so a `type=query` page's `cites:` frontmatter list is re-materialised as `ref_type='cited'` `page_entity_refs` — the read-side that lets query-page citations survive a full DB rebuild from Class A markdown alone. This is **structural change #2** (RTM R-6.5e). Without it, a query page's `cited` refs are lost on reindex (the current rebuild reads body `[[wikilinks]]` only, hardcoded `ref_type='mentioned'`).

**Critical mechanism (Arch M-1):** `cited` refs land in the **same** `page_entity_refs` table that reindex Step 2 already rebuilds via one `replace_refs(...)` call — and `replace_refs` is **delete-all-for-the-page then insert** ([sqlite_repository.py:381-399](../../scripts/wiki_index/sqlite_repository.py)). So the `cited` refs **must be unioned into the page's `out.refs` set BEFORE the single Step-2 `replace_refs`** — never a second `replace_refs` (which would clobber the body-`mentioned` refs).

## Changes Description

### Changes in Existing Files

#### File: `scripts/wiki_index/reindex.py`
- In the Step-2 per-page rebuild loop ([reindex.py:261-273](../../scripts/wiki_index/reindex.py)), after `adapter.fetch(item)` produces `out` and `normalize_frontmatter` yields `db_type`, add a **type-aware branch**: `if db_type == "query":` parse the page's `cites:` frontmatter list into additional `PageRef`s and **extend `out.refs`** before the single `repo.replace_refs(vault_id, out.page_slug, out.project, out.refs)` call.
- Add a helper `_cited_refs_from_frontmatter(updated_fm, vault_id, page_slug, page_project) -> list[PageRef]`:
  - Read `updated_fm.get("cites")`; if not a list → return `[]`.
  - For each entry: must be a `str` of shape `"<project>/<slug>"` (split on the last `/`; both parts non-empty kebab). Build `PageRef(vault_id, page_slug, page_project, entity_slug=<cited-slug>, ref_type="cited", line_start=None, line_end=None, source_quote=None, trust_level="medium")`. **Note (Plan Reviewer m-1):** the cited target's *project* is parsed only for shape-validation/grounding parity — it is **not** persisted in the ref row (`page_entity_refs` keys refs by `entity_slug` only, exactly as body-`mentioned` refs do). 007-06 must store the same `entity_slug`-only row so the `apply`-written ref and this reindex-rebuilt ref are byte-for-byte identical (007-08 cross-checks the symmetry).
  - **Skip-and-report** malformed/empty entries by appending to the reindex `skipped`/warnings report (never silent-drop, mirroring R-5.3c). Do not raise.
  - De-dup within the page on `(entity_slug, "cited")`.
- Confirm **Step 2.5 (AM-3)** ([reindex.py:372-409](../../scripts/wiki_index/reindex.py)) already canonicalizes these new `cited` rows: it rewrites `entity_slug` through the alias map for **every** ref regardless of `ref_type`, and never touches `ref_type` — so a `cites:` target that is a registered alias re-points to canonical, and the row stays `'cited'`. No change needed in Step 2.5; **add an assertion-style test** that confirms it.

### Component Integration
The `cited` refs join the body-wikilink `mentioned` refs in `out.refs`, all written by the existing single `replace_refs`. A query page may carry both a `cited` (frontmatter) and a `mentioned` (body `## Sources` wikilink) ref to the same target — the composite PK `(vault_id, page_slug, page_project, entity_slug, ref_type)` keeps them distinct.

## Test Cases

### End-to-end Tests
1. **TC-E2E-01 (durability core):** Fixture vault with `_queries/q.md` (`type: query`, `cites: [_vault_/foo]`, body containing `[[bar]]`). Run `reindex_full`. Assert: `page_entity_refs` has `(q, foo, 'cited')` **and** `(q, bar, 'mentioned')` — the `cited` ref is created and the body `mentioned` ref is **not clobbered** (Arch M-1 regression).
2. **TC-E2E-02 (AM-3, ref_type preserved):** `cites: [_vault_/old-name]` where `old-name` is a registered alias of canonical `new-name`. After `reindex_full`: the ref is `(q, new-name, 'cited')` — `entity_slug` canonicalized, `ref_type` still `'cited'` (Arch M-2; no degradation to `'mentioned'`).
3. **TC-E2E-03 (skip+report):** `cites: ["", "no-slash", _vault_/ok]` → only `(q, ok, 'cited')` written; the two malformed entries appear in the reindex `skipped`/warnings report.

### Unit Tests
1. **TC-UNIT-01:** `_cited_refs_from_frontmatter` parses `"_vault_/foo"` → `PageRef(entity_slug="foo", ref_type="cited", trust_level="medium", line_start=None, source_quote=None)`.
2. **TC-UNIT-02:** malformed entries (`""`, `"nofoo"` without `/`, non-str) → excluded + recorded.

### Regression Tests
- Non-query pages (`_sources`/`_concepts`/`_entities`) reindex **unchanged** — the branch is gated on `db_type == "query"`.
- The existing AM-3 / merge durability tests (`test_entity_resolution_durability.py`, `test_reindex_alias_mirror.py`) stay green.

## Acceptance Criteria
- [ ] `type=query` page's `cites:` → `ref_type='cited'` refs, unioned into the single Step-2 `replace_refs` (NOT a second call).
- [ ] Body `mentioned` refs on a query page survive (not clobbered).
- [ ] AM-3 (Step 2.5) canonicalizes `cited` targets through aliases with `ref_type` preserved.
- [ ] Malformed `cites:` entries skip-and-report (no silent drop, no raise).
- [ ] Non-query pages unchanged; full `pytest` green; `mypy --strict` clean.

## Notes
Strict-TDD: write TC-E2E-01/02/03 RED first (they fail because the branch returns no `cited` refs / clobbers), then implement. This bead is on the critical path and is the load-bearing fix the Task-Review CRITICAL (C-1) and Arch-Review M-1/M-2 demanded.
