# task-013-01 — DAL: `search_pages` where_fields + query-optional + non-FTS path

**Parent:** TASK 013. **Depends on:** 013-00 (anchor green). **RTM:** R-MF-1,2,3,4,5,6,7,10.

## Goal
Teach the DAL to filter by frontmatter metadata as a **predicate** over the
already-stored `pages.frontmatter_json`, with a query-less (non-FTS) path. Zero DDL.

## Design (locked — ARCHITECTURE.md §11a Q-013-b/c/d)
- Signature: `search_pages(self, query: str | None, *, vaults=None, types=None,
  exclude_types=None, project=None, where_fields: list[tuple[str, str]] | None = None,
  limit=20)`.
- **MATCH term present** (`query` truthy): today's `pages_fts JOIN pages` path,
  append `AND json_extract(p.frontmatter_json, ?) = ?` per filter (path param
  `'$.'+field`, value param). Order unchanged (BM25).
- **Query empty + ≥1 `where_fields`**: non-FTS path —
  `SELECT <same page columns>, NULL AS bm25_score, '' AS snip FROM pages p
   WHERE 1=1 [AND vault IN …][AND type IN …][AND project=?] AND <json_extract preds>
   ORDER BY p.project, p.slug LIMIT ?`. (No `pages_fts`, no `bm25()`.)
- **Both empty**: caller contract — `search_pages` requires a `query` OR
  `where_fields`; raise `ValueError` (the CLI converts to a usage error before
  calling, but the DAL defends).
- Shared `validate_filter_field(field) -> str` (regex `^[a-z][a-z0-9_]*$`,
  raises `ValueError`) re-applied in the DAL on each `where_fields` entry
  (library-caller defense). Value is NEVER validated/escaped — it is a bound
  parameter (any string, incl. `SEV-2`, quotes, is safe).

## Stub-First
1. **Stub**: add `where_fields` param to the ABC (`repository.py`) + the
   `SQLiteRepository` impl; initially ignore it (or `raise NotImplementedError`
   on the non-FTS branch). Write a **RED** E2E test:
   `wiki-search`-equivalent call with `where_fields=[('status','open')]` expects
   only open pages.
2. **Green**: implement the predicate building + FTS/non-FTS branch + ordering +
   field re-validation. RED → GREEN.
3. **Unit tests**:
   - `where_fields` AND semantics (two filters intersect).
   - field absent on a page → `json_extract` NULL → page excluded (no error).
   - hyphenated value `('severity','SEV-2')` returns SEV-2 rows (equality path).
   - query-less path returns rows ordered `(project, slug)` (lock the order).
   - query-less path emits `bm25_score = None`/`0.0` consistently (define + test).
   - **injection**: `('a;DROP TABLE',  'x')` → `ValueError` (field reject);
     `('status', "' OR 1=1 --")` → 0 rows, no error (value parameterized).

## Acceptance
- ✅ FTS query + `where_fields` intersect correctly (R-MF-1,2).
- ✅ `SEV-2` works via equality, not FTS (R-MF-3).
- ✅ Query-less listing returns rows, deterministic order (R-MF-4,5).
- ✅ Field allowlist rejects metacharacters; value fully parameterized (R-MF-6,7).
- ✅ `PRAGMA user_version` still 5; no schema migration (R-MF-10).
- ✅ 013-00 anchor still byte-identical; mypy strict clean.

## Files
- `scripts/wiki_index/repository.py` (ABC signature)
- `scripts/wiki_index/sqlite_repository.py` (`search_pages` + field re-validate)
- `scripts/wiki_skills/_retrieval.py` or `_common.py` (`validate_filter_field`)
- `tests/test_wiki_search_metadata_filter.py` (DAL-level tests)
