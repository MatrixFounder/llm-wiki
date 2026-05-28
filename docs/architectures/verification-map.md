# Verification Map (TASK requirements ↔ Architecture sections)

> Part of [docs/ARCHITECTURE.md](../ARCHITECTURE.md).

## Verification Map (TASK requirements ↔ Architecture sections)

| TASK Requirement | Architecture coverage | Test/AC reference |
|---|---|---|
| R-01 (config schema) | §3.2 Configuration Resolver, §10.3 | UC-01 AC (CLAUDE.md valid YAML) |
| R-02 (SQLite + FTS5) | §6.3 Database, [SCHEMA-DRAFT.sql](./SCHEMA-DRAFT.sql) | UC-01 AC `journal_mode=wal`; FTS5 contentless mode (post C-1 fix) |
| R-03 (iCloud-aware DB location) | §6.4 / §3.2 wiki-init, §7.2 Data Protection | UC-01 AC «DB path не содержит Mobile Documents/iCloud~» |
| R-04 (DAL) | §3.2 IndexRepository (15 methods), SQLiteRepository | I-2.4 unit tests на minimal vault fixture |
| R-05 (wiki-init) | §3.2 wiki-init component, §10.4 deployment step 7 | UC-01 entire |
| R-06.1 (SourceAdapter contract) | §3.2 SourceAdapter Interface subsection (NEW) | I-3.1 abstract base + base.py module |
| R-06.2 (manual adapter) | §3.2 wiki-source-manual | UC-02 entire |
| R-06.3 (transcript adapter) | §3.2 wiki-source-transcript + Q-A1 resolution required | UC-02 by reference (transcript flow goes through manual chain) |
| R-07 (wiki-index-upsert as standalone skill) | §3.2 wiki-index-upsert (через SQLiteRepository.upsert_page wrapper) | UC-02 step 7 + AC |
| R-08 (wiki-index-render) | §3.2 wiki-index-render component (separate skill, projection generator) | UC-05 step 7 |
| R-09 (wiki-append-log) | §3.2 wiki-append-log component, §9.3 Monitoring (log/{YYYY-MM}.md rotation) | UC-02 step 11 |
| R-10 (wiki-search) | §3.2 wiki-search, §8.3 DB Optimization | UC-03 entire |
| R-11 (wiki-lint) | §3.2 wiki-lint, §9.3 Monitoring | UC-04 entire |
| R-12 (ingest-source workflow) | §3.2 Workflow Orchestrator | UC-02 step 1, UC-05 step 5, UC-06 step 1 |
| R-13 (bulk migration) | §3.2 Migration & Validation Tools, §10.4 | UC-05 entire |
| R-14 (benchmark) | §10.2 CI bench target, §8.3 + §28 Performance budget | I-5.3 benchmark suite output (CI-fail если > target) |
| R-15.1-15.2 (provenance v1.1 in DDL + extracted_items) | §4.1 PageEntityRef + extracted_items entities | SCHEMA CHECK constraint enforcement |
| R-15.3 (per-adapter trust_level) | §3.2 wiki-source-manual=high, transcript/light=medium | UC-02 AC |
| R-24 (wiki-light-summary) | §3.2 wiki-source-light, §5.3 Anthropic API integration | UC-06 entire |
| R-25 (vault_metadata) | §4.1 VaultMetadata entity, §4.4 Migrations | UC-01 AC `vault_metadata seeded` |
| R-26.1 (sentinel-PK fix) | §4.1 Page (sentinel '_vault_'), SCHEMA L106 | UC-02 AC idempotency test |
| R-26.2 (path-traversal validation) | §3.2 wiki-source-manual + §7.3 A01 + SourceAdapter contract `PATH_OUTSIDE_VAULT` error code | UC-02 AC path-traversal test |
| **R-26.3** (path-traversal AC test) | UC-02 AC explicit binary test (re-running `--source ../../../etc/passwd` returns error envelope, no SQLite write) | UC-02 AC line 8 |

Все 18 MVP requirements + sub-features покрыты Architecture sections + tied к binary test references.

### Concept Extractor Requirements (R-30..R-43)

