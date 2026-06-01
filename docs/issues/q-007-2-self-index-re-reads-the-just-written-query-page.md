---
id: Q-007-2
type: known-issue
status: open
opened_at: 2026-05-29
category: quality
severity: SEV-3
slug: q-007-2-self-index-re-reads-the-just-written-query-page
---

# self-index re-reads the just-written query page

- **Symptom**: `_index_query_page` re-reads + re-parses `_queries/<slug>.md` via
  the `ManualSourceAdapter` rather than indexing the in-memory content `apply`
  just wrote.
- **Root cause**: deliberate — reusing the reindex page-build (`_build_page` +
  `_cited_refs_from_frontmatter`) guarantees the apply-written `pages`/refs rows
  are **byte-identical** to what `wiki-reindex --full` rebuilds (the UC-20 §D8
  symmetry, `test_wiki_query_durability.py`). One extra file read per `apply`.
- **Affected**: `scripts/wiki_skills/wiki_query.py::_index_query_page`.
- **Fix plan**: keep — the durability-symmetry guarantee outweighs one re-read.
