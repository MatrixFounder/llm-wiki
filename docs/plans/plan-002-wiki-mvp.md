# Development Plan: LLM Wiki MVP — Phase 3a (Foundation + DAL + Core Ingest + Search/Lint + Reindex + Benchmark)

> **Status**: COMPLETE (2026-05-26). All 34 tasks landed; 274 tests pass; mypy strict clean; rebuildability E2E gate green. Phase 3b still blocked on `wiki-ingest` v1.1 release.
> **Task ID**: 001 / Slug: `wiki-mvp`
> **Methodology**: Stub-First (TDD). Stage 1 creates structure + stubs + E2E asserting hardcoded values; Stage 2 replaces stubs with real logic; Stage 3 runs benchmark + e2e validation.
> **Source artefacts**: [TASK.md](./TASK.md) (RTM section 2), [SCHEMA-v2.sql](./SCHEMA-v2.sql), [ADR-001](./adr/ADR-001-wiki-ingest-integration.md), [ADR-002](./adr/ADR-002-multi-vault-bottleneck-corrections.md), [reviews/architecture-review-pre-phase3a-2026-05-26.md](./reviews/architecture-review-pre-phase3a-2026-05-26.md).
> **RTM coverage (Phase 3a)**: R-01, R-02, R-03, R-04, R-05, R-06.1, R-06.2, R-07 (R-07.1/.2/.3/.4/.5), R-08, R-09, R-10, R-11, R-13, R-14, R-15.3, R-25 (superseded by `vaults`), R-26, R-27 (multi-vault), R-28 (log_events), R-29 (cross-vault search+lint).
> **Out of Phase 3a**: R-06.3 (transcript), R-12 (`ingest-source` meta-workflow), R-24 (`wiki-light-summary`), R-15 LLM-coupled trust_level paths, promotion/demotion, full file-level lint (delegate to wiki-ingest v1.1).

---

## 0. Architectural foundation (reference)

| Layer | Owns | Class (ADR-002 §D8) |
|---|---|---|
| **Markdown vault** (Obsidian + iCloud) | All semantic content: concept/entity/source pages, frontmatter, wiki-links, footnotes, log.md, index.md | Class A — canonical |
| **wiki-ingest** (external skill, v1.1 release pending) | File-level CRUD: additive merge, footnote rendering, file-level lint, promote/demote | Layer between vault and DB |
| **This Phase 3a deliverable** (`obsidian-llm-wiki/`) | SQLite multi-vault index, FTS5 search, SQL-level lint, `vaults` registry, structured `log_events`, reindex from disk | Class B (cache) + Class C (operational metadata) |

**Rebuildability invariant**: `rm global.db && wiki-init --register-existing --vault <path> && wiki-reindex --full --all-vaults` восстанавливает БД без потери семантики; только `vaults.registered_at` теряет exact timestamp (approximated from `MIN(log_events.event_ts)`).

---

## 1. Task Execution Sequence

### Stage 1 — Structure & Stubs ([STUB CREATION])

Create file structure, class definitions, method signatures, and stubs (`NotImplementedError` / hardcoded values). Each stub task is paired with E2E tests asserting hardcoded behavior.

- [R-02] Apply `sql/wiki-index-v2.sql` (copy from SCHEMA-v2.sql) + smoke test
  - Description File: [docs/tasks/task-001-01-apply-schema-v2.md](./tasks/task-001-01-apply-schema-v2.md)
  - Priority: Critical
  - Dependencies: none

- [R-01] Repo structure scaffolding + `requirements.txt` + JSON Schema stub for `wiki:` config
  - Description File: [docs/tasks/task-001-02-repo-scaffolding-and-config-schema.md](./tasks/task-001-02-repo-scaffolding-and-config-schema.md)
  - Priority: Critical
  - Dependencies: none

- [R-04] `IndexRepository` abstract base + dataclasses (`Page`, `Entity`, `PageHit`, `LogEvent`, `Vault`, `OrphanLink`, `BatchRun`)
  - Description File: [docs/tasks/task-001-03-repository-abstract-base.md](./tasks/task-001-03-repository-abstract-base.md)
  - Priority: Critical
  - Dependencies: task-001-02

- [R-04] `SQLiteRepository` skeleton — all methods raise `NotImplementedError`
  - Description File: [docs/tasks/task-001-04-sqlite-repository-stub.md](./tasks/task-001-04-sqlite-repository-stub.md)
  - Priority: Critical
  - Dependencies: task-001-03

