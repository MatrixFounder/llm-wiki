# ARCHITECTURE: LLM Wiki MVP

> This is a living INDEX. Section bodies live in
> [docs/architectures/](./architectures/). Edit the relevant chunk and
> keep the one-line summary on this page in sync.

> **Status**: **TASK 005 active** — Epic 7 completion (R-4 confirmed/candidate
> entity resolution incl. `wiki-merge` duplicate-fold + R-5 two-tier alias
> table). ADRs 001 + 002 in effect; ADR-002 §D8 amended for the
> `entity_aliases` PK change (schema v2→v3, closes L-4). Living document —
> describes the current/target architecture, not the change history. For shipped task specs (history, decisions, hardening
> rounds) see [tasks/](./tasks/) + [plans/](./plans/) archives;
> for deferred items see [KNOWN_ISSUES.md](./KNOWN_ISSUES.md).
>
> **Source spec**: [docs/TASK-ref-v2.md](./TASK-ref-v2.md) — full v2 reference specification.
> **Schema**: [docs/SCHEMA-v2.sql](./SCHEMA-v2.sql) — SQLite DDL (multi-vault, partitioned by `vault_id`).
> **Backend choice**: [docs/SQLITE-VS-POSTGRES.md](./SQLITE-VS-POSTGRES.md) — SQLite default, Postgres opt-in via DAL.
> **Layout constants** consolidated in [scripts/wiki_index/layout.py](../scripts/wiki_index/layout.py) — single source of truth for `PAGE_SUBDIRS`, `COURSE_TIER_DIR`, `VAULT_INDEX_DIR`, `LOG_SUBDIR`, `SCAFFOLD_DIRS`, `SYSTEM_FILES`, `GLOBAL_VAULT_SENTINEL`.

---

## Table of Contents

