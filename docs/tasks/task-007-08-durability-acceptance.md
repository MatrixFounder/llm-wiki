# Task 007-08: §D8 durability round-trip acceptance test (the binding gate)

> **strict-TDD** (high-assurance — this is the §D8 acceptance gate for the compounding promise).

## Use Case Connection
- UC-20: Durability round-trip (the load-bearing acceptance test).

## Task Goal
Prove the §D8 contract end-to-end (RTM R-6.5 + R-6.5e + AM-3): a query page filed by `wiki-query apply` reconstructs **from Class A markdown alone** after a full DB rebuild — the query page is rediscovered as `type=query` and its `cited` refs are re-materialised from the `cites:` frontmatter, **not** lost and **not** degraded to `mentioned`.

## Changes Description

### New Files
- `tests/test_wiki_query_durability.py` — the §D8 round-trip acceptance test (the `test_entity_resolution_durability.py` analog).

### Test Body (the gate)
1. Scaffold a throwaway `/tmp` vault; register it; seed a couple of `_concepts`/`_sources` pages (e.g. `hermes-agent`, a source mentioning it).
2. Run the full `wiki-query` flow to file a query page: `prepare` → synthesise a small answer + citations (`["_vault_/hermes-agent"]`) in-test (no real LLM — construct the citations directly) → `apply`. Optionally the query page body also contains a `[[hermes-agent]]` `## Sources` wikilink (to exercise the dual `cited`+`mentioned` coexistence).
3. **Snapshot** the DB state: the `pages` row `(query_slug, '_vault_', 'query')` and the `page_entity_refs` rows for `query_slug` (expect a `'cited'` ref to `hermes-agent`, and — if the body wikilink is present — a `'mentioned'` ref too).
4. **Delete the DB file**; run `wiki-reindex --full` on the vault.
5. **Re-read** the DB state and assert.

## Test Cases

### End-to-end Tests
1. **TC-E2E-01 (page rediscovered):** after DB-delete + `reindex --full`, the `pages` row `(query_slug, '_vault_', 'query')` exists (proves `_queries ∈ PAGE_SUBDIRS`, 007-01).
2. **TC-E2E-02 (cited refs restored):** a `page_entity_refs` row `(query_slug, hermes-agent, 'cited')` exists — reconstructed from `cites:` frontmatter alone by the R-6.5e read-side (007-02). **`ref_type == 'cited'`**, explicitly asserting it is NOT `'mentioned'`.
3. **TC-E2E-03 (dual-ref coexistence):** if the body carried `[[hermes-agent]]`, both `(…, hermes-agent, 'cited')` and `(…, hermes-agent, 'mentioned')` exist post-reindex (PK-distinct; the `cited` ref not clobbered by the body pass — Arch M-1).
4. **TC-E2E-04 (AM-3, alias cite):** a variant where `cites: [_vault_/old-name]` and `old-name` is an alias of `hermes-agent` → post-reindex the ref is `(query_slug, hermes-agent, 'cited')` (canonicalized, ref_type preserved — Arch M-2).
5. **TC-E2E-05 (FTS recall, UC-19 link):** post-reindex, `wiki-search v "<question terms>"` returns the query page.

### Regression Tests
- The existing §D8 durability tests for entities/aliases/merges (`test_entity_resolution_durability.py`) stay green — query-page durability is additive.

## Acceptance Criteria
- [ ] After DB-delete + `wiki-reindex --full`: query page rediscovered as `type=query`; `cited` refs reconstructed from `cites:` alone; `ref_type='cited'` (not `'mentioned'`); body `mentioned` refs intact; alias-cite canonicalized with ref_type preserved.
- [ ] Test runs on a throwaway `/tmp` fixture vault (no in-repo dogfood).
- [ ] Full `pytest` green; `mypy --strict scripts/` clean.

## Notes
Strict-TDD: this test is authored RED against the spine (007-01/02/05/06) and must pass only once the read-side is correct. It is the binding gate — if it cannot pass, the compounding promise is not delivered. Depends on **007-05** (write-side, to write the Class A page) + **007-06** (index-side, to index it) + 007-02 (to round-trip the `cited` refs) + 007-01 (to rediscover the page). (007-06 transitively requires 007-05, so the build order is correct regardless; both are listed for accuracy — Plan Reviewer M-1.)
