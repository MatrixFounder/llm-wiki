# Task 001-18: Lint queries — orphan_links, drift (with §6.1 type-mapping), cross_vault_concept_duplicates [LOGIC IMPLEMENTATION]

## Use Case Connection
- UC-04 (`wiki-lint` SQL checks)
- R-29 (cross-vault duplicate detection)

## Task Goal
Implement `find_orphan_links`, `find_pages_missing_in_index`, `check_drift`, `find_cross_vault_concept_duplicates` on `SQLiteRepository`. Drift check MUST apply [TASK.md §6.1](../TASK.md) type-mapping (file `lesson-summary` + DB `summary` + tag is intentional, NOT drift).

## Changes Description

### New Files
None.

### Changes in Existing Files

#### File: `scripts/wiki_index/sqlite_repository.py`

**Method `find_orphan_links(self, vault_id: str | None = None) -> list[OrphanLink]`:**
- Query:
  ```sql
  SELECT r.vault_id, r.page_slug, r.page_project, r.entity_slug, r.line_start, r.source_quote
  FROM page_entity_refs r
  LEFT JOIN entities e ON e.vault_id = r.vault_id AND e.slug = r.entity_slug
  LEFT JOIN pages p ON p.vault_id = r.vault_id AND p.slug = r.entity_slug
  WHERE e.slug IS NULL AND p.slug IS NULL
  ```
  + optional `AND r.vault_id = ?` if `vault_id` provided.
- Map rows to `OrphanLink` dataclasses.

**Method `find_pages_missing_in_index(self, vault_id: str, vault_root: Path) -> list[Path]`:**
- Walk filesystem under `vault_root/{_sources,_concepts,_entities}/` and `vault_root/Lessons/*/`.
- For each .md file found, compute its expected slug (filename stem).
- Compare with `SELECT slug FROM pages WHERE vault_id = ?`.
- Return Paths present on disk but absent from DB.

**Method `check_drift(self, vault_id: str) -> DriftReport`:**
- Walk filesystem (as above) → for each file compute current `file_hash` + parse frontmatter `type`.
- Query DB: `SELECT slug, project, type, file_hash, frontmatter_json FROM pages WHERE vault_id = ?`.
- For each pair: detect `missing_in_db`, `missing_on_disk`, `hash_mismatch`, `type_mismatch`.
- **CRITICAL §6.1 mapping**: if `file_type == 'lesson-summary'` AND `db_type == 'summary'` AND `json_extract(frontmatter_json, '$.tags')` contains `'lesson-summary'` → NOT drift. Same for `summary-light` and `meeting-summary`.
- Helper: `_is_intentional_mapping(file_type, db_type, db_tags) -> bool` encoding the mapping table.
- Return `DriftReport(...)`.

**Method `find_cross_vault_concept_duplicates(self) -> list[tuple[str, list[str]]]`:**
- Query:
  ```sql
  SELECT slug, GROUP_CONCAT(vault_id, ',') as vaults, COUNT(DISTINCT vault_id) as n
  FROM entities
  WHERE type = 'concept'
  GROUP BY slug
  HAVING n > 1
  ORDER BY slug
  ```
- Map to `[(slug, vaults.split(','))]`.

### Component Integration
- All four methods consumed by `wiki-lint` CLI (task-001-29).
- `check_drift` runs after `find_pages_missing_in_index` to differentiate missing-on-disk vs hash-changed.

## Test Cases

### End-to-end Tests
1. **TC-E2E-01**: On multi-vault fixture with shared `shadow-ai.md` concept → `find_cross_vault_concept_duplicates` returns `[('shadow-ai', ['vault-alpha', 'vault-beta'])]`.
2. **TC-E2E-02**: Orphan link to nonexistent concept → reported.
3. **TC-E2E-03**: Drift: file has `type: lesson-summary`, DB has `type='summary'` with tag `'lesson-summary'` → **NOT** reported as drift (§6.1 mapping).
4. **TC-E2E-04**: Drift: file has `type: lecture-notes` (unmapped) AND DB has `type='summary'` (no tag) → reported as `type_mismatch`.

### Unit Tests
1. **TC-UNIT-01**: `_is_intentional_mapping` covers all three rows of §6.1 (`summary-light`, `lesson-summary`, `meeting-summary`).
2. **TC-UNIT-02**: Orphan query handles vault filter.
3. **TC-UNIT-03**: Performance: lint on 1000-doc fixture < 2s (SLO per [TASK.md §5.1](../TASK.md)).
4. **TC-UNIT-04**: M-5 (architecture review): cross-vault duplicate query uses index on `(type, slug)` (verify EXPLAIN QUERY PLAN).
5. **TC-UNIT-05**: Lint on single-vault fixture (no duplicates) returns `[]`.

### Regression Tests
- task-001-16 upsert tests still pass.
- E2E harness updated to assert lint output structure.

## Acceptance Criteria
- [ ] All four methods implemented per spec.
- [ ] §6.1 type-mapping correctly applied in `check_drift`.
- [ ] Cross-vault duplicate detection works on multi-vault fixture.
- [ ] Latency SLO met (TC-UNIT-03).
- [ ] All TC tests pass.

## Notes
- TASK.md UC-04 AC: "On vault with orphan link `[[Школа менеджмента Стратоплан]]` → report contains exact line." — exercise via fixture text.
- The type-mapping table is the single source of truth — keep `_is_intentional_mapping` in sync with §6.1 if/when extended (Schema Change Request workflow).
- M-5: EXPLAIN QUERY PLAN should show `SEARCH entities USING INDEX ...` for the cross-vault duplicate query.
