# Task 001-30: `wiki-reindex --full --vault <id>` impl [LOGIC IMPLEMENTATION]

## Use Case Connection
- UC-05 (validates full migration)
- Phase 3a rebuildability invariant (ADR-002 §D8 Class A → B reconstruction)

## Task Goal
Replace `wiki-reindex --full` stub with the rebuildability proof impl: walk vault filesystem (both tiers: root + `Lessons/<course>/`), parse every concept/entity/source page, populate `pages` + `entities` + `page_entity_refs` from frontmatter + body, parse existing `log.md` blocks → repopulate `log_events` rows (with `log_md_byte_offset`), rebuild FTS5 index, emit synthetic `reindex` log event.

## Changes Description

### New Files
- `scripts/wiki_index/reindex.py`:
  - `def discover_pages(vault_root: Path) -> list[tuple[Path, str, str]]:` — walks both tiers:
    - Root tier: `<vault>/{_sources,_concepts,_entities}/*.md` → project = `'_vault_'`.
    - Course tier: `<vault>/Lessons/<course>/{_sources,_concepts,_entities,*}.md` and `<vault>/Lessons/<course>/<other>/*.md` → project = `kebab(course)`.
    - Returns `[(path, slug, project), ...]`.
  - `def reindex_full(repo: IndexRepository, vault_id: str) -> dict:` — orchestrates:
    1. `vault = repo.get_vault(vault_id)`; abort if None.
    2. `run_id = repo.begin_batch_run(vault_id, 'full')`.
    3. `BEGIN IMMEDIATE` (single big transaction for atomic rebuild).
    4. `DELETE FROM pages WHERE vault_id=?`; `DELETE FROM entities WHERE vault_id=?`; `DELETE FROM page_entity_refs WHERE vault_id=?`; `DELETE FROM log_events WHERE vault_id=?`.
    5. Walk filesystem via `discover_pages(vault_root)`.
    6. For each `(path, slug, project)`:
       - Build `SourceItem(kind='manual', source_path=path, vault_root=vault_root, vault_id=vault_id, extra={})`.
       - Reuse `ManualSourceAdapter().fetch(item)` (same path as `wiki-index-upsert`).
       - Apply normalization (R-07.4, R-07.5).
       - Build `Page`; call `repo.upsert_page(page)`.
       - Build refs; call `repo.replace_refs(...)`.
       - Also: if path is under `_concepts/` or `_entities/`, register an `Entity` row.
    7. Parse `<vault>/00-Vault-Index/log/*.md` (or top-level `<vault>/log.md`) via `parse_log_md`; reconstruct `LogEvent` rows; call `repo.append_log_event(...)` for each; populate `log_md_byte_offset` from parsed offsets.
    8. `repo.finish_batch_run(run_id, 'success', notes=f'pages={N} entities={M} log_events={K}')`.
    9. Append synthetic log_event: `LogEvent(event_type='reindex', subject='full', ...)`.
    10. Commit.

### Changes in Existing Files

#### File: `scripts/wiki_skills/wiki_reindex.py`

**Function `main()`:**
- Args: `--full`, `--vault <id>`.
- `config = load_config()`; `repo = make_repo(config)`.
- Call `reindex_full(repo, args.vault)`.
- JSON output: `{"action": "reindexed", "vault_id": ..., "pages": N, "entities": M, "log_events": K, "duration_seconds": T}`.

### Component Integration
- This is the proof of ADR-002 §D8 Class A → B reconstruction.
- Used in task-001-34 e2e rebuildability test (`rm global.db && wiki-init --register-existing && wiki-reindex --full && wiki-search` returns identical results).

## Test Cases

### End-to-end Tests
1. **TC-E2E-01**: Reindex on `minimal_vault` → all 3 pages present in DB; FTS5 search returns them.
2. **TC-E2E-02**: Reindex on `multi_vault/vault-alpha` (two-tier) → both root and course-local pages present; project values differ.
3. **TC-E2E-03**: **Rebuildability**: ingest 3 files → query → delete DB → register-existing → reindex --full → query → identical results (modulo `registered_at`).
4. **TC-E2E-04**: log.md → log_events round-trip: pre-existing log.md with 3 events → after reindex, 3 rows in `log_events` with matching offsets.

### Unit Tests
1. **TC-UNIT-01**: `discover_pages` finds both root and course-tier files.
2. **TC-UNIT-02**: Course-derived project name is kebab-slugified.
3. **TC-UNIT-03**: Atomic rebuild: simulated failure mid-walk → DB remains in pre-reindex state (BEGIN IMMEDIATE rolled back).
4. **TC-UNIT-04**: Latency: reindex on 1K-page fixture < 20s (SLO).
5. **TC-UNIT-05** (I-5 fix — mentions_count idempotency): After reindex, for every entity row `entities.mentions_count == (SELECT COUNT(*) FROM page_entity_refs WHERE vault_id=entities.vault_id AND entity_slug=entities.slug)`. Reindex MUST recompute this field in the same transaction (after all `page_entity_refs` are populated). Without this, the rebuildability invariant breaks: pre/post-delete-rebuild `mentions_count` would drift, failing task-001-34 TC-E2E-01 false-positive.

### Regression Tests
- task-001-25 single-file upsert still works.

## Acceptance Criteria
- [ ] `discover_pages` covers both promotion-spec tiers.
- [ ] Atomic rebuild verified.
- [ ] log.md ↔ log_events round-trip verified (TC-E2E-04).
- [ ] Rebuildability test green (TC-E2E-03).
- [ ] **`entities.mentions_count` recomputed in same transaction** as page_entity_refs population (TC-UNIT-05). I-5 fix — without this, rebuildability gate (task-001-34) gives false-positive.
- [ ] SLO met.

## Notes
- This task IS the Class A → B reconstruction proof. Quality here defines the entire invariant from ADR-002 §D8.
- The atomic rebuild via single transaction may not scale to 100K+ files; if benchmark task (001-33) flags it, swap to chunked-transaction strategy. Phase 3a SLO is 1K-10K, well within single-tx capacity.
- `log_md_byte_offset` for reconstructed log_events comes from `parse_log_md` (task-001-27).