| Requirement | Architecture coverage |
|---|---|
| R-30 (skill entry point) | §2.1 Component: Concept Extractor — entry point `scripts/wiki_skills/wiki_extract_concepts.py`; §2.1 Skill Layer list |
| R-31 (required `--vault` + `--source-page` args; vault-relative path resolution) | §2.1 CLI surface; R-26.2 path-traversal guard inherited via `validate_inside_vault` |
| R-32 (pre-extraction known-entities query) | §2.1 `load_known_entities` function; §4.1 Entity (ADR-002 D3 entities-via-SQL) |
| R-33′ (operator-synthesised candidates JSON; strict schema validation) | §2.1 `_validate_candidates_schema`; §2.1 Candidates JSON contract; §3.4 STEP 5 (synthesis in calling agent) |
| R-34 (de-duplication at extraction time) | §2.1 `classify_candidates` function; §2.1 Concept Extractor purpose |
| R-35 (manifest output, wiki-ingest v1.1 compatible) | §2.1 `build_manifest` function; §3.4 STEP 6 |
| R-36 (concept page generation, `_concepts/<slug>.md`) | §2.1 `write_concept_page` (atomic; content-hash skip; symlink refuse; `_sanitize_markdown_text`); §4.1 Entity Business Rules (Class A) |
| R-37 (entity row upsert, `is_candidate=1`) | §2.1 `upsert_extracted_entity`; §2.1 Index Layer DAL `upsert_entity` (SQL-level `MIN()` downgrade-guard); §4.1 Entity write-path |
| R-38 (`page_entity_refs`, `trust_level='medium'`, parsed line spans) | §2.1 `upsert_entity_refs`; §4.1 PageEntityRef |
| R-39 (idempotency: same source body → `is_unchanged=true`) | §2.1 `check_idempotency`; §3.4 STEP 2; UC-09 prose in §4.1 |
| R-40 (multi-vault `vault_id` enforced throughout) | §2.1 Multi-vault invariant; §2.1 Index Layer multi-vault note (ADR-002 §D1) |
| R-41 (in-process dispatch via neutral `_manifest_consumer`) | §2.1 `dispatch_to_indexer`; §3.4 STEP 6 sub-branch; §1.5.2 transport diagram |
| R-42 (error handling, exit codes 0/1/2/4/5/6; CWE-117/209 envelope discipline) | §2.1 Exit-code envelope contract table; §2.1 Operational invariants; §9.1 Error Handling |
| R-43 (tests: unit + integration + parametrised envelope shape; mypy --strict) | §10.2 CI/test gate; §2.1 Universal envelope invariant note |

### wiki-ingest Vendoring Requirements (R-45..R-57)

> Transport-layer concern only: the in-process import path collapses the subprocess hop in §1.5.2 to a Python call. No new DAL methods, no new DB tables, no new user-facing skills. All rows trace to §1.5.2 (flow diagram), §1.5.7 (vendored module anatomy), §2.1 Source Adapters (transport note), §7.4 (vendoring policy), or §10.4 (install simplification).

| Requirement | Architecture coverage |
|---|---|
| R-45 (vendor copy: `scripts/wiki_ingest/` present and importable) | §1.5.7 vendored module anatomy (directory layout, `VENDORED_FROM.md`); §1.5.3 dual-existence note |
| R-46 (programmatic `ingest()` function + `IngestError` exposed) | §1.5.7 Public API surface; §1.5.2 PRIMARY PATH step 2 |
| R-47 (`wiki_enrich.py` primary path: in-process) | §1.5.2 PRIMARY PATH (full diagram); §2.1 Source Adapters transport note; §1.5.4 DAL invariant |
| R-48 (subprocess fallback path retained) | §1.5.2 FALLBACK PATH (full diagram); §1.5.2 path decision branch (`WIKI_ENRICH_NO_VENDORED`, `ImportError`) |
| R-49 (`scripts/sync_wiki_ingest.sh` snapshot sync script) | §1.5.7 sync-script description (divergence-check, rsync, `VENDORED_FROM.md` update); §7.4 Vendoring Policy |
| R-50 (`mypy --strict` clean for `scripts/wiki_ingest/`) | §1.5.7 vendoring policy (type fixups, `local_patches`); §7.4 Vendoring Policy |
| R-51 (tests: vendored path + fallback coverage) | §1.5.2 path decision branch (three fallback scenarios); §10.2 CI/test gate |
| R-52 (`bin/wiki-enrich` launcher no longer requires `wiki-ingest` on PATH) | §1.5.2 PRIMARY PATH; §1.5.5 symlink graph note (external symlink optional) |
| R-53 (README and install docs simplified) | §10.4 Deployment Instructions (`wiki-ingest` symlink demoted to optional) |
| R-54 (ARCHITECTURE.md §1.5.2 updated — this document) | §1.5.2 restructure (PRIMARY PATH + FALLBACK PATH + decision branch); §1.5.3 dual-existence note; §1.5.7 |
| R-55 (`THIRD_PARTY_NOTICES.md` credits upstream wiki-ingest) | §7.4 Vendoring Policy (third-party notices paragraph); §1.5.7 vendoring policy (notices file, LICENSE-upstream) |
| R-56 (`wiki-enrich` interface contracts preserved, no surface breakage) | §1.5.2 (both paths emit identical envelope shape); §2.1 Source Adapters (`--source required=True` note) |
| R-57 (standalone `wiki-ingest` CLI behavior unchanged) | §1.5.3 dual-existence note (vendored copy usable as CLI via `python -m`); §1.5.7 Public API (CLI surface preserved) |

---

