# ARCHITECTURE: LLM Wiki MVP

> This is a living INDEX. Section bodies live in
> [docs/architectures/](./architectures/). Edit the relevant chunk and
> keep the one-line summary on this page in sync.

> **Status**: Phase 3b — incremental feature/hardening tasks (one per `docs/tasks/*`).
> The **current** task is in [docs/TASK.md](./TASK.md); the shipped-task log lives in
> [docs/tasks/](./tasks/) + [docs/plans/](./plans/) + git — intentionally not repeated
> here, nor in `CLAUDE.md`. The per-task **design rationale** (Q-0XX) is §11, chunked to
> [architectures/open-questions.md](./architectures/open-questions.md). **Schema
> `user_version 7`** ([sql/wiki-index-v2.sql](../sql/wiki-index-v2.sql)); the DB is a
> Class-B rebuildable cache (ADR-002 §D8 — a schema bump is a `wiki-reindex --full`
> rebuild, never an in-place ALTER). ADRs: [001](./adr/ADR-001-wiki-ingest-integration.md)
> wrap+index · [002](./adr/ADR-002-multi-vault-bottleneck-corrections.md) multi-vault +
> Class A/B/C · [003](./adr/ADR-003-typed-knowledge-classes.md) typed knowledge classes ·
> [004](./adr/ADR-004-event-graph-typed-edges.md) event graph ·
> [005](./adr/ADR-005-fts-narrowed-membership-filter.md) FTS-narrowed membership ·
> [006](./adr/ADR-006-derived-knowledge-health.md) derived knowledge health ·
> [007](./adr/ADR-007-config-driven-write-grammar.md) config-driven write-grammar (Karpathy = a layout YAML) ·
> [008](./adr/ADR-008-active-note-resolution.md) active-note resolution ·
> [009](./adr/ADR-009-policy-before-model.md) policy-before-model retrieval scoping (**Accepted**, SHIPPED as TASK 049 — headed the now-complete ROADMAP R-16…R-19 enterprise-readiness theme).
>
> **Source spec** (historical): [docs/archive/TASK-ref-v2.md](./archive/TASK-ref-v2.md) — the original pre-implementation v2 reference spec (archived; the living architecture is this document + `docs/architectures/`).
> **Schema**: [docs/SCHEMA-v2.sql](./SCHEMA-v2.sql) — SQLite DDL (multi-vault, partitioned by `vault_id`).
> **Backend choice**: [docs/SQLITE-VS-POSTGRES.md](./SQLITE-VS-POSTGRES.md) — SQLite default, Postgres opt-in via DAL.
> **Layout constants** consolidated in [scripts/wiki_index/layout.py](../scripts/wiki_index/layout.py) — single source of truth for `PAGE_SUBDIRS`, `COURSE_TIER_DIR`, `VAULT_INDEX_DIR`, `LOG_SUBDIR`, `SCAFFOLD_DIRS`, `SYSTEM_FILES`, `GLOBAL_VAULT_SENTINEL`.

---

## Table of Contents