- [R-04] Factory `make_repo(config)` stub + iCloud-rejection placeholder
  - Description File: [docs/tasks/task-001-05-repo-factory-stub.md](./tasks/task-001-05-repo-factory-stub.md)
  - Priority: High
  - Dependencies: task-001-04

- [R-06.1] `SourceAdapter` abstract base + dataclasses (`SourceItem`, `SourceOutput`)
  - Description File: [docs/tasks/task-001-06-source-adapter-abstract.md](./tasks/task-001-06-source-adapter-abstract.md)
  - Priority: High
  - Dependencies: task-001-02

- [R-06.2] `wiki-source-manual` adapter stub (path-traversal stub returns hardcoded `SourceOutput`)
  - Description File: [docs/tasks/task-001-07-source-manual-stub.md](./tasks/task-001-07-source-manual-stub.md)
  - Priority: High
  - Dependencies: task-001-06

- [R-05, R-08, R-09, R-10, R-11] CLI skill scaffolds: `wiki-init`, `wiki-search`, `wiki-lint`, `wiki-index-render`, `wiki-append-log`, `wiki-index-upsert`
  - Description File: [docs/tasks/task-001-08-cli-skill-scaffolds.md](./tasks/task-001-08-cli-skill-scaffolds.md)
  - Priority: High
  - Dependencies: task-001-03, task-001-04

- [R-14] CLI skill scaffold: `wiki-reindex`
  - Description File: [docs/tasks/task-001-09-wiki-reindex-scaffold.md](./tasks/task-001-09-wiki-reindex-scaffold.md)
  - Priority: High
  - Dependencies: task-001-08

- [R-14] pytest fixtures — minimal-vault + multi-vault synthetic (trade-agents-shaped)
  - Description File: [docs/tasks/task-001-10-pytest-fixtures.md](./tasks/task-001-10-pytest-fixtures.md)
  - Priority: High
  - Dependencies: task-001-01, task-001-02

- [R-14] E2E test harness — asserts stubs return hardcoded values
  - Description File: [docs/tasks/task-001-11-e2e-stub-harness.md](./tasks/task-001-11-e2e-stub-harness.md)
  - Priority: Critical
  - Dependencies: task-001-04, task-001-07, task-001-08, task-001-09, task-001-10

- [R-26] Path-traversal guard utility (`scripts/wiki_index/security.py::validate_inside_vault`)
  - Description File: [docs/tasks/task-001-12-path-traversal-guard.md](./tasks/task-001-12-path-traversal-guard.md)
  - Priority: Critical
  - Dependencies: task-001-02

### Stage 2 — Core Functionality ([LOGIC IMPLEMENTATION])

Replace stubs with real logic; E2E tests updated to assert real values; unit tests added.

- [R-01] `config_loader.py` — `load_config(cwd)` walk-up + deep-merge + JSON Schema validation (fail-fast)
  - Description File: [docs/tasks/task-001-13-config-loader-impl.md](./tasks/task-001-13-config-loader-impl.md)
  - Priority: Critical
  - Dependencies: task-001-02, task-001-11

- [R-03] iCloud detection + platform-default DB path resolver
  - Description File: [docs/tasks/task-001-14-icloud-detection-and-db-path.md](./tasks/task-001-14-icloud-detection-and-db-path.md)
  - Priority: Critical
  - Dependencies: task-001-13

- [R-04, R-27] `SQLiteRepository` — vaults CRUD (`register_vault`, `get_vault`, `list_vaults`) + CASCADE behavior on rename
  - Description File: [docs/tasks/task-001-15-vaults-crud-impl.md](./tasks/task-001-15-vaults-crud-impl.md)
  - Priority: Critical
  - Dependencies: task-001-04, task-001-11

- [R-04, R-07] `SQLiteRepository` — pages CRUD via `ON CONFLICT(vault_id, slug, project) DO UPDATE SET ...` (M-4 contract; NEVER `INSERT OR REPLACE`)
  - Description File: [docs/tasks/task-001-16-pages-upsert-impl.md](./tasks/task-001-16-pages-upsert-impl.md)
  - Priority: Critical
  - Dependencies: task-001-15

- [R-04, R-10, R-29] `SQLiteRepository.search_pages` — FTS5 + BM25 + `--vaults` filter + snippet highlighting
  - Description File: [docs/tasks/task-001-17-search-pages-impl.md](./tasks/task-001-17-search-pages-impl.md)
  - Priority: High
  - Dependencies: task-001-16

