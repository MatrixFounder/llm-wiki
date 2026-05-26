# Task 001-17: `SQLiteRepository.search_pages` — FTS5 + BM25 + `--vaults` filter [LOGIC IMPLEMENTATION]

## Use Case Connection
- UC-03 (`wiki-search`)
- R-29 (cross-vault search)

## Task Goal
Implement `search_pages(query, *, vaults=None, types=None, project=None, limit=20)` returning `list[PageHit]` ordered by BM25 ascending (lower = more relevant). Snippet uses explicit FTS5 `snippet()` args with `<b>...</b>` highlighting.

## Changes Description

### New Files
None.

### Changes in Existing Files

#### File: `scripts/wiki_index/sqlite_repository.py`

**Method `search_pages(self, query: str, *, vaults: list[str] | None = None, types: list[str] | None = None, project: str | None = None, limit: int = 20) -> list[PageHit]`:**

- Build base SQL:
  ```sql
  SELECT p.vault_id, p.slug, p.project, p.type, p.title, p.tldr, p.date, p.last_modified,
         p.file_hash, p.frontmatter_json, p.body_excerpt,
         bm25(pages_fts) AS bm25_score,
         snippet(pages_fts, -1, '<b>', '</b>', '...', 16) AS snip
  FROM pages_fts
  JOIN pages p ON pages_fts.rowid = p.rowid
  WHERE pages_fts MATCH ?
  ```
- Append filters dynamically (parameterized):
  - `AND p.vault_id IN (?, ?, ...)` if `vaults` provided (uses `vault_id IN (...)`); if None → no filter (all registered vaults).
  - `AND p.type IN (?, ?, ...)` if `types` provided.
  - `AND p.project = ?` if `project` provided.
- `ORDER BY bm25_score ASC LIMIT ?`.
- Construct `Page` from row; wrap with `PageHit(page=..., bm25_score=row['bm25_score'], snippet=row['snip'])`.
- Return list.

**Helper `_build_in_clause(name: str, values: list[str]) -> tuple[str, list[str]]`:**
- Returns `(f"{name} IN ({','.join(['?']*len(values))})", values)`. Avoids SQL injection via f-string IN-list patterns.

### Component Integration
- Called from `wiki-search` CLI (task-001-28).
- `--vaults all` in CLI → pass `vaults=None` (all-registered behavior).
- `--vaults vault-alpha,vault-beta` → pass `['vault-alpha', 'vault-beta']`.

## Test Cases

### End-to-end Tests
1. **TC-E2E-01**: Search "shadow ai" on multi-vault fixture → hits from both `vault-alpha` and `vault-beta` (R-29 cross-vault).
2. **TC-E2E-02**: Search with `vaults=['vault-alpha']` → only `vault-alpha` hits.
3. **TC-E2E-03**: Snippet contains explicit `<b>` and `</b>` markers.
4. **TC-E2E-04**: Empty result set → returns `[]`.

### Unit Tests
1. **TC-UNIT-01**: `--type summary` filters to summary-type pages only.
2. **TC-UNIT-02**: `--project _vault_` filters correctly.
3. **TC-UNIT-03**: BM25 ordering: result list is sorted by `bm25_score` ascending.
4. **TC-UNIT-04**: FTS5 query escaping: query `"foo*"` (with quotes) is passed verbatim — FTS5 native syntax.
5. **TC-UNIT-05**: SQL injection: query `"'; DROP TABLE pages--"` does not drop the table (FTS5 MATCH parameterized).
6. **TC-UNIT-06**: Performance: search on 1000-doc fixture < 50ms (SLO per [TASK.md §5.1](../TASK.md)).

### Regression Tests
- task-001-16 upsert tests still pass.

## Acceptance Criteria
- [ ] Method implemented per spec.
- [ ] BM25 ordering ascending (lower = better in SQLite FTS5).
- [ ] Snippet uses explicit `<b>...</b>` and `'...'` ellipsis (verified in TC-E2E-03).
- [ ] `--vaults` filter works as documented.
- [ ] All TC tests pass.
- [ ] Latency SLO met on 1K-doc fixture.

## Notes
- FTS5 `snippet()` signature: `snippet(table, col_idx, '<b>', '</b>', '...', tokens)`. `col_idx=-1` means "first matching column".
- UC-03 AC requires explicit `<b>/</b>` arguments — do not rely on defaults.
- Cross-vault search (R-29) is just a soft semantics over the same query; no separate code path.
