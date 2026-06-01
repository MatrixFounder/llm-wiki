---
id: DF-1
type: known-issue
status: fixed
opened_at: 2026-05-29
category: dogfood
slug: df-1-wiki-search-crashes-on-a-hyphenated-bare-query
---

# wiki-search crashes on a hyphenated bare query

- **Symptom**: `wiki-search "hermes-agent" --no-expand-aliases` raised an unhandled `sqlite3.OperationalError: no such column: agent` (exit 1 + stack trace). FTS5 reads the unquoted hyphen as a NOT/column operator. (The default path masks it — alias expansion quotes the terms.)
- **Root cause**: the raw user query was passed to `search_pages` as an FTS5 MATCH expression with no escaping (pre-existing; `search_pages` docstring delegates escaping to the caller).
- **Affected components**: `scripts/wiki_skills/wiki_search.py::main`.
- **Resolution**: on `sqlite3.OperationalError`, retry the query as a literal quoted phrase (`_fts_quote`); a genuinely un-parseable query yields a clean `INVALID_QUERY` envelope (exit 2) instead of a stack trace. Regression: `tests/test_dogfood_fixes.py::test_df1_search_hyphenated_query_does_not_crash`.
