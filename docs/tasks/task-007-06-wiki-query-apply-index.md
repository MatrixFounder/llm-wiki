# Task 007-06: `wiki-query apply` (index-side) — self-index + `cited` refs + log event + idempotency record

## Use Case Connection
- UC-16: Ask → cited answer page (the page becomes queryable).
- UC-19: Compounding — the filed query page is FTS-searchable + back-linked.
- UC-17: Idempotency record (`record_query_state`).

## Task Goal
Complete `apply` (RTM R-6.4 + R-6.6-apply): after the Class A file write (007-05), self-index the one query page into the DB via **direct DAL calls on a single connection** — `upsert_page` (`type='query'`) + `replace_refs` (`cited` refs) — then `record_query_state` and append one `query` `log_event`. **Must NOT** route through `_manifest_consumer.index_from_manifest` → `wiki_index_upsert.main(argv)` (that is the open H-PERF-3/P-8 N+1; a query page is exactly one page).

## Changes Description

### Changes in Existing Files

#### File: `scripts/wiki_skills/wiki_query.py`
- After the successful Class A write, build the `Page` (reuse the normalization path: `parse_frontmatter` of the just-written file → `normalize_frontmatter(source_path=…)` → `_build_page`-equivalent, or construct `Page` directly with `type='query'`, `frontmatter_json`, `file_hash`, etc.). Prefer reusing the existing page-build helpers so FTS triggers + columns stay consistent with reindex.
- Build the `cited` `PageRef`s from the validated citations: `PageRef(vault_id, page_slug=query_slug, page_project=<the QUERY page's project>, entity_slug=<cited-slug>, ref_type='cited', line_start=None, line_end=None, source_quote=None, trust_level='medium')`. **Note (Plan Reviewer m-1):** `page_project` is the **query page's** project (where the ref lives), not the cited target's. The cited target's project (the part before `/` in the `project/slug` citation) is used only for the grounding match in 007-05 — it is **not** stored in the ref row (`entity_slug` is the slug alone), exactly mirroring 007-02's reindex read-side so the two produce byte-identical rows (cross-checked by 007-08).
- On **one repo connection**: `repo.upsert_page(page)` then `repo.replace_refs(vault_id, query_slug, project, cited_refs)`. (If the content-hash skip in 007-05 returned `changed:false`, still ensure the refs + state are consistent — but skip the rewrite.)
- `repo.record_query_state(vault_id, query_slug, question_hash)` (007-03).
- `repo.append_log_event(LogEvent(vault_id, event_ts=now, event_type='query', subject=query_slug, …))` — one event per filed query (Q6/Q-A6 default).
- Emit the final manifest envelope `{"vault_id","query_slug","cites":[…],"page_indexed":true,"action":"filed"}` (or `{"action":"unchanged"}` on a no-op skip).

### Component Integration
Closes the compounding loop: the query page is now an FTS-searchable `pages` row with `cited` backlinks. 007-02's reindex read-side re-materialises exactly these `cited` refs from the `cites:` frontmatter on a full rebuild (the two must agree — verified by 007-08).

## Test Cases

### End-to-end Tests
1. **TC-E2E-01 (self-index):** after `apply`, the `pages` row `(query_slug, '_vault_', 'query')` exists; `wiki-search v "<question terms>"` returns it.
2. **TC-E2E-02 (cited refs):** N `page_entity_refs` rows `(query_slug, <cited-slug>, 'cited')` exist, one per citation.
3. **TC-E2E-03 (log event):** exactly one `log_events` row `event_type='query'`, `subject=query_slug`.
4. **TC-E2E-04 (idempotency record):** `check_query_state(v, query_slug)` returns the `question_hash` after apply; a subsequent `prepare` of the same question → `is_unchanged: true`.
5. **TC-E2E-05 (no N+1):** assert (via a patched/​spy repo or a call-count guard) that indexing does **not** call `wiki_index_upsert.main` / `index_from_manifest` — the page is indexed by direct `upsert_page`+`replace_refs`.

### Unit Tests
1. **TC-UNIT-01:** the `Page` built for the query file has `type=='query'` and a non-empty `frontmatter_json` containing `cites`.
2. **TC-UNIT-02:** `cited` `PageRef`s carry `ref_type='cited'`, `trust_level='medium'`, `line_start/end/source_quote == None`.

### Regression Tests
- `wiki-search`/reindex behavior on non-query pages unchanged.
- The `cited` refs written by `apply` match (slug-for-slug) what 007-02's reindex read-side produces from the same `cites:` (cross-checked by 007-08).

## Acceptance Criteria
- [ ] `apply` self-indexes via direct `upsert_page` + `replace_refs` on one connection (NOT manifest/`main(argv)`).
- [ ] `cited` refs written (one per citation); query page FTS-searchable.
- [ ] One `query` log event; `record_query_state` called.
- [ ] No N+1 / manifest path (TC-E2E-05).
- [ ] Full `pytest` green; `mypy --strict scripts/` clean.

## Notes
Stub-First: Phase-1 = index step stubbed (file written, not indexed) + RED tests; Phase-2 = the direct-DAL index + log + state. The `apply` write-side (007-05) and index-side (007-06) together form the full `apply` subcommand.
