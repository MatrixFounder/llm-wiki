---
id: DF-V1
type: known-issue
status: fixed
opened_at: 2026-05-29
category: dogfood
slug: df-v1-verdict-page-pages-pk-collides-with-the-audited-query-page
---

# verdict-page `pages` PK collides with the audited query page

- **Symptom**: filing a verdict page overwrote the audited query page's `pages`
  row — after `wiki-verify-multi apply`, `get_page(query-slug, _vault_)` returned
  `type=verification` and the query row was gone (the compounding loop broke;
  `wiki-search`/re-`prepare` could no longer find the query).
- **Root cause**: the `pages` PK `(vault_id, slug, project)` is **subdir-independent**.
  The plan defaulted `verification_slug = query_slug` + filed at
  `_verifications/<query-slug>.md`, indexing as `(query-slug, _vault_, verification)`
  — the **same PK** as the query page `(query-slug, _vault_, query)`, so
  `upsert_page` (INSERT OR REPLACE on the PK) clobbered the query row. All four
  pre-impl gates (task/architecture/plan/adversarial) missed it; the 008-07
  strict-TDD test (`test_verify_state_recorded_then_unchanged`) surfaced it.
- **Affected**: `scripts/wiki_skills/wiki_verify_multi.py::prepare` (slug default).
- **Resolution (operator-approved STOP-and-decide)**: `verification_slug` defaults
  to **`verify-<query-slug>`** → file `_verifications/verify-<query-slug>.md`, a
  distinct `pages` PK; `verifies:` still points at `_vault_/<query-slug>`.
  Regression: `tests/test_wiki_verify_index.py::test_query_page_row_survives_verification`
  (both rows coexist) + the §D8 round-trip (`test_verify_durability.py`).