- [R-04, R-11, R-29] `SQLiteRepository` — lint queries (orphan_links, drift with §6.1 type-mapping, cross_vault_concept_duplicates)
  - Description File: [docs/tasks/task-001-18-lint-queries-impl.md](./tasks/task-001-18-lint-queries-impl.md)
  - Priority: High
  - Dependencies: task-001-16

- [R-04, R-28] `SQLiteRepository` — `log_events` CRUD (append + slice queries by vault/range/type)
  - Description File: [docs/tasks/task-001-19-log-events-crud-impl.md](./tasks/task-001-19-log-events-crud-impl.md)
  - Priority: High
  - Dependencies: task-001-15

- [R-04] Factory `make_repo(config)` real impl + iCloud-rejection enforcement
  - Description File: [docs/tasks/task-001-20-repo-factory-impl.md](./tasks/task-001-20-repo-factory-impl.md)
  - Priority: High
  - Dependencies: task-001-14, task-001-15

- [R-05] `wiki-init --scaffold-new` flow (interactive `vault_id` prompt, writes `WIKI_SCHEMA.md`, registers vault row, mkdir tree)
  - Description File: [docs/tasks/task-001-21-wiki-init-scaffold-new.md](./tasks/task-001-21-wiki-init-scaffold-new.md)
  - Priority: High
  - Dependencies: task-001-20

- [R-05] `wiki-init --register-existing` flow (reads `WIKI_SCHEMA.md::vault_id`, fail-fast `MISSING_VAULT_ID` per ADR-002 §D1.1)
  - Description File: [docs/tasks/task-001-22-wiki-init-register-existing.md](./tasks/task-001-22-wiki-init-register-existing.md)
  - Priority: High
  - Dependencies: task-001-21

- [R-05] `wiki-init --reconcile` flow (handles `VAULT_RENAMED` per ADR-002 §D8)
  - Description File: [docs/tasks/task-001-23-wiki-init-reconcile.md](./tasks/task-001-23-wiki-init-reconcile.md)
  - Priority: Medium
  - Dependencies: task-001-22

- [R-06.2, R-15.3, R-26] `wiki-source-manual` adapter impl — path-traversal, frontmatter parse, file_hash compute, `trust_level='high'`
  - Description File: [docs/tasks/task-001-24-source-manual-impl.md](./tasks/task-001-24-source-manual-impl.md)
  - Priority: High
  - Dependencies: task-001-12, task-001-20

- [R-07] `wiki-index-upsert` impl — R-07.1/.2/.3 (frontmatter parse + file_hash + single-tx upsert+refs) + R-07.4 (type-mapping §6.1) + R-07.5 (mermaid + SECTION strip with pinned regex, fail-fast on unclosed mermaid fence)
  - Description File: [docs/tasks/task-001-25-wiki-index-upsert-impl.md](./tasks/task-001-25-wiki-index-upsert-impl.md)
  - Priority: Critical
  - Dependencies: task-001-16, task-001-24

- [R-08] `wiki-index-render` impl — query `index_meta` VIEW + preserve custom sections (ADR-002 §D8) + auto-shard > 200 pages + atomic tempfile write
  - Description File: [docs/tasks/task-001-26-wiki-index-render-impl.md](./tasks/task-001-26-wiki-index-render-impl.md)
  - Priority: High
  - Dependencies: task-001-16

- [R-09, R-28] `wiki-append-log` impl — bi-directional sync `log.md` ↔ `log_events` (atomic flock, `log_md_byte_offset` populated, monthly rotation per R-09.1)
  - Description File: [docs/tasks/task-001-27-wiki-append-log-impl.md](./tasks/task-001-27-wiki-append-log-impl.md)
  - Priority: High
  - Dependencies: task-001-19

- [R-10, R-29] `wiki-search` CLI — wrapper over `repo.search_pages` with `--vaults` flag + markdown output
  - Description File: [docs/tasks/task-001-28-wiki-search-cli-impl.md](./tasks/task-001-28-wiki-search-cli-impl.md)
  - Priority: High
  - Dependencies: task-001-17

- [R-11, R-29] `wiki-lint` CLI — SQL-level checks + cross-vault concept duplicates (R-29) + markdown report + JSON sidecar + `--fix` safe operations
  - Description File: [docs/tasks/task-001-29-wiki-lint-cli-impl.md](./tasks/task-001-29-wiki-lint-cli-impl.md)
  - Priority: High
  - Dependencies: task-001-18, task-001-19

