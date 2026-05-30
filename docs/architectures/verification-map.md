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

### Entity Resolver Requirements (TASK 005 — R-4 + R-5)

> Epic 7 completion. Closes KNOWN_ISSUES **L-4**; unblocks ROADMAP **R-X5**.
> Persistence is Class A frontmatter + Class B mirror throughout (ADR-002 §D8).

| Requirement | Architecture coverage | Test / AC reference |
|---|---|---|
| R-4.1 (is_candidate Class A round-trip) | §4.1 Entity Business Rules (Class A frontmatter; reindex reads flag); §2.1 Entity Resolver "Class A/B durability" | UC-14 AC (delete DB → reindex → candidate stays candidate) |
| R-4.2 (`wiki-confirm <slug>`) | §2.1 Entity Resolver CLI surface; §2.1 Index Layer `set_entity_candidate` | UC-09 AC (frontmatter + DB flip; idempotent) |
| R-4.3 (`--undo` demotion) | §2.1 Entity Resolver CLI surface; `set_entity_candidate` bypasses `MIN()` | UC-09 A4 |
| R-4.4 (`--auto [--threshold N]`, N=3) | §2.1 Index Layer `recompute_mentions` + `auto_promote_candidates`; §4.1 Entity Business Rules (auto-promote) | UC-10 AC (fresh mentions; `--dry-run` no-write; `≥` boundary) |
| R-4.5 (`resolve_entity` implemented, incl. alias-aware `find_orphan_links` R-4.5d) | §2.1 Index Layer `resolve_entity` (slug or alias → Entity) + `find_orphan_links` (alias-aware) | UC-12 (alias resolution feeds search); UC-15 AC (merged-away slug not orphaned) |
| R-4.6 (extract-concepts keeps Class A flag) | §2.1 Concept Extractor (writes `is_candidate: true`); §4.1 Entity | regression: applied candidate survives `reindex --full` as candidate |
| R-4.7 (`wiki-merge <from> <into>` duplicate fold) | §2.1 Entity Resolver CLI surface + `merge_entities` (pure-DML, no DDL) + durability "Reindex ref-canonicalization (AM-3)"; §4.1 Entity "Merge path" + PageEntityRef "Merge re-pointing" + "Canonical-slug invariant (AM-3)"; §4.2 (uses `idx_refs_entity` + `idx_aliases_entity`) | UC-15 AC (resolve(from-surface)→into; mentions = dedup union **survives full reindex** via AM-3; no orphans; full-reindex reproduces from Class A alone; `--dry-run` no-write) |
| R-5.1 (`wiki-alias --add`) | §2.1 Entity Resolver CLI; §4.1 EntityAlias Business Rules; §2.1 Index Layer `add_alias` | UC-11 AC (frontmatter + DB; collision refused) |
| R-5.2 (`--remove` / `--list`) | §2.1 Entity Resolver CLI; Index Layer `remove_alias` / `list_aliases` | UC-11 A3/A4 |
| R-5.3 (reindex mirrors `aliases:`) | §4.1 EntityAlias (Class A→B path); §2.1 Entity Resolver durability (report+skip on PK conflict) | UC-14 AC (alias rebuilt from frontmatter) |
| R-5.4 (PK → `(vault_id, alias)`, L-4) | §4.1 EntityAlias PK rule; §4.4 Migrations v2→v3; SCHEMA-v2.sql + sql/wiki-index-v2.sql | migration: bump `user_version` 2→3 + `wiki-reindex --full` |
| R-5.5 (search alias expansion, default on) | §2.1 Skill Layer `wiki-search`; Index Layer `expand_query_aliases` | UC-12 AC (page w/ only "Hermes Framework" hit by "Hermes"; `--no-expand-aliases` byte-identical) |
| R-5.6 (lint alias collision) | §2.1 Skill Layer `wiki-lint`; Index Layer `find_alias_collisions` + Lint-Layer frontmatter scan | UC-13 AC (in-table + cross-table + Class A frontmatter; `--json` parity) |

### RAG Query Layer Requirements (TASK 007 — R-6 `wiki-query`)