- [1. Task Description](#1-task-description) (inline)
- [1.5. Project Anatomy](#15-project-anatomy) → [architectures/project-anatomy.md](./architectures/project-anatomy.md)
- [2. Functional Architecture](#2-functional-architecture) → [architectures/functional-architecture.md](./architectures/functional-architecture.md)
- [3. System Architecture](#3-system-architecture) → [architectures/system-architecture.md](./architectures/system-architecture.md)
- [4. Data Model (Conceptual)](#4-data-model-conceptual) → [architectures/data-model.md](./architectures/data-model.md)
- [5. Interfaces](#5-interfaces) → [architectures/interfaces.md](./architectures/interfaces.md)
- [6. Technology Stack](#6-technology-stack) → [architectures/technology-stack.md](./architectures/technology-stack.md)
- [7. Security](#7-security) → [architectures/security.md](./architectures/security.md)
- [8. Scalability and Performance](#8-scalability-and-performance) → [architectures/scalability-and-performance.md](./architectures/scalability-and-performance.md)
- [9. Reliability and Fault Tolerance](#9-reliability-and-fault-tolerance) → [architectures/reliability-and-fault-tolerance.md](./architectures/reliability-and-fault-tolerance.md)
- [10. Deployment](#10-deployment) → [architectures/deployment.md](./architectures/deployment.md)
- [11. Open Questions](#11-open-questions) (inline)
- [Verification Map](#verification-map) → [architectures/verification-map.md](./architectures/verification-map.md)
- [Quality Checklist (VDD)](#quality-checklist-vdd) (inline)

---

## 1. Task Description

Реализация MVP персональной LLM Wiki поверх Obsidian-vault'а пользователя:
- **Markdown — source of truth** (Karpathy canon).
- **SQLite — derivative cache** (FTS5 + WAL для < 50ms search; rebuildable).
- **Pluggable source adapters** (manual + transcript + light для MVP).
- **Идемпотентные операции**: re-ingest того же source = no-op.
- **iCloud-aware**: SQLite вне vault'а, markdown в iCloud.

Полное описание целей: archived MVP TASK at [tasks/task-002-wiki-mvp.md](./tasks/task-002-wiki-mvp.md).

---

## 1.5. Project Anatomy

Where things live in the repo: anatomy of one in-repo skill (template + symlink graph), `wiki-enrich` ↔ `wiki-ingest` integration flow (primary in-process path + subprocess fallback), dual-existence of `wiki-ingest` (Universal-skills standalone + this repo's vendored snapshot), and the vendored module's directory layout / sync policy / public API.

→ [details](./architectures/project-anatomy.md)

---

## 2. Functional Architecture

Functional components (Configuration Resolver, Source Adapters, Index Layer DAL, Search Layer FTS5, Lint Layer, Workflow Orchestrator, Migration Tools, Concept Extractor, **Entity Resolver** `wiki-confirm`+`wiki-alias`+`wiki-merge`) and the connection diagram between them. Includes the full `wiki-extract-concepts` `prepare`/`apply` contract, candidates JSON schema, the TASK 005 Entity Resolver CLI surface + exit-code envelopes (incl. `wiki-merge` duplicate-fold), operational invariants, and RTM cross-reference.

→ [details](./architectures/functional-architecture.md)

---

## 3. System Architecture

Architectural style (layered + plugin), system-component breakdown (Skill Layer → Adapters → DAL → SQLite), component-interaction diagram, and the UC-08 Concept Extraction sequence diagram (calling agent owns LLM synthesis; Python skill is deterministic plumbing only).

→ [details](./architectures/system-architecture.md)

---

## 4. Data Model (Conceptual)

Conceptual entities (Vault, Page, Entity, EntityAlias, PageEntityRef, SourceState, LogEvent) with key attributes, relationships, business rules, and ADR-002 Class A/B/C layering for each. Includes the entity write-path + downgrade-guard semantics, the TASK 005 two-tier confirm/candidate resolution (`is_candidate` as Class A frontmatter), the EntityAlias activation (PK `(vault_id, alias)`, L-4 closed; schema v2→v3 migration), and the duplicate-merge path (R-4.7: pure-DML re-pointing, alias-as-redirect, no merge-ledger table).

→ [details](./architectures/data-model.md)

---

## 5. Interfaces

External APIs (CLI surface, JSON-envelope shape), internal interfaces (`IndexRepository` ABC + concrete `SQLiteRepository`, incl. the TASK 005 entity-resolution methods + `merge_entities` + alias-aware `find_orphan_links`, and `wiki-confirm`/`wiki-alias`/`wiki-merge` error codes), and integrations (wiki-ingest manifest contract v1.1).

→ [details](./architectures/interfaces.md)

---

## 6. Technology Stack

Backend (Python 3.14, SQLite 3.35+ with FTS5 + WAL), frontmatter / pyyaml / python-slugify / jsonschema libraries, infrastructure (single-user laptop, optional iCloud-synced vault, no server).

→ [details](./architectures/technology-stack.md)

---

## 7. Security

Threat model (single-user trust scope), authN (N/A) + authZ (file-permission-only), path-traversal guard (`validate_inside_vault`), SQL-injection guard (parameterised statements only, no f-string composition), and the Vendoring Policy (§7.4) covering type fixups, drift detection, and third-party notices.

→ [details](./architectures/security.md)

---

## 8. Scalability and Performance

Scaling strategy (vertical only — single-user), caching (SQLite FTS5 cache is the only cache), DB optimisation (WAL mode, narrow indexes, no JSON-expr indexes). Open performance items live in [KNOWN_ISSUES.md](./KNOWN_ISSUES.md) (P-1..P-9, H-PERF-3).

→ [details](./architectures/scalability-and-performance.md)

---

## 9. Reliability and Fault Tolerance

Error-handling pattern (fail-fast + structured JSON envelopes + exit codes), backup policy (markdown is canonical → git-versioned; DB is rebuildable cache), monitoring (none in MVP; operator-driven).

→ [details](./architectures/reliability-and-fault-tolerance.md)

---

## 10. Deployment

Environments (single-user laptop, optional iCloud sync), CI/CD pipeline (pytest + mypy --strict on PR), configuration (`config/wiki-config.yaml`, `WIKI_*` env vars), and deployment instructions (clone repo, install requirements, symlink skills into vendor dirs).

→ [details](./architectures/deployment.md)

---

## 11. Open Questions

### 11a. RESOLVED (по итогам TASK iteration 2)

- Q-A: SQLite vs Postgres — **SQLite default**, Postgres opt-in через DAL. См. [SQLITE-VS-POSTGRES.md](./SQLITE-VS-POSTGRES.md).
- Q-B: Code location — этот репо `obsidian-llm-wiki/`.
- Q-C: PK NULL semantics — fixed sentinel `'_vault_'` в schema.
- Q-D: vault_hash storage — `vault_metadata` table.
- Q-E: trust_level per adapter — manual=high, transcript/light=medium.
- Q-F: required_frontmatter для flat — без `project`.

### 11b. Defer-able (не блокирует Architecture, можно решать в Plan/Dev)

- **Q-1: Embedding модель для Epic 8**.
- **Q-2: light-summary LLM model** — Haiku (default, $) vs Sonnet (quality).
- **Q-3: Cron / launchd для daily automation** — Epic 6 detail.
- **Q-4: Plugin packaging format** — после MVP стабилизации.
- **Q-5: `wiki-source-light` text input limit** — спека `≤ 10K chars` стоит ли расширить? Решается в Dev по UX feedback'у.

### 11c. Architecture-specific Open Questions

- **Q-A1: ABI compatibility transcript adapter ↔ summarizing-meetings**. Какой именно contract?
  - **Default assumption**: subprocess invocation `claude /generate-detailed-meeting-summary --source <transcript>` → читаем stdout JSON envelope с output path. Если skill эмиттит другой формат — adapter parser нужно адаптировать.
  - **Resolution**: подтверждается при первом end-to-end тесте transcript adapter (Epic E3 I-3.3).

- **Q-A2: Should `wiki-init` cron-job creation быть default ON or OFF?**
  - **Current TASK answer**: interactive prompt, default OFF.
  - **Architecture stance**: согласен — automation — opt-in для предотвращения surprise behavior.

- **Q-A3: Schema migration framework выбор**.
  - **Default assumption**: rolling files в `scripts/migrations/v{N}_to_v{N+1}.py` без external lib (Alembic-style — overkill).
  - **Resolution**: confirmed для MVP. Re-evaluate если migration count > 5.
  - **TASK 005 note**: the v2→v3 `entity_aliases` PK change needs **no migration script** — the DB is a Class B rebuildable cache, so `wiki-reindex --full` is the migration. Bump `PRAGMA user_version` + `schema_meta` only.

- **Q-A4 (TASK 005): alias-expansion breadth cap.** What maximum number of OR-terms per query before truncation (FTS-blow-up perf guard)?
  - **Default assumption**: cap at the matched entity's own alias set + canonical name; **no transitive expansion**. Non-blocking — tune in Dev on real-vault feedback.

- **Q-A5 (TASK 005): auto-promote log-event granularity.** Should `wiki-confirm --auto` emit one `entity-confirmed` log event per promoted slug, or a single batch event?
  - **Default assumption**: one event per promotion (backlink traceability). Resolve in Planning. Non-blocking.

---

## Verification Map

Requirement → architecture-surface traceability for Phase 3a MVP (R-01..R-26), Concept Extractor (R-30..R-43), wiki-ingest Vendoring (R-45..R-57), and Entity Resolver (R-4 + R-5, TASK 005).

→ [details](./architectures/verification-map.md)

---

## Quality Checklist (VDD)

- [x] **Data Model**: entities + key attributes + relationships + indexes defined (§4 + SCHEMA-v2.sql). Entity write-path documented in §4.1 Entity Business Rules.
- [x] **Traceability**: Verification Map covers Phase 3a (R-01..R-26), Concept Extractor (R-30..R-43), and wiki-ingest Vendoring (R-45..R-57).
- [x] **Security**: AuthN — N/A (single-user); AuthZ — file permissions; path-traversal + SQL-injection protections explicit (§7.3). `validate_inside_vault` applied to every `_concepts/` write path AND every operator-supplied path (source-page, candidates-file).
- [x] **Multi-vault**: every operation carries a `vault_id` predicate or is scoped to `vault_root`. Vendored `ingest()` accepts `vault_id` as explicit kwarg; no hash-fallback.
- [x] **Stub-First**: TASK 005 Entity Resolver is designed Stub-First (DAL signatures + RED tests before logic); `resolve_entity` is promoted from deferred stub → implemented (R-4.5).
- [x] **ADR-001 clarification**: Source Adapters component preserves the single-indexer invariant while allowing derivative page writes (concept pages) by downstream skills.
- [x] **Backward compat**: subprocess fallback path fully preserved (§1.5.2 FALLBACK PATH); external `wiki-ingest` binary remains optional.
- [x] **Template**: extended template applied (Sections 1-11 covered + §3.4 Sequence Diagram + §1.5.7 vendored-module subsection + §7.4 Vendoring Policy subsection).