- [R-14] `wiki-reindex --full --vault <id>` impl — walks both tiers (root + `Lessons/<course>/`), rebuilds pages/entities/refs/log_events; rebuildability proof
  - Description File: [docs/tasks/task-001-30-wiki-reindex-full-impl.md](./tasks/task-001-30-wiki-reindex-full-impl.md)
  - Priority: Critical
  - Dependencies: task-001-25, task-001-27

- [R-14] `wiki-reindex --delta` impl — mtime-based incremental from `vaults.last_ingest_at`
  - Description File: [docs/tasks/task-001-31-wiki-reindex-delta-impl.md](./tasks/task-001-31-wiki-reindex-delta-impl.md)
  - Priority: High
  - Dependencies: task-001-30

- [R-13] `tmp2/` migration script (`scripts/wiki_migrate_flat_to_folders.py`) — flat → `_sources/<file>.md` + `--dry-run`
  - Description File: [docs/tasks/task-001-32-tmp2-migration-script.md](./tasks/task-001-32-tmp2-migration-script.md)
  - Priority: Medium
  - Dependencies: task-001-25

### Stage 3 — Testing & Benchmark

- [R-14] Benchmark suite — synthetic vault generator (100/1000/10000 docs) + per-operation latency harness + multi-vault scaling test + SLO assertions
  - Description File: [docs/tasks/task-001-33-benchmark-suite.md](./tasks/task-001-33-benchmark-suite.md)
  - Priority: Critical
  - Dependencies: task-001-28, task-001-29, task-001-30, task-001-31

- [R-14] End-to-end rebuildability test — `DELETE global.db` → register-existing → reindex --full → identical query results
  - Description File: [docs/tasks/task-001-34-e2e-rebuildability-test.md](./tasks/task-001-34-e2e-rebuildability-test.md)
  - Priority: Critical
  - Dependencies: task-001-30, task-001-33

---

## 2. Use Case Coverage

| Use Case | Description | Phase 3a Tasks |
|---|---|---|
| **UC-01** | `wiki-init` — bootstrap / register-existing vault | task-001-21, task-001-22, task-001-23 |
| **UC-02** | Manual ingest of existing markdown | task-001-24, task-001-25, task-001-27 |
| **UC-03** | `wiki-search` text search | task-001-17, task-001-28 |
| **UC-04** | `wiki-lint` health-check (SQL-level + cross-vault dup) | task-001-18, task-001-29 |
| **UC-05** | `tmp2/` bulk migration | task-001-32, task-001-25, task-001-26 |
| **UC-06** | `wiki-light-summary` | **Deferred to Phase 3b** (R-24 LLM-coupled) |
| **UC-07** | `wiki-source-transcript` | **Deferred to Phase 3b** (R-06.3 wiki-ingest v1.1) |

---

## 3. RTM Coverage Matrix

| RTM ID | Requirement | Task(s) | Stage |
|---|---|---|---|
| R-01 | Config schema (root + project) + deep-merge + validation | task-001-02 (stub), task-001-13 (impl) | 1, 2 |
| R-02 | SQLite + FTS5 + WAL + triggers | task-001-01 | 1 |
| R-03 | iCloud-aware DB path | task-001-14 | 2 |
| R-04 | `IndexRepository` interface + SQLiteRepository | task-001-03, task-001-04, task-001-05 (stubs), task-001-15..task-001-20 (impl) | 1, 2 |
| R-05 | `wiki-init` 3 modes | task-001-08 (stub), task-001-21, task-001-22, task-001-23 | 1, 2 |
| R-06.1 | `SourceAdapter` abstract | task-001-06 | 1 |
| R-06.2 | `wiki-source-manual` | task-001-07 (stub), task-001-24 (impl) | 1, 2 |
| R-07.1-.5 | `wiki-index-upsert` + type-mapping + body normalization | task-001-08 (stub), task-001-25 (impl) | 1, 2 |
| R-08 | `wiki-index-render` | task-001-08 (stub), task-001-26 (impl) | 1, 2 |
| R-09 | `wiki-append-log` monthly rotation | task-001-08 (stub), task-001-27 (impl) | 1, 2 |
| R-10 | `wiki-search` FTS5/BM25 | task-001-08 (stub), task-001-17 (repo), task-001-28 (CLI) | 1, 2 |
| R-11 | `wiki-lint` SQL-level | task-001-08 (stub), task-001-18 (repo), task-001-29 (CLI) | 1, 2 |
| R-13 | `tmp2/` migration | task-001-32 | 2 |
| R-14 | Benchmark + SLO checker | task-001-09, task-001-33, task-001-34 | 1, 3 |
| R-15.3 | `trust_level` from manual adapter | task-001-24 | 2 |
| R-25 (superseded) | vault registry (now `vaults` table) | task-001-15 | 2 |
| R-26 | Path-traversal + sentinel `'_vault_'` PK | task-001-12, task-001-24 | 1, 2 |
| **R-27** (new) | Multi-vault partitioning | task-001-01 (schema), task-001-15 (vaults CRUD) | 1, 2 |
| **R-28** (new) | `log_events` structured mirror | task-001-19, task-001-27 | 2 |
| **R-29** (new) | Cross-vault search + lint | task-001-17, task-001-18, task-001-28, task-001-29 | 2 |