- [1. Task Description](#1-task-description) (inline)
- [1.5. Project Anatomy](#15-project-anatomy) → [architectures/project-anatomy.md](./architectures/project-anatomy.md)
- [1.6. Skill / Command / Workflow Execution Model](#16-skill--command--workflow-execution-model) → [architectures/skill-command-workflow-model.md](./architectures/skill-command-workflow-model.md) (RU · [EN](./architectures/skill-command-workflow-model.en.md))
- [2. Functional Architecture](#2-functional-architecture) → [architectures/functional-architecture.md](./architectures/functional-architecture.md)
- [3. System Architecture](#3-system-architecture) → [architectures/system-architecture.md](./architectures/system-architecture.md)
- [4. Data Model (Conceptual)](#4-data-model-conceptual) → [architectures/data-model.md](./architectures/data-model.md)
- [5. Interfaces](#5-interfaces) → [architectures/interfaces.md](./architectures/interfaces.md)
- [6. Technology Stack](#6-technology-stack) → [architectures/technology-stack.md](./architectures/technology-stack.md)
- [7. Security](#7-security) → [architectures/security.md](./architectures/security.md)
- [8. Scalability and Performance](#8-scalability-and-performance) → [architectures/scalability-and-performance.md](./architectures/scalability-and-performance.md)
- [9. Reliability and Fault Tolerance](#9-reliability-and-fault-tolerance) → [architectures/reliability-and-fault-tolerance.md](./architectures/reliability-and-fault-tolerance.md)
- [10. Deployment](#10-deployment) → [architectures/deployment.md](./architectures/deployment.md)
- [11. Open Questions](#11-open-questions) → [architectures/open-questions.md](./architectures/open-questions.md)
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

Where things live in the repo: anatomy of one in-repo skill (template + symlink graph) and how the CLIs, DAL, and layout engine compose.

> **Superseded (TASK 047):** the `wiki-enrich` ↔ vendored `wiki-ingest` integration flow (the
> primary in-process path + subprocess fallback + the vendored-snapshot layout / sync policy)
> described in the linked body was **retired** — `wiki-import` is the in-repo construct engine and
> concept-page compounding is a derived Class-B render (`wiki-index-render --concept-mentions`).
> Those §1.5.2/§1.5.3/§1.5.7 subsections are kept as accepted-then-superseded history.

→ [details](./architectures/project-anatomy.md)

---

## 1.6. Skill / Command / Workflow Execution Model

Как **один `/wiki-*` вызов реально исполняется** — how-to для человека (с presentation-ready
mermaid-схемами). Объясняет: почему одно имя (`wiki-sync`) встречается как **command +
SKILL + workflow (+ `bin/` + `scripts/`)** и почему это намеренный многоключевой биндинг,
а не дубликат; **симлинк-разветвление** repo-root → `.claude/`/`.agent/`/глобальная
установка (в `.claude/` **нет** `workflows/` — рецепт читается по пути через `Read`);
**ленивая загрузка слоями** (Слой 0 `description`-меню → Слой 1 инжект тела харнессом →
Слои 2–3 `Read`-цепочка workflow + `references/`); **детерминированная диспетчеризация** (`/`
разрешает CLI, не LLM; команды слиты со скилами; одноимённая коллизия безвредна — оба входа
сходятся на одном рецепте); и **управляющая структура workflow** (линейный спайн + цикл по
`entries[]` + ветвления + per-file isolation, исполняемые оркестратором, тогда как
детерминизм сидит в shell-out Decision-17 CLI). Дополняет [§1.5](#15-project-anatomy) (там —
*где лежат файлы*; здесь — *что и откуда берётся при запуске*). Доступно на двух языках
(держатся синхронными).

→ [details (RU)](./architectures/skill-command-workflow-model.md) · [details (EN)](./architectures/skill-command-workflow-model.en.md)

---

## 2. Functional Architecture

The functional components and the connection diagram between them:

| Component | Role |
|---|---|
| Configuration Resolver | per-vault identity + per-layout grammar resolution |
| Source Adapters | manual / transcript / import on-ramps |
| Index Layer (DAL) | `IndexRepository` over SQLite (FTS5 + WAL) |
| Search Layer (FTS5) | BM25 + alias expansion; metadata / temporal filters |
| Lint Layer | SQL health + R-15 lifecycle-drift + R-19 ontology-violation gates (`--strict`) |
| Workflow Orchestrator | multi-step ingest-recipe driver |
| Migration Tools | reindex / bulk-ingest / benchmark |
| Concept Extractor (`wiki-extract-concepts`) | densify a source into concept pages (`prepare`/`apply`) |
| **Typed-Knowledge Rail** (`wiki-extract-decisions`, TASK 063 / RFC-004) | a summarised note → `decision`/`requirement`/`risk` pages + **forward** edges (inverses auto-derive at `--full`). `prepare` emits the **ontology contract** (roster · edge domain/range · per-class `status` enums) and **PREFLIGHTS G4**; `apply` validates every candidate against it **before any write** (violation ⇒ exit 4, **zero** files) and reconciles supersede targets from the layout's OWN `drift_rules`. **G4 is a CONJUNCTION** — the layout must *map* the classes **AND** its read globs must *see* the write dir; a glob-invisible page is written, never indexed, and raises **zero** lint issues, because `find_pages_missing_in_index` walks via `discover_pages` and never discovers it. That structural blindness is why the acceptance property is `(delta-clean) AND (G6)`: **the delta catches HARM, G6 catches SILENCE**, and G6 is anchored on the **submitted candidate batch**, never on the rail's own report. Anti-fabrication is a MECHANISM (empty = SUCCESS, verbatim `source_quote`, **no escape hatch**), not a prompt |
| Entity Resolver (`wiki-confirm`/`wiki-alias`/`wiki-merge`) | promote / alias / merge-fold entities |
| RAG Query Layer (`wiki-query`) | retrieve → cited synthesis → filed `_queries/` page |
| **Native-App Control Skill** (`obsidian-cli`) | prompt-layer routing/safety over the live Obsidian app (§2.2) |
| **Sync Dispatcher** (`wiki-sync`) | batch driver: scan → delegate per item to `wiki-import` (evolution below) |
| **Config Interface** (`wiki-config`, TASK 058) | per-folder `.wiki/sync.yaml` operator surface: inheritance provenance (mirror-of-merge fold, equivalence-gated vs the real resolver), 3-system validate, tiered doctor/fix (ruamel sandwich — comment survival is a checked invariant; backups+restore, TOCTOU), templates, HTML report, local token-auth web editor; 100% schema-driven (`x-wiki-*` annotations) → new fields need zero UI code; no DB access |

**Sync Dispatcher evolution:**
1. **TASK 018 / R-11** — format+content classifier → scan-plan + orchestrated convert/ingest/upsert/skip.
2. **TASK 019** — re-summarization **policy gate**: skip-if-summarized (D1 `source_state` ∪ D2a provenance ∪ D2b mirror) + `--force` + per-folder `.wiki/sync.yaml` cascade overrides.
3. **TASK 051 / R-18** — `resummarize.mode: if-changed` (D1 keyed on hash-**equality**, not marker-**presence** → a *changed* source re-summarises, an unchanged one is `skip:summary-unchanged`) + a `wiki-import prepare` `is_unchanged` short-circuit + the connector-contract substrate.

The chunk carries the full detail: the `wiki-extract-concepts` `prepare`/`apply` contract + candidates JSON schema (§2.1), the TASK 005 Entity Resolver CLI surface + exit-code envelopes, the TASK 007 `wiki-query` RAG contract (retrieval envelope + answer/citations + grounding gate + `cited`-backlink self-index), plus the per-component design deltas — obsidian-cli + active-note (§2.2 / §2.2.1), the construct path with its hardening / transcript-fetcher / embedded-video / converged-pipeline / video-robustness+folder-inference+announcement subsections (§2.3–§2.3.5), and the policy + trust layer (§2.4 / §2.4.1) — operational invariants, and RTM cross-reference.

→ [details](./architectures/functional-architecture.md)

---

## 3. System Architecture

Architectural style (layered + plugin), system-component breakdown (Skill Layer → Adapters → DAL → SQLite), component-interaction diagram, and the UC-08 Concept Extraction sequence diagram (calling agent owns LLM synthesis; Python skill is deterministic plumbing only). **TASK 056** restructures the DAL concrete: `sqlite_repository.py` (2227-line monolith) becomes the domain-package `sqlite_repository/` — per-table-family mixin modules composed onto an abstract `SQLiteRepositoryBase(IndexRepository)` root, import path frozen, behaviour-freeze proven by the untouched test suite; the per-domain layout + per-module `dialect:` tags are the mirror-template for the future `postgres_repository/` (ROADMAP P3, SQLITE-VS-POSTGRES.md §4).

**Layout-engine evolution** (§3.5):
1. **TASK 012 / R-X1 — config-driven Layout Engine.** Two separate config layers (per-vault identity via `config_loader` + per-layout grammar via the new `layout_config` + built-in `layouts/{karpathy,dev-project,obsidian-personal}.yaml`); the `iter_pages` walk that converges the four hardcoded two-tier walks; the byte-identity strategy (karpathy.yaml = validated projection of `layout.py`; three slug surfaces kept distinct); the ReDoS guard (TASK 012 stdlib-`re` load-gate **+** the TASK 017 runtime per-file `regex` `timeout=` deadline for operator-custom patterns, R-X1-REDOS-RT); the PW-H `auto_indexes[]` renderer + PW-Q lint guard; the TASK 017 single-stat walk + drift fast-path (P-2/P-3 — Class-B "rebuildable markdown", zero DDL).
2. **TASK 030 (R-030-3/6) — single-pass iterative alive-set engine** (replaced the per-glob walk).
   - `_PatternState` NFA per `paths[]` glob; exact `Path.glob` symlink-union parity.
   - PROPER-prefix descent + real `<prefix>/**` ignore-pruning; every dir scandir'd ≤1× — measured 140→61 at 2k files.
   - karpathy "root subtrees never walked" instrumented; matcher deltas enumerated Q-030-2 v4; the DirEntry-stat single-stat mechanism re-pinned.
3. **TASK 031 (R-031-3) — de-hardcoded layout REGISTRY + typed-knowledge taxonomy.** The `--layout` choice-set + two-tier-scaffold family + legacy alias map (previously three sources of truth — `wiki_init._LAYOUT_CHOICES`/`_KARPATHY_LAYOUTS` + `layout_config._ALIAS`) collapse into ONE cached YAML-derived registry, via two optional additive `LayoutConfig` keys `aliases`/`init_scaffold` (init-only metadata — they do NOT touch the indexer, so Karpathy byte-identity holds); a new built-in layout becomes a valid `--layout` value as a pure drop-in `*.yaml`. Adds the **typed-knowledge taxonomy** (decision/requirement/risk/incident/hypothesis/fact/event) as zero-DDL `type_mapping` tag-routes in `dev-project.yaml` + the new `cybos.yaml` (ADR-003; classification only — the event-graph relation layer is deferred Phase-2 per ROADMAP R-13).

→ [details](./architectures/system-architecture.md)

---

## 4. Data Model (Conceptual)

Conceptual entities (Vault, Page, Entity, EntityAlias, PageEntityRef, SourceState, LogEvent) with key attributes, relationships, business rules, and ADR-002 Class A/B/C layering for each. Includes the entity write-path + downgrade-guard semantics, the TASK 005 two-tier confirm/candidate resolution (`is_candidate` as Class A frontmatter), the EntityAlias activation (PK `(vault_id, alias)`, L-4 closed; schema v2→v3 migration), the duplicate-merge path (R-4.7: pure-DML re-pointing, alias-as-redirect, no merge-ledger table), and the TASK 007 RAG additions (query page as a first-class compounding `type=query` artifact; `ref_type='cited'` query→source backlinks with the R-6.5e reindex read-side; `source_state` reuse for query idempotency — all **zero-DDL**, `user_version` stays 4). **TASK 019** (re-summarization policy) is likewise **zero-DDL**: D1 reuses `SourceState` (`source_kind='sync'`), D2a reads `Page.frontmatter_json` (`json_extract`/`json_each`, TASK 013 mechanism) through **two new read-only DAL methods** — `find_pages_citing_source` (single-source check) + `all_cited_sources` (the bulk citation set, hoisted once per scan, Q-019-10) — D2b is filesystem-only — **no new entity/column**, `user_version` stays **5**. **TASK 051 / R-18** (source freshness) is likewise **zero-DDL**: `resummarize.mode: if-changed` READS `SourceState.source_hash` (`source_kind='sync'`) for a hash-equality skip (no new read method — the recorded marker + the scan-computed `_hash_file` already exist, hoisted ahead of the gate per Q-051-1), and `wiki-import prepare` hashes the on-disk `_raw/<slug>.md` before overwrite (file-vs-file, no DB read) — **no new entity/column**, `user_version` stays **7**. **TASK 032 (event graph, ADR-004)** is the **first schema bump since TASK 008**: `PageEntityRef.ref_type` gains an inverse-closed typed-edge set (`implements`/`implemented-by`, `supersedes`/`superseded-by`, `causes`/`caused-by`; `relates_to` reuses the dormant symmetric `related`) — additive CHECK values only, `user_version` **5→6**, migration = Class-B rebuild. No table/PK change. Forward edges are extracted into the source page's single `replace_refs` (M-1); inverse rows (on the *target* page) are materialized by a global post-pass (AM-3 sibling) — see Q-032-1/2/3.

→ [details](./architectures/data-model.md)

---

## 5. Interfaces

External APIs (CLI surface, JSON-envelope shape), internal interfaces (`IndexRepository` ABC + concrete `SQLiteRepository`, incl. the TASK 005 entity-resolution methods + `merge_entities` + alias-aware `find_orphan_links`, and `wiki-confirm`/`wiki-alias`/`wiki-merge` error codes; the TASK 007 `wiki-query` `prepare`/`apply` CLI surface + `check_query_state`/`record_query_state` DAL methods + error codes), and the internal v1.1 concept-manifest contract (the external `wiki-ingest` consumer was retired in TASK 047; the manifest shape is now `wiki-extract-concepts --ingest` → `_manifest_consumer` only). **TASK 049** adds ONE pure module (`scripts/wiki_index/policy.py`), two optional `search_pages` DAL params (`allowed_classifications`/`classification_default`), two read-only DAL methods (`find_classification_leaks`/`find_invalid_classifications`), and the `--audience`/`--classification` flags (§2.4) — no new CLI, no envelope change under OFF.

→ [details](./architectures/interfaces.md)

---

## 6. Technology Stack

Backend (Python 3.14, SQLite 3.35+ with FTS5 + WAL), frontmatter / pyyaml / python-slugify / jsonschema libraries, infrastructure (single-user laptop, optional iCloud-synced vault, no server).

→ [details](./architectures/technology-stack.md)

---

## 7. Security

Threat model (single-user trust scope), authN (N/A) + authZ (file-permission-only), path-traversal guard (`validate_inside_vault`), SQL-injection guard (parameterised statements only, no f-string composition), and the Vendoring Policy (§7.4) covering type fixups, drift detection, and third-party notices. **TASK 029** adds the prompt-layer command-safety surface for the `obsidian-cli` skill — the TOTAL T1/T2/T3 tier model (T3 ban on `eval`/`dev:*`/plugin/snippet/sync mutations; fail-safe T2-with-confirmation default) + the untrusted-CLI-output posture (H-6 class) — design at §2.2 in [functional-architecture.md](./architectures/functional-architecture.md) (no code change; the threat actor is hostile note content steering an agent, not a second user). **TASK 041 / ADR-008** extends this posture for active-note resolution (§2.2.1): resolution is driven by **live app state, never note content** (H-6); **auto-resolved read content is DATA** — no action-escalation onto a new target/verb/T2\*/T3 op; the F-4 footgun is *amended not deleted* (the mutation still carries an explicit resolved `path=`, so E-11 holds); destructive verbs always re-confirm (E-14); headless → no resolve. The one new artifact is a stdlib skill-local resolver (`obsidian-active-note`) — no new attack surface on the DB/DAL. **TASK 068** extends this posture for the editor-selection bridge (§2.2.2): selection read/replace via the `agent-bridge` T2 plugin channel; `eval` stays T3 and is never auto-dispatched, regardless of note-content phrasing — the sole new attack surface is a **305-line** least-privilege plugin (`main.js`, the only file Obsidian executes, built from a 457-line `main.ts`; `.obsidian/`-scoped JSON I/O only, no process/network access. ⚠️ *This read "~110-line" until TASK 070 — a **design-time estimate the implementation never matched**: `main.ts` was already 248 lines at TASK 068's own ship commit, and §2.2.2 contradicted the figure at the time. A size claim in a security section is a claim about **reviewability**, so it is measured here, not estimated*; **TASK 070** makes its `main.js` an esbuild **build product** of `main.ts` type-checked against the **real** pinned `obsidian` package — the vendored d.ts that had *invented* `getMode?()` is deleted, and `--write` refuses to re-pin on a type error. The build toolchain (`esbuild`/`typescript`, exact-pinned, `npm install` runs esbuild's postinstall) is **dev-only and never ships**: install copies exactly two files, `manifest.json` + `main.js`, so a vault never gains a Node/npm surface), and the `command id=` default-T3/DENY rule gains one explicit, H-5-re-pinned proven-effect carve-out (R-068-8) rather than a silent loosening.

→ [details](./architectures/security.md)

---

## 8. Scalability and Performance

Scaling strategy (vertical only — single-user), caching (SQLite FTS5 cache is the only cache), DB optimisation (WAL mode, narrow indexes, no JSON-expr indexes). Open performance items live in [KNOWN_ISSUES.md](./KNOWN_ISSUES.md) (P-4, P-9, P-11, R-X1-CFG-COST, R-X3-MF-SCAN; P-1 closed by TASK 030 — see §8.5).

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

RESOLVED foundational decisions (11a), defer-able items (11b), and the
architecture-specific open/resolved **Q-0XX** entries (11c) — every shipped TASK's
design rationale lives here (the layout engine Q-012, metadata filter Q-013/033,
vault-local DB Q-022, typed classes/event graph Q-031/032, temporal `--as-of`
Q-034, the TASK 035 FTS-narrowed tag-membership **Q-035-1/2**, the TASK 044
transcript-fetcher video routing **Q-044-1**; embedded-video design rationale +
ad-exclusion heuristic **Q-044-9/Q-044-10/Q-044-11**; TASK 045 Obsidian
deep-link design **Q-045-1/2**; the policy/trust layer Q-049/Q-050; TASK 051
source-freshness design **Q-051-1..5** — §11k, incl. the ratified `if-changed`-vs-`always`
decision; and the TASK 056 DAL-modularization rationale **Q-056-1..3** — §11m: mixin-package
over facade, the four-call cross-domain coupling map + MRO base-tuple rule, and the
health-cluster rule-provenance split).

→ [details](./architectures/open-questions.md)

---

## Verification Map

Requirement → architecture-surface traceability for Phase 3a MVP (R-01..R-26), Concept Extractor (R-30..R-43), wiki-ingest Vendoring (R-45..R-57), Entity Resolver (R-4 + R-5, TASK 005), RAG Query Layer (R-6, TASK 007), the **Sync Dispatcher re-summarization policy (TASK 019, AC-1..13 → Q-019-1..9)**, and the **source-freshness slices (TASK 051 / R-18, R1..R5 → Q-051-1..5)**.

→ [details](./architectures/verification-map.md)

---

## Quality Checklist (VDD)

- [x] **Data Model**: entities + key attributes + relationships + indexes defined (§4 + SCHEMA-v2.sql). Entity write-path documented in §4.1 Conceptual Data Model.
- [x] **Traceability**: Verification Map covers Phase 3a (R-01..R-26), Concept Extractor (R-30..R-43), and wiki-ingest Vendoring (R-45..R-57).
- [x] **Security**: AuthN — N/A (single-user); AuthZ — file permissions; path-traversal + SQL-injection protections explicit (§7.3). `validate_inside_vault` applied to every `_concepts/` write path AND every operator-supplied path (source-page, candidates-file).
- [x] **Multi-vault**: every operation carries a `vault_id` predicate or is scoped to `vault_root`. Vendored `ingest()` accepts `vault_id` as explicit kwarg; no hash-fallback.
- [x] **Stub-First**: TASK 005 Entity Resolver is designed Stub-First (DAL signatures + RED tests before logic); `resolve_entity` is promoted from deferred stub → implemented (R-4.5).
- [x] **RAG Query Layer (TASK 007)**: `wiki-query` designed as a deterministic `prepare`/`apply` skill (Decision-17, no LLM in Python); query page is a first-class compounding `type=query` artifact; durability secured by the R-6.5e `cites:`→`'cited'` reindex read-side (the §D8 gate, mirroring R-5.3); zero schema DDL; grounding enforced in Python (`CITATION_NOT_RETRIEVED` / `NO_CONTEXT`).
- [x] **Native-App Control Skill (TASK 029)**: prompt-layer only — routing/coherence/safety/degradation invariants designed (§2.2); zero DDL, zero new Python, no interface change; safety model TOTAL over the verified 102-command surface with fail-safe default (incl. the 029-07 `command id=`→T3 + Templater-template→T3 refinements); eval harness machine-checkable without a grader (Q-029-1).
- [x] **Indexer hardening (TASK 030, SHIPPED)**: rename-aware `--delta` (new-path membership predicate, zero extra I/O, swap-class residual documented), chunked-tx `--full` (private txn-free DML helpers; M-4/FTS-trigger posture untouched), single-pass pruned walk (descent predicate preserves karpathy "root never walked"; `Path.glob` symlink parity); zero DDL; design at Q-030-1..6; spec docs/TASK.md + reviews/task-030-review.md.
- [x] **Typed knowledge classes (TASK 031)**: classification-only Phase 1 — 7 classes tag-routed zero-DDL onto the existing db_type enum (Q-031-1/2) in `dev-project` + new `cybos` layout (Q-031-3); layout registry de-hardcoded to one cached YAML-derived source via additive `aliases`/`init_scaffold` keys (Q-031-4); event graph deferred Phase-2 (Q-031-5 / ROADMAP R-13). ADR-003; Karpathy byte-identity preserved; 1339 pytest, mypy strict; `/vdd-multi` converged (5 LOW: 3 fixed + 2 accepted-residual). DF-031-1 dogfood doc-fix folded.
- [x] **Event graph (TASK 032)**: R-13 Phase 2 — typed page-to-page edges + graph-aware RAG (ADR-004). Schema v5→v6 inverse-closed `ref_type` (first DDL since TASK 008; Class-B rebuild). Forward edges via per-page `replace_refs` (M-1 intact); auto-inverse via a global AM-3-sibling post-pass (Q-032-2); delta scoped-additions + removal-deferred-to-`--full` (provenance-safe, Q-032-3). New `wiki-graph` CLI (Q-032-5) + typed-edge DAL reads (Q-032-6); `wiki-query --follow-edges` graph-RAG, default OFF, deterministic hash (Q-032-4). Karpathy byte-identity preserved. 1381 pytest, mypy strict.
- [x] **List-membership metadata filter (TASK 033)**: `wiki-search --where` now matches list-valued frontmatter (`tags[]`) via `scalar = ? OR EXISTS(json_each … = ?)` — the proven `find_pages_citing_source` shape lifted into `search_pages` (Q-033-1), + a `--tag <value>` sugar flag (Q-033-2). Closes the ROADMAP R-13 residual (one clean per-typed-class command). Backward-compatible (scalar `--status`/`--severity` unchanged), injection posture preserved (allowlist + twice-bound params + no echo + dup-guard), **zero DDL** (`user_version` 6).
- [x] **FTS-narrowed tag membership (TASK 035, ADR-005)**: closes the hot branch of R-X3-MF-SCAN measured on the real 2493-page vault. Metadata-only `--tag`/`tags=` membership now narrows via the already-existing `pages_fts.tags` index ("FTS narrows, `json_each` confirms" — Q-035-2) instead of a full-partition scan; result list byte-identical (superset + exact confirm, empirically 0 mismatches over 40 real tags), zero-token values fall back to the scan. The scalar/temporal/non-tags branches are left as a scan by design (P-5: their fields are sparse/absent — Q-035-1). **Zero DDL** (`user_version` stays 7), no new dep, no layering inversion, Karpathy byte-identity preserved.
- [x] **ADR-001 clarification**: Source Adapters component preserves the single-indexer invariant while allowing derivative page writes (concept pages) by downstream skills.
- [x] **Backward compat**: subprocess fallback path fully preserved (§1.5.2 FALLBACK PATH); external `wiki-ingest` binary remains optional. *(Both retired in TASK 047 — `wiki-import` is the in-repo construct engine; entry kept as shipped-history.)*
- [x] **Obsidian deep-links (TASK 045)**: `wiki-search` JSON hits gain `file_path` (always present) + `obsidian_url` (`obsidian://open?vault=<folder-basename>&file=<encoded-path>`, null when vault unknown — Q-045-1). Vault cache built once per unique `vault_id` across hits (R-3). `--format markdown`: OSC 8 hyperlinks on iTerm2/VS Code terminal; plain URL fallback for pipe + Apple Terminal (detected via `TERM_PROGRAM=Apple_Terminal` — Q-045-2); chat agents show clean title/slug/snippet (obsidian:// not clickable in VS Code webview CSP). H-6 control-char sanitisation (`_term_safe`) applied to title/snippet before TTY output (CWE-150). Zero DDL, zero new deps.
- [x] **Policy-before-model retrieval scoping (TASK 049 / ADR-009 / R-16)**: optional default-OFF classification layer — `policy:` ladder + `classification:` key + `--audience` on wiki-search/wiki-query/wiki-verify-multi (+ `wiki-import --classification` H-6 quarantine). ONE bound pre-LIMIT SQL predicate in `search_pages` shared `clause_parts` (all three shapes; fail-closed; both-or-neither guard) + per-page gates on the two `get_page` bypass paths (`_follow_edges` pre-truncation, `_gather_examined` count-only). Hash fold + envelope keys only-when-active (OFF ≡ byte-identical, equivalence-tested). Lint `classification-leak` (`--strict` rail, ADR-006) + `invalid-classification`; COUNT=1 leak-join guard (Q-049-3). Honest boundary documented (§7.6): scopes the MODEL, not the operator. **Zero DDL** (`user_version` 7), vendor-agnostic, derive-don't-author (optional keys only). Design: §2.4 + Q-049-1..4.
- [x] **Read-side audit + derived trust tier (TASK 050 / R-17)**: apply audit fires on every success (cited slugs, action, audience?, actor?); `WIKI_ACTOR_ID` via shared `_common.ORCH_ID_RE`; opt-in `--log-retrieval`/`--log-access` (best-effort, Class-C DB-only); `reindex_full` spares NULL-offset `log_events` rows (D5 — Class-C survives a Class-B rebuild); per-hit derived `trust` + `--min-trust` SQL pre-LIMIT floor (COALESCE-guarded three-valued-logic-safe predicate, `LIKE ESCAPE` on `_raw`, Python↔SQL alignment test-pinned). **Zero DDL** (`user_version` 7); hash folds only-when-flag-present; the one unconditional envelope delta = the `trust` hit key + the D1 completeness event. Design: §2.4.1 + Q-050-1..3.
- [x] **Formal ontology spec (TASK 054 / ADR-009 / R-19)**: optional default-OFF `ontology:` layout block (cybos only) — `closed_types` + `edges` (per-ref_type domain→range) + `properties` (per-class value enums), promoting the typed-knowledge ontology from tribal convention to a declared, validated, diffable contract (closes the ADR-009 pillar-2 "ontology is convention" gap). Load-gate `_validate_ontology` (edges ∈ `reindex._INVERSE_REF_TYPE`; from/to/class ∈ `type_mapping` keys; field allow-listed — a typo is exit 6). Read-side DAL `find_ontology_violations` (edge domain/range via the `find_classification_leaks` target-JOIN + COUNT=1 guard; property enum; all bound params) → `wiki-lint` `ontology-violation` (advisory, gates `--strict`, ADR-006 D-036) + `wiki-health ontology` (always exit 0). `closed_types` enforced at **index time** (reindex SKIPS an out-of-roster `$.type`), not re-swept read-side (Q-054). **NOT a write gate** — a violating page still indexes (ADR-002 §D8). **Zero DDL** (`user_version` 7); OFF ≡ byte-identical (only cybos ships a block).
- [x] **Honest denominators + two fail-open fixes (TASK 061 / ADR-006 D-036-4)**: the health layer was **built correctly and firing on nothing** — `{"total_gaps": 0}` was indistinguishable from a real green (on the live vault it read 0 because **nothing typed existed to examine**). Every health report now states its **denominator** and says so when it is 0: `wiki-health coverage` → `pages_examined`; `wiki-health ontology` → **`edges_examined` AND `property_pages_examined`** (ONE DAL call spans **TWO** populations — edges for domain/range, pages for property enums; one noun there would have re-run the bug a layer down); `wiki-lint` → an additive **per-check-keyed** `denominators` payload for **BOTH** config-driven semantic checks (`lifecycle-drift` **and** `ontology-violation` — **both** gate `--strict`, i.e. the CI rail). Invariants are asserted **per rule against that rule's own family denominator** — never `total ≤ examined` (FALSE on correct data: two rules may target one class ⇒ one page can gap twice), and edge findings are a **per-kind dict** (domain and range can both fire on the same ref row). Two fail-opens closed: (1) **trust** — `policy.EXTERNAL_PROVENANCE_KEYS` is now the ONE enumeration incl. **case variants**, *rendered* into BOTH the Python `_is_external` half and the `_EXT` SQL literal (18 live `Source:` pages had derived `internal`; residual **Q-061-4** — vault-specific keys `youtube:`/`teachable:` — is **test-pinned in its known-wrong state**); (2) **`wiki-config show.effective`** is now the parsed dataclass **OVERLAID** on the merged raw dict (it had silently dropped keys the dataclass didn't declare, while still emitting their `provenance` pointer). `FieldSpec.description` now renders in **every** surface (it was **`serve`-only**, so TASK 058's zero-UI-code invariant was narrower than believed) ⇒ `zones:`'s advisory nature is **data, not code**. **Zero DDL** (`user_version` 7), envelope keys **additive-only**, exit codes unchanged. Adoption of typed knowledge on real content → **TASK 062**.
- [x] **Shape-complete external-origin predicate + one-`json_each` pass (TASK 061 VDD fix-loop / H2 + M2)**: TASK 061's own trust fix was **itself an instance of the disease it named**. It enumerated the provenance KEYS from one constant — and never enumerated the **VALUE SHAPES**, asserting a scalar on both halves. So a **list**-valued `sources:` — the framework's OWN canonical provenance shape, which `all_cited_sources` reads and `generate-detailed-meeting-summary` writes — was invisible to the predicate, and the plural key `sources` was **not in the constant at all**. **17 live pages** whose provenance is an external URL (1 × `sources: [https://…]`, 16 × `sources: [{id, url, file}]`) derived `internal` and passed `--min-trust internal`, the filter whose entire purpose is the H-6 contract. Both halves **agreed** the whole time — **alignment is not the security property; FAIL-CLOSED is** (`security.md` had even *accepted* "list-valued `source:` — the derivation reads scalars"; that acceptance was written without a census). The constant now carries the keys **and** the shapes (scalar · list · list-of-`{url}`-objects · top-level-`{url}`-object, **a fixed set of 4 member positions, never a recursion** — no `json_tree` on the hot path, with the uncovered shapes **test-pinned** so the limit is visible rather than merely true), the alignment test is the **cross product** of keys × shapes, and live `external` goes **720 → 737** of 3267. **The security and perf fixes CONVERGE on one rewrite**: seeing *inside* a list requires walking members (`json_each`), and walking members is exactly what stops re-parsing the blob — the SQL half went from **12 `json_extract` blob re-parses per candidate row** (6 at TASK 050, silently doubled by 061-06's key growth: an "accepted" cost that grew under an edit nobody re-measured) to **ONE parse per row**, flat in the key count. **Zero DDL** (`user_version` 7); **no new index** — fixed by query SHAPE (**P-5 holds**). Q-061-4 stays OPEN and its census is corrected: **9 pages, not 18** (the same 9 carry *both* `youtube:` and `teachable:`; "18" summed two key-occurrence counts as if they were disjoint page sets — the count-the-wrong-noun bug, recurring inside TASK 061's own residual accounting).
- [x] **The drift guard covered KEYS but not SHAPES (TASK 061 VDD iteration-2 / MED-1 + LOW-1/2/3)**: the H2 fix above shipped a docstring asserting *"neither a new key nor a new shape can drift the halves apart."* The **key** half was true (both halves render from `EXTERNAL_PROVENANCE_KEYS`; a test pins every key into every SQL `IN` list). The **shape** half was **false, and nothing could have made it true**: a value shape is *control flow* (an `isinstance` ladder / a `je.type` ladder), not data, so there is no constant for the halves to share — the shape table lived in the TEST file and **neither half read it**. Measured, not reasoned: widen the Python predicate, leave the SQL alone, and the 54-case cross-product gate reports **108 passed**. This is the H2 defect class *one layer up* — **a gate asserting a coverage it does not have** — and the docstring's absolute phrasing is what would have stopped the next reviewer looking. Closed by **observing** alignment instead of asserting it: `test_sql_and_python_agree_on_generated_frontmatter` generates frontmatter from a grammar that does not know the predicate (≤4 deep) and requires `trust_tier(...) == "external"` **⟺** the row is dropped by `--min-trust internal` — a half-widening fails in **either** direction (mutation-verified ×4). It asserts its own generator reached every shape and both outcomes, so it cannot pass vacuously; and it **states what it cannot do** — revert a shape on *both* halves and they agree again, so it goes green. *Alignment is not the security property; fail-CLOSED is* — the matrix pins the **value**, this pins the **halves**, neither is redundant. **LOW-3**: `source: {url: …}` (top-level object) was a *disclosed-but-live* fail-open — "0 live pages / no tool emits it" is a fact about **tools**, while frontmatter is hand-authored and untrusted (H-6); it is the same excuse this codebase already retired for `Source:`. Closed as a **4th fixed position** (`_member_is_external`/`_member_sql` each written once, rendered at both member positions), live tier unchanged (737/3267); and `sources: [{url: [https://…]}]` was **unpinned while its four siblings were pinned** — the enumeration that *proves* the boundary had a gap exactly where a gap is invisible. **LOW-2**: the `Source:` census disagreed with itself across three surfaces (18 vs 19) inside a fix loop whose headline was *"18 was two counts of the wrong noun"*. Re-censused read-only: **19** carry the key, **18** carry an http scalar, **13 actually failed open** — and the arithmetic always said 13 (707 + 13 = 720 + 17 = 737). Written once **with its re-runnable query**. Zero DDL, no new index (LIKE count 8 → 10, still **constant in the key count**). **2475 passed**, mypy `--strict` clean.
- [x] **Write-side injection canary (H-6 item (c), 2026-07-15)**: the last concrete fix-plan item for the **H-6** prompt-injection issue (issue → `mitigated`). Ingress fencing was **advice**; this is a **mechanism**. A shared `_common.scan_injection_canaries` — three families (chat-template control tokens `<|…|>`/`[INST]`/`<<SYS>>`, shouted line-leading `SYSTEM:` role directives, `ignore`/`disregard previous instructions`-style overrides), **precision-tuned against a technical-definition FP set** (the imperative family is `ignore`/`disregard` + an injection-object noun ONLY — `override`/`forget` + `context`/`rule` are ordinary CS/ML prose and were dropped after a measured 7/8 false-positive rate; the residual rarer phrasings are left to the structural-token + classification + egress layers) — is called by **both** typed-knowledge rails (`wiki-extract-concepts`, `wiki-extract-decisions`) over the **model-authored** fields only (`name`/`definition`, `title`/`body`) → `INJECTION_CANARY`, exit 4, **zero files**: refuse-don't-escape, so a **parroted** marker never launders into a clean `_concepts/`/typed page a later scoped synthesis reads back as an instruction. ★ The verbatim **`source_quote` is deliberately exempt** — proven-in-body source content (a legit security article quotes these markers), escaped inert on egress, and `_raw/` is classification-quarantined (item (d)); scanning it would refuse the source's own evidence. Value never echoed (CWE-117). Residual is **architecturally inherent** to LLM01 (unscoped retrieval is prompt-armor-only; a re-encoded exfil payload is not a literal marker). Design: `security.md` §"write-side injection canary"; `tests/test_h6_injection_canary.py` (families · zero-FP guard set · the quote-exemption keystone · no-payload-leak). Both rails' suites + `mypy --strict` green; **zero DDL**.
- [x] **Skill-contract integrity hash-pin (H-5 item (a), TASK 067, 2026-07-15)**: the sibling of the H-6 canary — H-6 refuses an injection from an untrusted SOURCE; H-5 detects tampering with the **REASON CONTRACT ITSELF** (`skills/*/SKILL.md` loaded VERBATIM; Decision-17 means no pip-pinned bytes). The M-4 banner was a **comment**; now a **runtime + CI mechanism** across the **whole loaded-verbatim surface** (unenumerated-surface lens). ★ **Enrolment cross-checked, not single-source** (the adversarial review's MAJOR: marker-ONLY enrolment missed `obsidian-cli`, a verbatim safety-tier model with the T3 `eval`/RCE ban that `skills/.AGENTS.md` already designated same-class — a code-exec hole leaving every gate green): (1) the `SECURITY-SENSITIVE` marker grep (recursive `skills/**/SKILL.md`, shared re-pin/test) → manifest; (2) `_DESIGNATED_VERBATIM_CONTRACTS` positive allow-list, asserted `== roster` BOTH ways; (3) a `Skill({skill:X})` load-site test; (4) a completeness test grepping **ALL** skills markdown so a marker'd file in any location must be pinned-or-exempt (cycle-3: enrolment is file-shape-independent, not scoped to `SKILL.md`). **Seven** SHA-256-pinned in `config/skill-integrity.sha256` (`sha256sum -c`-verifiable) — 5 `SKILL.md` (`concept-extraction`, `decision-extraction`, `wiki-query-synthesis`, `wiki-verify`, **`obsidian-cli`** — cycle-2) **plus 2 `references/*.md`** (cycle-2 MAJOR): `obsidian-cli/references/command-reference.md` (per-command tier table) and `wiki-import/references/reason-contract.md` (the H-6 injection fence for import/sync). `wiki-verify-multi/SKILL.md` + `skills/.AGENTS.md` **exempt by name+reason**. Stated residuals (exhaustive-sweep-verified): `summarizing-meetings` (vendored → Vendoring Policy §7.4), `recipes.md` (playbooks), operator CLI-reference SKILL.md. ★ **Runtime:** each rail's `prepare` embeds a value-free `integrity` block (`verify_skill_integrity` — path + hex only, CWE-117/209) via the shared `emit_prepare_with_integrity` choke point; all four workflows STOP-before-load on `status != "ok"`; `WIKI_STRICT_SKILL_INTEGRITY=1` refuses (exit 2 `SKILL_INTEGRITY_DRIFT`). ★ **CI:** `tests/test_h5_skill_integrity.py` goes RED on any un-re-pinned edit (fix-plan (d)'s SECURITY-review intent, mechanised + vendor-neutral, no git hook); MUTATION-verified (one byte → RED → revert → green). Re-pin via `scripts/pin_skill_integrity.py --write` (reviewable diff). **Honest residual:** does not stop a maintainer who re-pins malice in the same commit (branch-protection / CODEOWNERS, out of runtime scope); options (b) signing / (c) prompt-into-Python carry the same residual at more weight — deferred (TASK 067 §7). *Ancillary:* the missing `workflows/wiki-extract-decisions.md` was created (a TASK-063 convention gap). Issue → `mitigated`. `mypy --strict` clean; **zero DDL** (`user_version` 7); no new dep, no LLM client.
- [x] **Template**: extended template applied (Sections 1-11 covered + §3.4 Sequence Diagram + §1.5.7 vendored-module subsection + §7.4 Vendoring Policy subsection).
