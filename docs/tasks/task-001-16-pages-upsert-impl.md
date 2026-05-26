# Task 001-16: `SQLiteRepository` pages CRUD via `ON CONFLICT DO UPDATE` [LOGIC IMPLEMENTATION]

## Use Case Connection
- UC-02 (manual ingest), UC-05 (bulk migration), UC-06 (light summary), UC-07 (transcript)

## Task Goal
Implement `upsert_page`, `get_page`, `delete_page`, `upsert_refs`, `replace_refs`, `get_backlinks` on `SQLiteRepository`. **CRITICAL (M-4 architecture review)**: pages UPSERT MUST use `INSERT INTO pages (...) VALUES (...) ON CONFLICT(vault_id, slug, project) DO UPDATE SET last_modified=excluded.last_modified, file_hash=excluded.file_hash, ...`. **NEVER `INSERT OR REPLACE`** — the latter deletes and re-inserts, triggering FK CASCADE on `page_entity_refs` and breaking referential idempotency.

## Changes Description

### New Files
None.

### Changes in Existing Files

#### File: `scripts/wiki_index/sqlite_repository.py`

**Method `upsert_page(self, page: Page) -> Literal['inserted','updated','unchanged']`:**
- Wrap in `BEGIN IMMEDIATE`.
- Query existing row: `SELECT file_hash FROM pages WHERE vault_id=? AND slug=? AND project=?`.
- If row exists AND `existing_file_hash == page.file_hash` → return `'unchanged'`, no write.
- Otherwise execute:
  ```sql
  INSERT INTO pages (vault_id, slug, project, type, title, tldr, date, last_modified, file_hash,
                     frontmatter_json, body_excerpt)
  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  ON CONFLICT(vault_id, slug, project) DO UPDATE SET
      type=excluded.type,
      title=excluded.title,
      tldr=excluded.tldr,
      date=excluded.date,
      last_modified=excluded.last_modified,
      file_hash=excluded.file_hash,
      frontmatter_json=excluded.frontmatter_json,
      body_excerpt=excluded.body_excerpt
  ```
- Determine `'inserted'` vs `'updated'` by checking pre-row presence.
- Commit; return outcome.

**Method `get_page(self, vault_id: str, slug: str, project: str) -> Page | None`:**
- Standard SELECT; deserialize `frontmatter_json` and derive `tags` from it.

**Method `delete_page(self, vault_id: str, slug: str, project: str) -> None`:**
- `DELETE FROM pages WHERE vault_id=? AND slug=? AND project=?` — schema FK CASCADE removes refs.

**Method `upsert_refs(self, refs: list[PageRef]) -> None`:**
- For each ref: `INSERT INTO page_entity_refs (...) VALUES (...) ON CONFLICT(vault_id, page_slug, page_project, entity_slug, ref_type) DO UPDATE SET line_start=excluded.line_start, line_end=excluded.line_end, source_quote=excluded.source_quote, trust_level=excluded.trust_level`.
- Use `executemany` for batch.

**Method `replace_refs(self, vault_id: str, page_slug: str, page_project: str, refs: list[PageRef]) -> None`:**
- Wrap in `BEGIN IMMEDIATE`.
- `DELETE FROM page_entity_refs WHERE vault_id=? AND page_slug=? AND page_project=?`.
- Bulk-insert `refs` via `executemany`.
- Commit.

**Method `get_backlinks(self, vault_id: str, entity_slug: str) -> list[PageRef]`:**
- `SELECT vault_id, page_slug, page_project, entity_slug, ref_type, line_start, line_end, source_quote, trust_level FROM page_entity_refs WHERE vault_id=? AND entity_slug=? ORDER BY page_slug, line_start`.

### Component Integration
- `replace_refs` is called by `wiki-index-upsert` (task-001-25) after re-parsing wiki-links from body.
- `get_backlinks` is used by `wiki-lint` "missing backlinks" check (task-001-18).
- FTS5 sync is automatic via DDL triggers (defined in SCHEMA-v2.sql) — no Python work.

## Test Cases

### End-to-end Tests
1. **TC-E2E-01**: Insert page → `get_page` returns identical fields (round-trip).
2. **TC-E2E-02**: Re-upsert same `file_hash` → returns `'unchanged'`, no write.
3. **TC-E2E-03**: Re-upsert different `file_hash` → returns `'updated'`, `frontmatter_json` reflects new values.
4. **TC-E2E-04**: After upsert, `pages_fts MATCH 'title-keyword'` returns ≥ 1 hit (FTS5 trigger fired).
5. **TC-E2E-05**: `replace_refs` deletes all prior refs and inserts new ones atomically.

### Unit Tests
1. **TC-UNIT-01**: `INSERT OR REPLACE` is NOT used anywhere in `sqlite_repository.py` (grep test).
2. **TC-UNIT-02**: SQL injection: insert page with title `"'; DROP TABLE pages--"` → table remains.
3. **TC-UNIT-03**: Composite PK enforced: insert same `(vault_id, slug, project)` twice → second call returns `'updated'`, only 1 row in DB.
4. **TC-UNIT-04**: `delete_page` cascades to `page_entity_refs` (FK CASCADE).
5. **TC-UNIT-05**: `replace_refs([])` (empty list) is valid — deletes all without inserting.
6. **TC-UNIT-06**: Backlink query returns refs sorted by `(page_slug, line_start)`.

### Regression Tests
- task-001-15 vaults tests still pass.

## Acceptance Criteria
- [ ] All six methods implemented.
- [ ] **M-4 contract enforced**: grep of `INSERT OR REPLACE` in `sqlite_repository.py` returns 0 lines.
- [ ] FTS5 round-trip verified.
- [ ] All TC tests pass.
- [ ] `mypy --strict` passes.
- [ ] Parameterized queries everywhere (no f-string SQL).

## Notes
- M-4 contract is load-bearing: future regressions to `INSERT OR REPLACE` would break ref idempotency. Add a CI grep guard if convenient.
- `BEGIN IMMEDIATE` (vs `DEFERRED`) prevents deadlock between two writers; UC-02 A5 (concurrent ingest) relies on this.
- `unchanged` outcome enables UC-02 A3 (re-ingest same hash → no extra log row).
