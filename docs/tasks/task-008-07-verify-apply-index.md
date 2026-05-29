# Task 008-07: `wiki-verify-multi apply` (index-side) — self-index the verdict page

> **strict-TDD** (plan-review M-2) — the byte-identical-rows §D8 *symmetry keystone*.
> `apply`'s `pages` row + `verifies` ref MUST equal a `reindex._build_page` +
> `_frontmatter_refs` rebuild byte-for-byte, or 008-09's drop-DB→reindex comparison
> is vacuous. **TC-UNIT-01 (byte-identity) is written test-first**, RED before the
> direct-DAL index logic lands.

## Use Case Connection
- UC-22: Verify → PASS (the verdict page compounds — indexed + back-linked).
- UC-24: Idempotency (`record_verify_state`).
- UC-25: Compounding (the verdict is FTS-searchable + the `verifies` backlink exists).

## Task Goal
Complete `apply` by self-indexing the one verdict page — **R-8.4 + R-8.6 (apply half)**. Use a **direct `upsert_page` + `replace_refs` on a single repo connection** (NOT `index_from_manifest`→`main(argv)`, the open H-PERF-3/P-8 N+1; a verdict page is exactly one page). Reuse `reindex._build_page` + the `_frontmatter_refs` helper (008-03) so the `apply`-written rows are **byte-identical** to what `wiki-reindex --full` rebuilds (the UC-26 §D8 symmetry).

## Changes Description

### Changes in Existing Files

#### File: `scripts/wiki_skills/wiki_verify_multi.py`
- In `apply(args)`, after the successful Class A write (008-06), add the index step on **one** repo connection:
  - Build the `pages` row via `reindex._build_page(...)` over the just-written `_verifications/<slug>.md` (reuse the reindex page-build so the row matches a full reindex byte-for-byte — the Q-007-2 symmetry rationale). `upsert_page(page)` (`type='verification'`).
  - Build the refs via `_frontmatter_refs("verification", updated_fm, …)` (008-03) — the `verifies` ref (+ optional `cited`) — plus any body `mentioned` refs the rendered `## Sources` list produces (via the normal body-wikilink extraction, so `apply` and reindex agree). `replace_refs(vault_id, verification_slug, project, refs)` — **one call** (no second `replace_refs`).
  - `record_verify_state(vault_id, verification_slug, verify_hash)` (008-04).
  - `append_log_event(event_type='verify', subject=verification_slug, …)` — record the `verdict`, `verifies` target, and `--orchestrator-id` in `details_json` for provenance (default `"orchestrator"` + `logger.warning`).
  - Update the success envelope → `page_indexed: true`.
- The verdict exit code (008-06: exit 6 on FAIL) is preserved — indexing happens regardless of PASS/FAIL (the audit trail is the value), then the verdict exit code is returned.

### Component Integration
After `apply`, the verdict page is a `pages` row (`type=verification`), a `verifies` `page_entity_ref` to the query page, a `source_state` row, and a `verify` log event — and is immediately FTS-searchable (`wiki-search --types verification`). `wiki-reindex --full` (008-09) rebuilds the identical rows from Class A markdown alone.

## Test Cases

### End-to-end Tests
1. **TC-E2E-01 (indexed):** after `apply` (PASS), the `pages` row `type='verification'` exists with the right `verifies:` frontmatter; `wiki-search <q> --types verification` returns it.
2. **TC-E2E-02 (verifies ref):** a `page_entity_refs` row `(verification_slug, query_slug, 'verifies')` exists after `apply`.
3. **TC-E2E-03 (log event):** one `log_events` row `event_type='verify'`, subject = `verification_slug`, `details_json` carries the verdict + `--orchestrator-id`.
4. **TC-E2E-04 (verify-state recorded):** `check_verify_state` returns the `verify_hash` after `apply`; a subsequent `prepare` → `is_unchanged: true`.
5. **TC-E2E-05 (FAIL still indexed):** a FAIL `apply` → page indexed + `verifies` ref written **and** exit 6 (indexing is independent of the verdict).
6. **TC-E2E-06 (no N+1):** assert `apply` does not invoke `index_from_manifest`/`wiki_index_upsert.main` (e.g. one `upsert_page` + one `replace_refs` call — spy/patch count).

### Unit Tests
1. **TC-UNIT-01 (byte-identical rows):** the `pages` row + refs written by `apply` equal those produced by `reindex._build_page` + `_frontmatter_refs` on the same file (the §D8 symmetry the 008-09 acceptance leans on).

### Regression Tests
- `prepare` + the 008-06 write-side behavior unchanged; full `pytest` green.

## Acceptance Criteria
- [ ] `apply` self-indexes the verdict page via direct `upsert_page` + a single `replace_refs` on one connection (no manifest/`main(argv)` N+1).
- [ ] `verifies` ref written; `verify` log event with `--orchestrator-id` provenance; `record_verify_state` called.
- [ ] Rows are byte-identical to a `reindex._build_page` rebuild (§D8 symmetry).
- [ ] FAIL verdict still indexes (exit 6 preserved); full `pytest` green; `mypy --strict` clean.

## Notes
Stub-First: Phase-1 the index step stubbed (file written, not indexed) + RED tests asserting the `pages` row / ref / log event absent → present; Phase-2 the direct-DAL index. Depends on 008-06 (write-side), 008-04 (verify-state DAL), **008-03** (the `_frontmatter_refs("verification", …)` helper TC-UNIT-01 + the ref-build reuse — adversarial-plan finding DEC-2; 008-03 must land first or `from scripts.wiki_index.reindex import _frontmatter_refs` won't resolve), 008-01 (schema admits `type=verification`/`verifies`/`verify`), 008-02 (`_build_page`'s `normalize_frontmatter` maps the type). Mirrors TASK 007's 007-06.