> Epic 7 RAG layer entry-point. Decision-17 `prepare`/`apply` split (no LLM in
> Python). Query page = first-class compounding artifact. **Zero schema DDL**
> (`user_version` stays 4); two code-only structural changes (`layout.py` +
> R-6.5e reindex read-side). Scope = R-6 only (R-7/R-8 deferred + gated).

| Requirement | Architecture coverage | Test / AC reference |
|---|---|---|
| R-6.1 (`prepare` deterministic retrieval) | §2.1 RAG Query Layer CLI surface (`prepare`) + `prepare(args)` fn; reuses Index Layer `expand_query_aliases`+`search_pages` | UC-16 AC (retrieval envelope; `--limit` default 10; alias expansion default-on) |
| R-6.2 (orchestrator-owned synthesis, Decision-17) | §2.1 RAG Query Layer "Design pattern" + "Answer + citations contract (`wiki-query-synthesis`)"; §3 sequence (calling agent owns synthesis) | grounding contract: every cite ∈ retrieved set; H-6 untrusted-retrieval prompt-armor |
| R-6.3 (`apply` writes Class A query page) | §2.1 RAG Query Layer CLI surface (`apply`) + `apply(args)` fn (atomic-write, `_sanitize_markdown_text`, `--question-hash` TOCTOU); §4.1 Page (query page Class A) | UC-16 AC (`type: query` + `cites:` written); `QUESTION_CHANGED` on hash mismatch |
| R-6.4 (compounding — indexed + back-linked) | §2.1 RAG Query Layer Outputs + Operational invariants (self-index via direct `upsert_page`+`replace_refs`, **not** manifest/`main(argv)`); §4.1 PageEntityRef (`cited` ref) | UC-19 AC (filed query page returned by search; `cited` refs exist; `--types` filter) |
| R-6.5 (`_queries/` discoverable) | §4.1 Page (layout change); §4.4 Migrations (v4 unchanged, code-only); [layout.py](../../scripts/wiki_index/layout.py) `_queries` in `PAGE_SUBDIRS`/`SCAFFOLD_DIRS`/`_PATH_TYPE_FALLBACK` | UC-20 AC (query page rediscovered + re-indexed `type=query`) |
| **R-6.5e** (reindex `cites:`→`'cited'` read-side — §D8 fix) | §4.1 PageEntityRef "Citation ref" + "Reindex phase order" (union into Step-2 `out.refs`; Step-2.5 AM-3 preserves `ref_type`); §4.4 Migrations (code-only change #2); §2.1 RAG Query Layer "§D8 durability" + `reindex.py` type-aware branch | UC-20 is the binding §D8 gate (`cited` refs reconstructed from `cites:` frontmatter alone; **not** degraded to `mentioned`, not clobbered by the body-wikilink pass) |
| R-6.6 (idempotency / re-run) | §2.1 Index Layer `check_query_state`/`record_query_state`; §4.1 SourceState (query reuse; Q-A6 hash-content) | UC-17 AC (unchanged re-query = no synthesis, no write; `--force` re-synthesises) |
| R-6.7 (grounding / no-hit refusal) | §2.1 RAG Query Layer Operational invariants ("grounding enforced in Python"); CLI surface `--min-hits` + `CITATION_NOT_RETRIEVED`/`NO_CONTEXT` | UC-18 AC (no synthesis on empty retrieval); UC-21 AC (citation ∉ hit set refused at boundary, `project/slug` key) |

### Verification Layer Requirements (TASK 008 — R-8 `wiki-verify-multi`)

> Epic 7 RAG-layer verification half. Decision-17 `prepare`/`apply` split (no LLM
> in Python). Verdict page = first-class compounding artifact (`type=verification`,
> `verifies` backlink, §D8-durable via R-8.5e). **Schema v4→v5** (verdict type +
> `verifies` ref + `verify` event NOT pre-provisioned). Off-by-default; FAIL =
> record verdict + non-zero exit, never mutate the answer. Layout-agnostic source
> access + verdict-surface role-split are a **binding** R-X1/R-X2-compat requirement.

| Requirement | Architecture coverage | Test / AC reference |
|---|---|---|
| R-8.1 (`prepare` deterministic envelope) | §2.1 Verification Layer CLI surface (`prepare`) + `prepare(args)` fn; reads query page + cited sources via `get_page`/`pages.file_path` | UC-22 AC (envelope assembled; cited bodies read via `file_path`); UC-28 AC (works on non-Karpathy layout) |
| R-8.2 (orchestrator-owned 4-critic audit, Decision-17) | §2.1 Verification Layer "Design pattern" + "Verdict contract (`wiki-verify`)"; four prose lenses (factual/logic/security/completeness) | grounding contract: every `findings[].source` ∈ examined set; H-6 untrusted-content prompt-armor |
| R-8.3 (`apply` writes Class A verdict page) | §2.1 Verification Layer CLI surface (`apply`) + `apply(args)` fn (atomic-write, `_sanitize_markdown_text`, `--answer-hash` TOCTOU); §4.1 Page (verification page Class A) | UC-22 AC (`type: verification` + `verifies:` + `verdict:` written); `ANSWER_CHANGED` on hash mismatch |
| R-8.4 (compounding — indexed + back-linked) | §2.1 Verification Layer Outputs + Operational invariants (self-index via direct `upsert_page`+`replace_refs`, **not** manifest/`main(argv)`); §4.1 PageEntityRef (`verifies` ref) | UC-25 AC (filed verdict page returned by `--types verification` search; `verifies` ref exists) |
| R-8.5 (`_verifications/` discoverable **and type-mapped**) | §4.1 Page (verification page, layout role-split); §4.4 Migrations (v4→v5, the three-part code-side change); [layout.py](../../scripts/wiki_index/layout.py) `_verifications` in `HOST_ONLY_SUBDIRS` **+** [normalization.py](../../scripts/wiki_index/normalization.py) `TYPE_MAPPING["verification"]` + `_PATH_TYPE_FALLBACK[VERIFICATIONS_SUBDIR]` (without the mapping `normalize_frontmatter` raises `UnmappedTypeError` → page skipped, never indexed — "layout.py alone is insufficient", the TASK 007 C-1 lesson) | UC-26 AC (verdict page rediscovered + re-indexed `type=verification`) |
| **R-8.5e** (reindex `verifies:`→`'verifies'` read-side — §D8 fix) | §4.1 PageEntityRef "Verifies ref" (union into Step-2 `out.refs`; `_frontmatter_refs(db_type)` generalising R-6.5e; Step-2.5 AM-3 preserves `ref_type`); §4.4 Migrations; §2.1 Verification Layer "§D8 durability" + the R-8.5e function note (prerequisite `normalization.py` mapping + the `reindex.py` read-side) | UC-26 is the binding §D8 gate (`verifies` ref reconstructed from frontmatter alone; **not** degraded to `mentioned`, not clobbered; `--full` **and** `--delta`) |
| R-8.6 (idempotency / re-run) | §2.1 Index Layer `check_verify_state`/`record_verify_state`; §4.1 SourceState (`source_kind='verification'`; Q-008-b verify_hash = `sha256(answer_hash ‖ examined slugs)`) | UC-24 AC (unchanged re-verify = no critics, no write; `--force` re-verifies; changed answer/source re-triggers) |
| R-8.7 (FAIL semantics — record + non-zero exit, no mutation) | §2.1 Verification Layer Exit-code contract (VERDICT_FAIL exit 6, distinct from errors) + Operational invariants ("answer never mutated"); `--fail-on` default `high` (Q-008-e) | UC-23 AC (FAIL → exit 6 + verdict filed; answer byte-identical; `--fail-on=none` → exit 0) |
| R-8.8 (grounding / no-fabrication of findings) | §2.1 Verification Layer Operational invariants ("grounding enforced in Python"); `NO_SOURCES`/`FINDING_SOURCE_NOT_EXAMINED`/`INVALID_VERDICT` | UC-22 (empty `cites:`→`NO_SOURCES`); UC-27 AC (stray finding source / answer-change refused at boundary, `project/slug` key) |
| R-8.9 (schema v4→v5) | §4.4 Migrations v4→v5 (`pages.type+='verification'`, `ref_type+='verifies'`, `event_type+='verify'`, `index_meta` view; `user_version` 4→5; reindex-rebuild migration, no ALTER); §4.1 Page/PageEntityRef | `tests/test_schema_v5.py` (new enums + `user_version=5`); UC-26 §D8 round-trip |
| R-8.10 (off-by-default opt-in) | §2.1 Verification Layer Purpose + Design pattern ("`wiki-query` never invokes it"); `workflows/wiki-verify-multi.md` recipe | regression: `wiki-query apply` does not call `wiki-verify-multi`; `wiki-query` behaviour unchanged |
| C-8/NFR-7 (layout-agnostic — binding R-X1/R-X2-compat) | §2.1 Verification Layer Stack position + Operational invariants ("layout-agnostic source access"); §4.1 Page (role-split); reads via `pages.file_path`, verdict surface only in `layout.py` | UC-28 AC (cited source resolved on non-Karpathy layout) + grep guard (no `PAGE_SUBDIRS` literal in `wiki_verify_multi.py`) |

### Critic-Prompt Hardening Requirements (TASK 009 — R-9 `wiki-verify-critic-rubric`)

> Quality hardening on the shipped R-8 (**R-8 stays DONE**; not a new ROADMAP epic).
> **Prompt + committed eval assets only — zero code/schema change** (`user_version` 5;
> verdict contract + lens/severity vocab + grounding gate + FAIL rule byte-stable;
> Decision-17 preserved). Motivated by the 2026-05-29 real-content dogfood (lens-bleed:
> same defect reported by 3–4 lenses; uncalibrated severity). No Data Model / Interface
> / schema change.

| Requirement | Architecture coverage | Test / AC reference |
|---|---|---|
| R-9.1 (anti-bleed lens scoping) | §2.1 Verification Layer "Critic-prompt scoping + calibration" (exclusive lens domains; non-FAIL lenses banned from re-reporting injections) | UC-1 (lens-purity metric) + UC-2/UC-3 AC (no *unsanctioned* finding under two lenses) |
| R-9.2 (severity rubric) | §2.1 "Critic-prompt scoping + calibration" (one shared anchored scale; same defect → same severity; vocab pinned to `{low,medium,high,critical}`) | eval severity-match metric (the same hallucination no longer `high`-vs-`critical` split) |
| R-9.3 (per-lens definitions + few-shot) | §2.1 "Critic-prompt scoping + calibration" (supported/unsupported defs; **defanged** few-shot; skill-creator inline-block limits) | review: examples carry no live directive; SECURITY audit clean |
| R-9.4 (durable committed eval set) | §2.1 "Eval harness" (`skills/wiki-verify/evals/evals.json` + fixtures; recall/lens-purity/severity expectations; C2 overlap excluded) | committed `evals.json` diff; cases cover the dogfood matrix + edge cases (logic-only, omission-only, false-positive guard, borderline overclaim) |
| R-9.5 (baseline-vs-enriched measurement) | §2.1 "Eval harness" (orchestrator-graded Workflow+grader; one-time delta; **NOT** pytest; `run_eval.py` unused — trigger-eval only) | recorded baseline→enriched delta: lens-purity↑, severity-match↑, **recall non-regression (injection 100%)** |
| R-9.6 (invariants preserved) | §2.1 "Critic-prompt scoping + calibration" ("zero code/schema change; verdict contract byte-stable"); the C2 backstop; Decision-17 | existing deterministic `tests/test_wiki_verify_*` green; `user_version` 5; no `import anthropic`; SECURITY audit + code review clean |
| **C2** (security FAIL-redundancy — binding) | §2.1 "The C2 backstop" (`factual`+`security` both MAY flag an injection — the one sanctioned overlap; lens-purity excludes it) | adversarial eval case: "the `security` lens under-reports the injection" still FAILs via `factual` (a FAIL-lens) |

---

