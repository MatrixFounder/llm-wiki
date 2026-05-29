# Task 007-09: end-to-end + compounding acceptance (UC-16/17/18/19/21)

## Use Case Connection
- UC-16 (happy path), UC-17 (idempotency), UC-18 (no-context refusal), UC-19 (compounding), UC-21 (grounding violation).

## Task Goal
Verify the full `wiki-query` behaviour end-to-end on a throwaway `/tmp` vault — the retrieve→synthesise→file loop and its compounding/idempotency/grounding guarantees — exercising the `bin/wiki-query` entry point as an operator would.

## Changes Description

### New Files
- `tests/test_wiki_query_e2e.py` — end-to-end acceptance suite driving `prepare`/`apply` (synthesis is done in-test by constructing the answer+citations directly; no real LLM call, per `tdd-stub-first` §3 "no mocking LLMs — use constructed inputs").

## Test Cases

### End-to-end Tests
1. **TC-E2E-16 (UC-16 happy path):** seed a vault; `prepare "How does Hermes route?"` → take the envelope's `query_slug`+`question_hash`+a citation from `hits`; `apply` with a small answer → `_queries/<slug>.md` exists (`type: query`, `cites:`), exit 0, `{"action":"filed"}`.
2. **TC-E2E-17a (UC-17 idempotent):** re-run `prepare` for the same question on the unchanged vault → `is_unchanged: true`; (workflow stops — assert the envelope, no second write).
3. **TC-E2E-17b (UC-17 --force):** `apply … --force` on byte-identical content does **not** skip — assert the concrete observable: the envelope reports `changed:true` (and/or a fresh `query` `log_event` is appended for the re-file), distinguishing it from the content-hash-skip path (`changed:false`) of a non-`--force` re-apply (Plan Reviewer m-4).
4. **TC-E2E-18 (UC-18 NO_CONTEXT):** `prepare "<topic absent from vault>"` → `{"error":"NO_CONTEXT"}` exit 2; assert no `_queries/*.md` written and no `pages` row created.
5. **TC-E2E-19 (UC-19 compounding + Q-A9(b) consumer-safety):** after filing a query page (TC-E2E-16), `wiki-search v "<question terms>"` returns the query page among hits; `wiki-search v "<terms>" --types query` returns only query pages; `wiki-search … --types summary,concept` excludes it; `repo.get_backlinks(hermes-agent)` (or a refs query) includes the `cited` ref from the query page. **Dual-ref consumer-safety (Arch Q-A9(b), Plan Reviewer M-2):** when the query page reaches a target via **both** a `cited` (frontmatter) and a `mentioned` (body wikilink) ref, assert (a) `get_backlinks(target)` surfaces the query page correctly (no double-count crash / no missing backlink), and (b) `repo.find_orphan_links(v)` does **not** false-flag the `cited` target as an orphan (it resolves to a real entity).
6. **TC-E2E-21 (UC-21 grounding violation):** `apply` with a citation not in the `prepare` hit set → `CITATION_NOT_RETRIEVED` exit 4; assert no file written, no `pages`/`refs` rows, envelope echoes no slug value.

### Regression Tests
- Full `pytest tests/` stays green; these are additive acceptance tests over the real `bin/` entry point.

## Acceptance Criteria
- [ ] UC-16/17/18/19/21 each have a passing end-to-end assertion over `bin/wiki-query`.
- [ ] `NO_CONTEXT` and `CITATION_NOT_RETRIEVED` paths write nothing (no file, no DB rows).
- [ ] `--types query` filter works; the filed query page is FTS-searchable + back-linked (compounding proven).
- [ ] Runs on a `/tmp` fixture vault; full `pytest` green; `mypy --strict` clean.

## Notes
Stub-First: scaffold with `pytest.skip` markers (Phase-1 collection green), then fill assertions as 007-04/05/06 land. Depends on the full skill (007-04/05/06) + 007-08 (the durability fixture helpers can be shared). Synthesis is constructed in-test — no LLM dependency.
