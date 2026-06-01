# ARCHITECTURE: LLM Wiki MVP

> This is a living INDEX. Section bodies live in
> [docs/architectures/](./architectures/). Edit the relevant chunk and
> keep the one-line summary on this page in sync.

> **Status**: **TASK 007 SHIPPED 2026-05-29** — Epic 7 **RAG layer** entry-point
> `wiki-query` (R-6): retrieve (FTS5 BM25 + alias expansion) → orchestrator-owned
> cited synthesis (Decision-17 `prepare`/`apply`; no `anthropic` import) → file a
> **first-class compounding** `_queries/<slug>.md` page (indexed `type=query`,
> FTS-searchable, `cited` backlinks, §D8-durable). **Zero schema DDL**
> (`pages.type='query'`, `ref_type='cited'`, `event_type='query'`, generic
> `source_state` all pre-exist; `user_version` stays **4**); **two code-only
> structural changes** — `layout.py` adds `_queries` (R-X1-forward role split
> `INGEST_SHARED_SUBDIRS`/`HOST_ONLY_SUBDIRS`), and a type-aware reindex read-side
> parses `cites:`→`'cited'` (R-6.5e, the §D8 fix mirroring R-5.3). Scope = R-6
> only; R-7 (`wiki-research`) + R-8 (`wiki-verify-multi`) unblocked + deferred.
> 10 beads (Stub-First, green-throughout; 3 VDD gates APPROVED + `/vdd-multi` ×2
> + real-content dogfood — DF-Q1 keyword-OR retrieval fix); **599 pytest**, mypy
> strict clean (60 files).
>
> **TASK 008 (R-8 `wiki-verify-multi`) — SHIPPED 2026-05-29** (11 beads, Stub-First
> green-throughout; 4 VDD gates incl. `/vdd-adversarial` on the plan; **666 pytest**,
> mypy strict clean (61 files); one found-in-dev serious-deviation fixed — the
> verdict↔query `pages` PK collision, resolved via the `verify-<query-slug>` distinct
> slug). Schema **v4→v5**. Nothing auto-committed): the RAG-layer
> *verification* half — an **off-by-default** four-critic **prose** audit
> (factual-grounding / logic-coherence / security-injection / completeness-
> faithfulness) of a filed `wiki-query` answer against its cited sources → a
> first-class `_verifications/<slug>.md` **verdict page** (`type=verification`,
> `verifies` backlink, §D8-durable via the **R-8.5e** reindex read-side that
> generalises R-6.5e). FAIL = record the verdict + **non-zero exit (6)**; the
> Class-A answer is **never mutated** (D-008-3). **First RAG-layer task requiring
> DDL — schema v4→v5** (verdict-page type + `verifies` ref + `verify` event are
> NOT pre-provisioned; Class-B reindex migration, no in-place ALTER). Adds
> `_verifications` as the **second `HOST_ONLY_SUBDIRS` member** (proving the
> R-X1-forward role-split generalises) and is **layout-agnostic by construction**
> (reads sources via `pages.file_path` + DAL, never a reconstructed subdir path —
> a binding R-X1/R-X2-compat constraint, C-8/NFR-7). Decision-17 `prepare`/`apply`
> (no `anthropic`). Spec + reviews: [tasks/](./tasks/) + [reviews/](./reviews/).
>
> **TASK 009 (R-9 critic-prompt hardening) — SHIPPED 2026-05-29** (6 beads, Stub-First
> RED→GREEN; 3 VDD gates APPROVE-WITH-NITS + security-audit PASS + code-review APPROVE;
> 697 pytest / 4 skip, mypy strict clean; **zero code/schema change**, `user_version` 5;
> nothing auto-committed). **Measured delta** (baseline thin → enriched scoped, same eval
> set + deterministic grader): unsanctioned lens-bleed violations **10→3 (−70%)**, security
> false-positives **2→0**, gate verdict-correctness **0.571→1.0** (both bleed-induced
> verdict flips eliminated), recall **0.571→1.0** with **injection recall held at 100%**;
> the C2 `factual`-backstop verified (security-suppressed injection still FAILs). Residual
> completeness-leak (3 viol) + a flat severity-exact-match are documented LOWs.
> A quality hardening of the R-8 `wiki-verify` four-critic prompt — **scoped
> (anti-bleed) + severity-calibrated lenses + a durable committed eval set**,
> motivated by the TASK-008 dogfood (lens-bleed: the same defect reported by 3–4
> lenses; uncalibrated severity — `high` vs `critical` for one hallucination).
> **Prompt + committed eval assets only — zero code/schema change** (`user_version`
> stays **5**; the verdict JSON contract + lens vocab `{factual,logic,security,
> completeness}` + severity vocab `{low,medium,high,critical}` + grounding gate +
> `factual|security ≥ --fail-on` rule all byte-stable; Decision-17 preserved). The one
> binding constraint is **C2**: anti-bleed must keep the `factual`+`security`
> FAIL-redundancy on injections (the **sanctioned overlap**, excluded from lens-purity).
> Eval = **orchestrator-graded Workflow+grader** (not `run_eval.py` — that's a
> trigger-eval; not a `pytest` gate). **SECURITY-SENSITIVE** prompt surface → code
> review + security audit mandatory. Spec: [tasks/](./tasks/) (R-9 in
> [verification-map](./architectures/verification-map.md) + [functional-architecture](./architectures/functional-architecture.md) §Verification Layer).
>
> **TASK 010 (R-9 follow-on — `wiki-verify` eval-v3, adversarial reasoning extension)
> — IN PROGRESS:** widens the committed benchmark to four classes v2 never tested —
> **temporal**, **negation/polarity-flip**, **multi-document** (composition +
> cross-source conflict), **entity-confusion** — as a self-contained
> `evals-v3.json` (22 cases: 18 seeded + 4 natural multi-doc; 6 new fictional
> domains). **Fixtures + test + recorded `reports/v3/` measurement only — ZERO
> code/schema change** (`user_version` stays **5**; `grade.py` is **source-blind**
> so multi-source is free for the grader; v3 is a separate file so the v1/v2
> reproducibility pins stay byte-identical). Motivated by the external v2 audit:
> all 32 v2 cases have exactly **one** `examined` source, leaving the
> `examined[]`/grounding-gate multi-source audit path **unexercised**. **Decision
> D-010-1 (cross-source conflict → `completeness`):** an unreconciled conflict
> between examined sources that the answer hides is a **material omission**
> (`completeness`/`medium`, PASS under the current FAIL rule) — NOT `factual`
> (each value is grounded in *a* source) and NOT `logic` (the inconsistency is
> across sources, not within the answer). The `SKILL.md` sentence specifying this
> is **deferred** to a separate security-reviewed PR (see [KNOWN_ISSUES](./KNOWN_ISSUES.md));
> v3 ships the conflict *cases* now. v3 does **not** touch the live prompt → the
> dataset/test are not security-sensitive (the deferred rule is). Spec:
> [tasks/](./tasks/). Post-ship hardening **D-010-1** (cross-source-conflict rule →
> `completeness`, SKILL.md v1.0→1.1) and **D-010-2** (misstatement≠omission anti-bleed,
> v1.1→1.2) merged 2026-06-01, each gated by a full-corpus v1+v2+v3 no-degradation A/B
> (D-010-2 multi-rep: inversion-bleed purity mean 4.8→2.8, recall 1.0 / FP 0 held).
>
> **TASK 011 (R-9 follow-on — `wiki-verify` eval-v4, deep multi-hop extension) —
> SHIPPED 2026-06-01** (13 cases / 3 chains / 3 domains; 722 pytest / 4 skip, mypy strict
> clean; **zero code/schema/prompt change**, `user_version` 5; 3 gates clean — code-review
> MERGE + security clean-pass + logic PASS): adds `evals-v4.json` — a focused benchmark on **4–5-source dependency
> chains** (3 chains, 3 new fictional domains) and the **broken-middle-hop** failure
> class (correct endpoints, fabricated middle link → unsupported conclusion), which v3
> never tested (v3's max chain was 3 sources, mostly 2-hop joins). **Fixtures + test +
> recorded `reports/v4/` measurement only — ZERO code/schema/prompt change**
> (`user_version` stays **5**; `grade.py` is source-blind so deep chains are free; v4 is
> a separate file so v1/v2/v3 reproducibility pins stay byte-identical). Headline metric:
> **broken-middle-hop recall** — does the shipped 4-critic prompt verify every hop or only
> the endpoints? **Result: NO endpoint-bias** — broken-middle-hop recall **1.0** = wrong-terminus
> recall 1.0, verdict-match 1.0, FP 0 (incl. a held `security`-guard on CVE language); the
> prompt catches a fabricated interior link as reliably as a wrong terminus. Carry-over
> D-010-2 completeness-bleed residual (3, lens-purity noise, not re-fixed). No prompt fix
> warranted. Spec: [tasks/](./tasks/) + `reports/v4/benchmark-v4.md`.
>
> **TASK 012 (R-X1 + R-X2 A-B + R-X3 — universal config-driven layout engine + dev-vault
> bootstrap) — IN PROGRESS (2026-06-01):** replaces ~15 hardcoded layout surfaces
> (`PAGE_SUBDIRS`, the `Lessons/` two-tier walk, `TYPE_MAPPING`/`_PATH_TYPE_FALLBACK`,
> `_WIKILINK_RE`, slug rules) with a **YAML-config-driven engine** (new
> `scripts/wiki_index/layout_config.py` + `config/layout-config.schema.yaml` + built-in
> `scripts/wiki_index/layouts/{karpathy,dev-project,obsidian-personal}.yaml`). **Two
> separate config layers** (D-012-2): the existing per-vault identity/policy
> (`config_loader`) is untouched; the new layer carries per-layout-class *grammar*.
> `flat`/`per-project` alias to `karpathy.yaml`. **Byte-identical for Karpathy**
> (golden-snapshot harness + `test_karpathy_config_matches_layout_constants`;
> three slug surfaces kept distinct; `identity` slug strategy). **ReDoS = stdlib `re`
> + load-time budget gate** (D-012-3, no `regex` dep). **PW-G/H/Q INCLUDE NOW** (D-012-1):
> the `auto_indexes[]` renderer + KNOWN_ISSUES splitter + `check_auto_generated_unchanged`
> lint guard, dogfooded by migrating this repo's `docs/KNOWN_ISSUES.md` → per-file
> Class-A `docs/issues/*.md` + a Class-B auto-rendered ledger (the **§D8 "rebuildable
> markdown" sub-case** — ADR-002 TASK-012 amendment, gating PW-H). **Zero DDL**
> (`user_version` stays **5**; new doc types via the TYPE_MAPPING tag-route). R-X2
> extends `wiki-init --layout` (5 values) + bootstraps this repo + one peer as dev-vaults
> (`wiki-search "ADR-002" --vaults all`). **R-X2 Phase C** (the agentic-development
> `archive_protocol.py` hook) is **DEFERRED** (D-012-4) + recorded in ROADMAP — stabilise
> the wiki first. See §3.5 + ADR-002 §D8 amendment. Spec: [tasks/](./tasks/).
> Predecessor: **TASK 006** (`ba4fa92`) — consolidation/hardening
> (schema **v3→v4**). ADRs 001
> + 002 in effect; §D8 amended for the entity_aliases PK (v2→v3, L-4) and the
> v3→v4 hygiene changes. Living document — current architecture, not change
> history. Shipped specs live in [tasks/](./tasks/) + [plans/](./plans/) +
> [KNOWN_ISSUES.md](./KNOWN_ISSUES.md). For shipped task specs (history, decisions, hardening
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

Functional components (Configuration Resolver, Source Adapters, Index Layer DAL, Search Layer FTS5, Lint Layer, Workflow Orchestrator, Migration Tools, Concept Extractor, **Entity Resolver** `wiki-confirm`+`wiki-alias`+`wiki-merge`, **RAG Query Layer** `wiki-query`) and the connection diagram between them. Includes the full `wiki-extract-concepts` `prepare`/`apply` contract, candidates JSON schema, the TASK 005 Entity Resolver CLI surface + exit-code envelopes (incl. `wiki-merge` duplicate-fold), the TASK 007 `wiki-query` `prepare`/`apply` RAG contract (retrieval envelope + answer/citations contract + grounding gate + `cited`-backlink self-index), operational invariants, and RTM cross-reference.

→ [details](./architectures/functional-architecture.md)

---

## 3. System Architecture

Architectural style (layered + plugin), system-component breakdown (Skill Layer → Adapters → DAL → SQLite), component-interaction diagram, and the UC-08 Concept Extraction sequence diagram (calling agent owns LLM synthesis; Python skill is deterministic plumbing only). **§3.5 (TASK 012 / R-X1)** adds the **config-driven Layout Engine**: two separate config layers (per-vault identity via `config_loader` + per-layout grammar via the new `layout_config` + built-in `layouts/{karpathy,dev-project,obsidian-personal}.yaml`), the `iter_pages` walk that converges the four hardcoded two-tier walks, the byte-identity strategy (karpathy.yaml = validated projection of `layout.py`; three slug surfaces kept distinct), the stdlib-`re` ReDoS load-gate, and the PW-H `auto_indexes[]` renderer + PW-Q lint guard (Class-B "rebuildable markdown" — zero DDL).

→ [details](./architectures/system-architecture.md)

---

## 4. Data Model (Conceptual)

Conceptual entities (Vault, Page, Entity, EntityAlias, PageEntityRef, SourceState, LogEvent) with key attributes, relationships, business rules, and ADR-002 Class A/B/C layering for each. Includes the entity write-path + downgrade-guard semantics, the TASK 005 two-tier confirm/candidate resolution (`is_candidate` as Class A frontmatter), the EntityAlias activation (PK `(vault_id, alias)`, L-4 closed; schema v2→v3 migration), the duplicate-merge path (R-4.7: pure-DML re-pointing, alias-as-redirect, no merge-ledger table), and the TASK 007 RAG additions (query page as a first-class compounding `type=query` artifact; `ref_type='cited'` query→source backlinks with the R-6.5e reindex read-side; `source_state` reuse for query idempotency — all **zero-DDL**, `user_version` stays 4).

→ [details](./architectures/data-model.md)

---

## 5. Interfaces

External APIs (CLI surface, JSON-envelope shape), internal interfaces (`IndexRepository` ABC + concrete `SQLiteRepository`, incl. the TASK 005 entity-resolution methods + `merge_entities` + alias-aware `find_orphan_links`, and `wiki-confirm`/`wiki-alias`/`wiki-merge` error codes; the TASK 007 `wiki-query` `prepare`/`apply` CLI surface + `check_query_state`/`record_query_state` DAL methods + error codes), and integrations (wiki-ingest manifest contract v1.1).

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
- **Q-012-e (TASK 012): `auto_indexes[]` template mechanism** — **RESOLVED: dependency-free Python renderer** driven by `group_by` / `sort_within_group`, with an optional `assets/<name>.md.tmpl` (`string.Template`) for the surrounding shell. No Jinja dependency (NFR-3). See §3.5.
- **Q-012-f (TASK 012): per-vault layout-override merge policy** — **RESOLVED: `paths[]`/`ref_extraction[]` REPLACE on operator-supplied key; scalars overlay.** Predictable (no partial-list merge surprises); pinned by schema-validation tests. See §3.5.
- **Q-012-g (TASK 012): peer dev-vault for the cross-project acceptance (UC-33)** — default `Universal-skills` unless operator prefers `trade-agents`; either satisfies the bar (low-stakes, operator confirms at Bead 15).

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

- **Q-A6 (TASK 007 — decide BEFORE R-6.6 planning): query idempotency hash content.** Should the `source_state` `value` hash the **question only** or **question + the ordered retrieved `project/slug` set**?
  - **Default assumption**: hash question + retrieved-slug-set, so a re-query after the corpus changed re-synthesises (defines UC-17 `is_unchanged` semantics + whether the compounding loop picks up new sources). Borderline-blocking — finalise in Planning.

- **Q-A7 (TASK 007): `cites:` identifier format.** Bare `slug` vs `project/slug`?
  - **Default assumption**: `project/slug` (disambiguates course-tier vs vault-tier; matches the `wiki-search` link shape; is the grounding comparison key). Non-blocking.

- **Q-A8 (TASK 007): body citation rendering.** Inline `[[project/slug]]`, a trailing `## Sources` list, or both?
  - **Default assumption**: a trailing `## Sources` list of `[[project/slug]]` wikilinks (Obsidian-native backlinks); `cites:` frontmatter remains the machine-readable source of truth. Non-blocking — interacts with Q-A9.

- **Q-A9 (TASK 007 — Task Reviewer O-2 / Arch-Reviewer M-1/M-2): dual ref-type coexistence + reindex mechanism.** A query page rendering both `cites:` (→ `'cited'` via R-6.5e) and body `## Sources` wikilinks (→ `'mentioned'` via `extract_wiki_links`) produces two `page_entity_refs` rows to the same target with different `ref_type`.
  - **Resolved (design):** allowed and consistent — the composite PK keeps the two rows distinct. **Mechanism (M-1):** both ref-types are written in the page's **single** `replace_refs` call (the `cited` refs are unioned into Step 2's `out.refs`) — never a second `replace_refs`, which is delete-all-then-insert and would clobber. **AM-3 (M-2):** Step 2.5 canonicalizes `cited` refs' `entity_slug` through the alias map just like `mentioned` refs (a merged-away cited target still resolves), rewriting `entity_slug` only — `ref_type` is preserved, so `cited` never degrades to `mentioned` (UC-20 holds structurally). `find_orphan_links`/backlink consumers key on the canonical slug and are unaffected. Whether to render body wikilinks at all (Q-A8) is the only residual sub-choice (`cites:` frontmatter is already authoritative). Non-blocking.

---

## Verification Map

Requirement → architecture-surface traceability for Phase 3a MVP (R-01..R-26), Concept Extractor (R-30..R-43), wiki-ingest Vendoring (R-45..R-57), Entity Resolver (R-4 + R-5, TASK 005), and RAG Query Layer (R-6, TASK 007).

→ [details](./architectures/verification-map.md)

---

## Quality Checklist (VDD)

- [x] **Data Model**: entities + key attributes + relationships + indexes defined (§4 + SCHEMA-v2.sql). Entity write-path documented in §4.1 Entity Business Rules.
- [x] **Traceability**: Verification Map covers Phase 3a (R-01..R-26), Concept Extractor (R-30..R-43), and wiki-ingest Vendoring (R-45..R-57).
- [x] **Security**: AuthN — N/A (single-user); AuthZ — file permissions; path-traversal + SQL-injection protections explicit (§7.3). `validate_inside_vault` applied to every `_concepts/` write path AND every operator-supplied path (source-page, candidates-file).
- [x] **Multi-vault**: every operation carries a `vault_id` predicate or is scoped to `vault_root`. Vendored `ingest()` accepts `vault_id` as explicit kwarg; no hash-fallback.
- [x] **Stub-First**: TASK 005 Entity Resolver is designed Stub-First (DAL signatures + RED tests before logic); `resolve_entity` is promoted from deferred stub → implemented (R-4.5).
- [x] **RAG Query Layer (TASK 007)**: `wiki-query` designed as a deterministic `prepare`/`apply` skill (Decision-17, no LLM in Python); query page is a first-class compounding `type=query` artifact; durability secured by the R-6.5e `cites:`→`'cited'` reindex read-side (the §D8 gate, mirroring R-5.3); zero schema DDL; grounding enforced in Python (`CITATION_NOT_RETRIEVED` / `NO_CONTEXT`).
- [x] **ADR-001 clarification**: Source Adapters component preserves the single-indexer invariant while allowing derivative page writes (concept pages) by downstream skills.
- [x] **Backward compat**: subprocess fallback path fully preserved (§1.5.2 FALLBACK PATH); external `wiki-ingest` binary remains optional.
- [x] **Template**: extended template applied (Sections 1-11 covered + §3.4 Sequence Diagram + §1.5.7 vendored-module subsection + §7.4 Vendoring Policy subsection).
