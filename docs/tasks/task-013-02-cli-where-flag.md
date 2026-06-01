# task-013-02 — CLI: `--where` / `--status` / `--severity`, query-optional, INVALID_FILTER

**Parent:** TASK 013. **Depends on:** 013-01. **RTM:** R-MF-1,2,6,8 + UC-1/2/3.

## Goal
Expose the metadata filter on `wiki-search`: the general repeatable
`--where 'field=value'` primitive plus `--status`/`--severity` sugar, with an
optional positional query (query-less listing) and an injection-safe error path.

## Design (locked — ARCHITECTURE.md §11a Q-013-a)
- Positional `query` → `nargs='?'`, default `None`.
- `--where` → `action='append'`, metavar `FIELD=VALUE`, repeatable.
- `--status <v>` / `--severity <v>` → desugar to `where_fields` entries
  `('status', v)` / `('severity', v)` (appended to any `--where`).
- Shared `parse_where(expr) -> (field, value)`: split on the **first** `=`;
  `validate_filter_field(field)`; empty field or no `=` → raise.
- Build `where_fields: list[tuple[str,str]]`. 
- **Refusal**: if `query` is falsy AND `where_fields` empty → usage error,
  `INVALID_QUERY`/usage envelope exit 2 (a bare `wiki-search` is meaningless).
- **Query-less path**: when `query` is falsy, skip `_expand_query` (alias
  expansion) and the DF-1 FTS-quote fallback entirely; call
  `repo.search_pages(None, …, where_fields=where_fields)`.
- **Errors**: a bad `--where`/field → `INVALID_FILTER` envelope (exit 2) naming
  the field key only — **never** echo the value (CWE-209/117; mirror the family's
  `test_*_never_echo_content` pattern).

## Stub-First
1. **Stub**: add the three args + the `parse_where` import; route through but
   leave `where_fields` unused → write a **RED** E2E:
   `main(["--status","open","--types","known-issue","--vaults","…","--db-path","…"])`
   expects only open-status hits.
2. **Green**: implement parsing/desugar/refusal/query-less wiring. RED → GREEN.
3. **Unit tests**:
   - `--status open` desugars to `where_fields=[('status','open')]`.
   - `--where 'status=open' --where 'severity=SEV-2'` → both, AND.
   - malformed `--where foo` (no `=`) → `INVALID_FILTER` exit 2.
   - bare `wiki-search` (no query, no filter) → usage exit 2.
   - error envelope for `--where 'x= secret'`-style never contains the value
     (`test_search_filter_envelope_never_echoes_value`).
   - `--where` composes with `--types`/`--project` (UC-3).
   - query-less call does not invoke alias expansion (no crash on empty query).

## Acceptance
- ✅ `--where`/`--status`/`--severity` produce correct filtered results (UC-1/3).
- ✅ Query-less `--where` listing works (UC-2).
- ✅ Repeatable `--where` → AND (R-MF-2).
- ✅ Field allowlist enforced at CLI; `INVALID_FILTER` never echoes value (R-MF-6,8).
- ✅ Output schema byte-identical when no metadata flag (013-00 anchor green).
- ✅ mypy strict clean.

## Files
- `scripts/wiki_skills/wiki_search.py` (args + parse + desugar + query-less wiring)
- shared `parse_where` (next to `validate_filter_field` from 013-01)
- `tests/test_wiki_search_metadata_filter.py` (CLI-level tests)