---

## 4. Phase 3a Exit Criteria

- [x] All Stage 1 tasks complete; E2E stub harness green on hardcoded values
- [x] All Stage 2 tasks complete; E2E updated to assert real values
- [x] Stage 3 benchmark suite implemented (`scripts/benchmark.py`); SLOs measured at N=100 (default CI). N=1000/10000 enforcement deferred — see KNOWN_ISSUES.
- [x] End-to-end rebuildability test passes (task-001-34): `rm global.db` → register-existing → reindex --full → identical search/lint output
- [x] Cross-vault scaling harness implemented (`run_multivault_scaling`); SLO enforcement at 5×1K / 10×5K deferred to nightly.
- [x] `/vdd-multi` Zero-Critical-Open on Phase 3a code (iteration 1 merged 2 CRITICAL + 5 HIGH + 11 MEDIUM → all CRITICAL/HIGH fixed; performance SEV-1 scaling concerns deferred).
- [x] Code review pass per `skill-code-review-checklist`

---

## 5. Open Issues Tracking (from architecture-review-pre-phase3a-2026-05-26)

Aligned 1-1 with original architecture-review M-IDs (do NOT renumber — review reports are source-of-truth).

| Issue | Description | Track in task |
|---|---|---|
| M-1 | `vault_id` GLOB tighten (no trailing/double hyphens) | Schema constraint in task-001-01; defense-in-depth in task-001-15 vaults-CRUD unit tests |
| M-2 | FTS5 `vault_id UNINDEXED` partition pruning under cross-vault scale | Benchmark in task-001-33 (5 vaults × 1K + 10 × 5K); EXPLAIN QUERY PLAN test in task-001-17 |
| M-3 | `idx_pages_vault_tags` functional-index byte-exact match | EXPLAIN QUERY PLAN test in task-001-18 + benchmark task-001-33 |
| M-4 | `ON CONFLICT(vault_id, slug, project) DO UPDATE SET` (NEVER `INSERT OR REPLACE`) | task-001-16 pages-upsert (with grep guard in TC-UNIT) |
| M-5 | `PRAGMA user_version = 2` for migration gating | task-001-01 (DDL + TC-E2E-01 check) |
| M-6 | Drop indexes on out-of-MVP tables (`interactions`, `extracted_items`) | task-001-01 (commented-out indexes + TC-E2E-02 verifies absence) |
| M-7 | `_global_` sentinel vault row + `batch_runs.vault_id NOT NULL` | task-001-15 vaults-CRUD (bootstrap row INSERT) + schema CHECK |
| L-1..L-7 | Low-severity cleanups (entities.file_path UNIQUE invariant docs, log_events.event_date GENERATED column, etc.) | Tracked in [docs/KNOWN_ISSUES.md](./KNOWN_ISSUES.md); batch into single cleanup PR before Phase 3a exit |

**Reindex idempotency invariant** (from architecture review §5 mentions_count drift): task-001-30 (`wiki-reindex --full`) MUST recompute `entities.mentions_count` from `page_entity_refs` for every entity row; rebuildability gate test (task-001-34) verifies. See also task-001-30 Acceptance Criteria.

---

## 6. Development Setup (one-time per developer)

1. `cd ~/dev-projects/obsidian-llm-wiki`
2. `python3 -m venv .venv && source .venv/bin/activate`
3. `pip install -r requirements.txt` (sqlite3 stdlib; add `python-slugify`, `pyyaml`, `python-frontmatter`, `pytest`, `jsonschema`, `mypy`)
4. `sqlite3 /tmp/wiki-test.db < sql/wiki-index-v2.sql` (after task-001-01)
5. `pytest tests/`
6. `python scripts/benchmark.py --n 1000` (after task-001-33)

---

## 7. Start Signal

**Phase 3a is green-lit (2026-05-26)** — start with task-001-01 (apply schema) and task-001-02 (repo scaffolding + config schema stub). Stage 1 tasks may run in parallel after task-001-02 lands.
