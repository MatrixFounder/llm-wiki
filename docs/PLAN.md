# Development Plan: TASK 003 — wiki-extract-concepts (v2 / post-TASK-004 resume)

> **Status**: DRAFT (2026-05-27) — awaiting plan-reviewer sign-off.
> **Task ID**: 003 / Slug: `wiki-extract-concepts`
> **Source spec**: [docs/TASK.md](./TASK.md) (active RTM R-30..R-43; R-44 RETRACTED; Issues I-7.0..I-7.14; UC-08, UC-09; Decisions 6, 7, 8, 10, 15, 16; smoke recipe §7 — 12 steps).
> **Architecture spec**: [docs/ARCHITECTURE.md](./ARCHITECTURE.md) §2.1 (Concept Extractor component), §3.4 (UC-08 sequence diagram), RTM coverage map (~L1480-1498). Architecture updates **already shipped** for v2; no further architecture work in this plan.
> **Methodology**: **Stub-First (TDD)**. Every code-bearing bead lands in two passes — Phase 1 stubs + E2E tests (Red→Green on stubs), Phase 2 logic. Documentation-only beads (I-7.2 skill wrapper) skip Phase 1; verification-only beads (I-7.14) run direct checks.
> **Predecessor**: TASK 004 (`wiki-ingest-vendoring`) — **SHIPPED** 2026-05-27 (commit `c409fd8`). In-process `ingest()` available; `wiki_enrich.py` exposes the manifest-consumer functions this task extracts.
> **Out of scope (carried forward from TASK.md §1.2 / §1.3)**: R-4 (`wiki-confirm`); R-5 (`wiki-alias`, search expansion, lint-collision); Epic 8 (vector / semantic); batch extraction across multiple sources; `--manifest-file` / `--manifest-stdin` on `wiki-enrich` (R-44 / I-7.15 — DROPPED by Decision-15); synthesiser-subagent hook into vendored `ingest()`.

---

## 0. Architectural Foundation (Reference)

| Layer | Owns | Class (ADR-002 §D8) |
|---|---|---|
| `scripts/wiki_skills/_manifest_consumer.py` (**new neutral module**, I-7.0) | `validate_manifest`, `index_from_manifest`, `WikiIngestError` — neutral sub-layer below skills | Glue (sub-layer below skills) |
| `scripts/wiki_skills/wiki_enrich.py` (back-compat re-export) | Re-exports the three symbols + `_validate_manifest` alias for one release cycle | Class A producer (raw-source synthesis path) |
| `scripts/wiki_skills/wiki_extract_concepts.py` (**new skill entry-point**) | Argparse, LLM extraction, dedup classification, concept-page writes, manifest emission, optional in-process dispatch | Class A producer (derivative-page synthesis path) |
| `skills/wiki-extract-concepts/SKILL.md` + `.claude/commands/wiki-extract-concepts.md` (new) | Slash command + skill wrapper docs | Class A docs |
| `IndexRepository` + `SQLiteRepository` (**extended**, I-7.7a) | New `upsert_entity` write-path method (ABC + concrete) | Class B (cache) |
| `entities`, `entity_aliases`, `page_entity_refs`, `source_state` | All required schema present from Phase 3a — **no DDL changes** | Class B (cache) |

**TASK 003 v2 invariants** (carried from architecture review):
- No new DB tables; no schema changes (R-43 / §6).
- `wiki_enrich.py` argparse surface **unchanged** — no new `--manifest-*` flags (Decision-15 retracts v1 Decision-9).
- No cross-skill imports — `wiki_extract_concepts` imports from `_manifest_consumer`, not from `wiki_enrich` (Decision-16).
- `vault_id` predicate on every entity / ref / source_state query (ADR-002 §D1.1).
- All R-3 entity rows written with `is_candidate=1`; promotion (R-4) is deferred.
- `resolve_entity` read-path stays a `NotImplementedError` stub (Phase 3a contract preserved).

---

## 1. Task Execution Sequence

### Phase 0 — Blocking-first refactor (PRECONDITION — no parallel work)

**The only bead in this phase. It blocks every other bead in the task** so that all subsequent imports target a clean module from the outset (no "import-from-sibling then refactor later" two-step).

- [R-41] [I-7.0] Extract `validate_manifest` + `index_from_manifest` + `WikiIngestError` from `scripts/wiki_skills/wiki_enrich.py` into the new neutral module `scripts/wiki_skills/_manifest_consumer.py`; re-export from `wiki_enrich.py` for back-compat; rename `_validate_manifest` → `validate_manifest` (no underscore) and keep `_validate_manifest` as a one-release alias; add 4 new tests in `tests/test_manifest_consumer.py`; stale-doc sweep for any residual `--manifest-file/--manifest-stdin`/R-44/I-7.15/`dispatch_to_wiki_enrich` references. **Mechanical move ~131 LoC; ceiling ≤ 200 LoC net diff.**
  - Description File: [docs/tasks/task-003-00-manifest-consumer-refactor.md](./tasks/task-003-00-manifest-consumer-refactor.md)
  - Priority: Critical (blocks I-7.1..I-7.14)
  - Dependencies: none
  - Estimated time: 0.5 day

### Phase 1 — Scaffolding (entry-point + skill wrapper + DAL extension)

After I-7.0 lands, three beads run in **parallel**: argparse skeleton with stubs (I-7.1), the docs-only skill wrapper (I-7.2), and the DAL extension (I-7.7a). I-7.1's stubs cover every helper function (I-7.3..I-7.11) so E2E tests can be wired to mocks before any logic exists.

- [R-30, R-31, R-42] [I-7.1] `scripts/wiki_skills/wiki_extract_concepts.py` argparse entry-point + `main(argv)` + stub helpers (every internal function `raise NotImplementedError`) + Red→Green smoke test on argparse error path.
  - Description File: [docs/tasks/task-003-01-extract-concepts-entrypoint.md](./tasks/task-003-01-extract-concepts-entrypoint.md)
  - Priority: Critical (gates I-7.3..I-7.11 — they fill in the stubs)
  - Dependencies: task-003-00
  - Estimated time: 0.5 day

- [R-30] [I-7.2] `skills/wiki-extract-concepts/SKILL.md` + `.claude/commands/wiki-extract-concepts.md` + symlinks into `.agent/skills/`. Documentation-only — no Phase 1 stub.
  - Description File: [docs/tasks/task-003-02-skill-wrapper.md](./tasks/task-003-02-skill-wrapper.md)
  - Priority: Medium
  - Dependencies: task-003-00 (so the SKILL.md examples reference the correct neutral-module import)
  - Estimated time: 0.25 day

- [R-37] [I-7.7a] DAL extension: add `upsert_entity(...)` to `IndexRepository` ABC + `SQLiteRepository` (atomic INSERT … ON CONFLICT DO UPDATE; SQL-level `is_candidate` downgrade-guard via `MIN(excluded, existing)`); unit tests in `tests/test_sqlite_repository.py`.
  - Description File: [docs/tasks/task-003-07a-dal-upsert-entity.md](./tasks/task-003-07a-dal-upsert-entity.md)
  - Priority: Critical (blocks I-7.7b)
  - Dependencies: task-003-00 (no other; clean DAL extension)
  - Estimated time: 0.75 day

### Phase 2 — Extraction core (LLM + classify + concept-page write + entity upsert)

Logic for the synthesis path. Each bead lands as Phase 1 stub-replacement in `wiki_extract_concepts.py` (the stub was created by I-7.1) plus a unit test in `tests/test_wiki_extract_concepts.py`. I-7.3 → I-7.4 → I-7.5 is a strict chain (each consumes the prior's output). I-7.6 and I-7.7b run after I-7.5 lands the classifier. I-7.8 follows I-7.7b. I-7.9 is independent and may run in parallel with I-7.4/5/6.

- [R-32] [I-7.3] `load_known_entities(repo, vault_id) → list[dict]` — SELECT entities LEFT JOIN entity_aliases; serialize to CONTRACT §2 known-concepts format; empty-vault handled.
  - Description File: [docs/tasks/task-003-03-load-known-entities.md](./tasks/task-003-03-load-known-entities.md)
  - Priority: High
  - Dependencies: task-003-01 (replaces stub), task-003-07a (uses repo)
  - Estimated time: 0.25 day

- [R-33, R-34] [I-7.4] `extract_concepts_llm(source_body, known_entities, model, max_tokens) → list[dict]` — Anthropic API call (`claude-sonnet-4-6`, `temperature=0`); structured-output validation; `EXTRACTION_PARSE_ERROR` on malformed JSON.
  - Description File: [docs/tasks/task-003-04-llm-extraction.md](./tasks/task-003-04-llm-extraction.md)
  - Priority: Critical
  - Dependencies: task-003-01 (replaces stub), task-003-03 (known-concepts input)
  - Estimated time: 1 day

- [R-34] [I-7.5] `classify_candidates(llm_results, known_slugs) → tuple[list_create, list_mention]` — slug-set diff; logged in `extraction_summary`.
  - Description File: [docs/tasks/task-003-05-dedup-classifier.md](./tasks/task-003-05-dedup-classifier.md)
  - Priority: High
  - Dependencies: task-003-01, task-003-04
  - Estimated time: 0.25 day

- [R-36, R-40] [I-7.6] `write_concept_page(vault_root, candidate, source_slug, today) → Path` — atomic write of `_concepts/<slug>.md` (tempfile + `os.replace`); frontmatter per R-36(b); `# <name>` + definition + `## Mentions` body; skip-on-exists.
  - Description File: [docs/tasks/task-003-06-concept-page-writer.md](./tasks/task-003-06-concept-page-writer.md)
  - Priority: Critical
  - Dependencies: task-003-01, task-003-05
  - Estimated time: 0.5 day

- [R-37] [I-7.7b] `upsert_extracted_entity(repo, vault_id, candidate, source_slug, today) → str` — call site wrapping `repo.upsert_entity(...)` with `is_candidate=1`; defensive downgrade-guard at call layer; `canonicalized_by="llm:claude-sonnet-4-6@<date>"`.
  - Description File: [docs/tasks/task-003-07b-call-upsert-entity.md](./tasks/task-003-07b-call-upsert-entity.md)
  - Priority: Critical
  - Dependencies: task-003-01, task-003-06, task-003-07a
  - Estimated time: 0.25 day

- [R-38, R-40] [I-7.8] `upsert_entity_refs(repo, vault_id, source_slug, source_project, all_candidates) → None` — parse `"Lstart-Lend"` → integer pair (Decision-10); collect refs with `trust_level='medium'`, `ref_type='mentioned'`; call `repo.replace_refs(...)` atomically.
  - Description File: [docs/tasks/task-003-08-entity-refs-upsert.md](./tasks/task-003-08-entity-refs-upsert.md)
  - Priority: Critical
  - Dependencies: task-003-01, task-003-07b
  - Estimated time: 0.5 day

- [R-39] [I-7.9] `check_idempotency(repo, vault_id, source_slug, current_hash) → bool` — `source_state` query with `source_kind='extract-concepts'`; update-on-success.
  - Description File: [docs/tasks/task-003-09-idempotency-gate.md](./tasks/task-003-09-idempotency-gate.md)
  - Priority: High
  - Dependencies: task-003-01 (parallel-safe with I-7.4..I-7.8)
  - Estimated time: 0.25 day

### Phase 3 — Manifest + indexer dispatch

After the extraction core lands, build the manifest and wire the optional in-process dispatch. The neutral-module import (created by I-7.0) is pinned at the **module top** of `wiki_extract_concepts.py` so `unittest.mock.patch` sites are stable (I-7.12 patch-target lock).

- [R-35] [I-7.10] `build_manifest(vault_id, source_slug, source_hash, create_list, mention_list, log_event, vault_root) → dict` — v1.1-compatible structure; emit to stdout when `--ingest` absent.
  - Description File: [docs/tasks/task-003-10-manifest-builder.md](./tasks/task-003-10-manifest-builder.md)
  - Priority: Critical
  - Dependencies: task-003-01, task-003-08
  - Estimated time: 0.5 day

- [R-41] [I-7.11] `dispatch_to_indexer(manifest_dict, vault_id, vault_root, db_path) → dict` — in-process call into `_manifest_consumer.validate_manifest` then `index_from_manifest`; combined emit `{"extraction": ..., "index": ...}`; `WikiIngestError` → exit 6; `summary["failed"]` non-empty → exit 5.
  - Description File: [docs/tasks/task-003-11-indexer-dispatch.md](./tasks/task-003-11-indexer-dispatch.md)
  - Priority: Critical
  - Dependencies: task-003-00 (the import target), task-003-10
  - Estimated time: 0.5 day

### Phase 4 — Tests + regression sweep

Most unit coverage lands inside the Phase-1 stubs of each individual code-bearing bead (per Stub-First — tests exist before logic). These two beads are the **consolidation gates**: I-7.12 confirms the unit-test surface is comprehensive (patch points correct, in-memory fixture wired); I-7.13 adds the end-to-end integration fixture; I-7.14 is the regression gate.

- [R-43] [I-7.12] `tests/test_wiki_extract_concepts.py` consolidation — confirm patch targets, in-memory `SQLiteRepository` fixture, `validate_manifest` live-import test, in-process dispatch mock at `scripts.wiki_skills.wiki_extract_concepts.index_from_manifest` (NOT at `_manifest_consumer` — see I-7.12 patch-target note).
  - Description File: [docs/tasks/task-003-12-unit-tests.md](./tasks/task-003-12-unit-tests.md)
  - Priority: High
  - Dependencies: task-003-01..task-003-11 (consolidation of the per-bead unit tests)
  - Estimated time: 0.5 day

- [R-43] [I-7.13] `tests/test_wiki_extract_concepts_integration.py` + `tests/fixtures/source_extract/source-page.md` — extraction round-trip with mocked LLM; re-run produces `unchanged`; `--ingest` end-to-end variant against in-memory SQLite asserts indexed-entity count.
  - Description File: [docs/tasks/task-003-13-integration-test.md](./tasks/task-003-13-integration-test.md)
  - Priority: Critical
  - Dependencies: task-003-01..task-003-11
  - Estimated time: 0.5 day

- [R-43, R-41, **all RTM**] [I-7.14] `mypy --strict` clean across `scripts/wiki_skills/wiki_extract_concepts.py` + `_manifest_consumer.py`; full pytest sweep (332+ green); manual smoke recipe (TASK.md §7) steps 1-12.
  - Description File: [docs/tasks/task-003-14-mypy-regression.md](./tasks/task-003-14-mypy-regression.md)
  - Priority: Critical (acceptance gate)
  - Dependencies: **all prior** task-003-00..task-003-13
  - Estimated time: 0.5 day

---

## 2. Dependency DAG (critical-path view)

```text
                  ┌──────────────────────────────┐
                  │ task-003-00 manifest-consumer│  (I-7.0, R-41) — BLOCKING
                  │   refactor (PHASE 0)         │
                  └──────────────┬───────────────┘
                                 │
            ┌────────────────────┼────────────────────┐
            ▼                    ▼                    ▼
   ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐
   │ task-003-01     │  │ task-003-02     │  │ task-003-07a        │
   │ entrypoint+stubs│  │ skill-wrapper   │  │ DAL upsert_entity   │
   │ (I-7.1, R-30..) │  │ (I-7.2, R-30)   │  │ (I-7.7a, R-37)      │
   └────────┬────────┘  └─────────────────┘  └──────────┬──────────┘
            │                                            │
            │ (every helper stub below replaced in turn) │
            ▼                                            │
   ┌─────────────────┐                                   │
   │ task-003-03     │ (I-7.3, R-32)                    │
   │ load-known-ents │                                   │
   └────────┬────────┘                                   │
            ▼                                            │
   ┌─────────────────┐                                   │
   │ task-003-04     │ (I-7.4, R-33/R-34)               │
   │ llm-extraction  │                                   │
   └────────┬────────┘                                   │
            ▼                                            │
   ┌─────────────────┐                                   │
   │ task-003-05     │ (I-7.5, R-34)                    │
   │ dedup-classifier│                                   │
   └────────┬────────┘                                   │
            ▼                                            │
   ┌─────────────────┐    ┌─────────────────┐           │
   │ task-003-06     │    │ task-003-09     │           │
   │ concept-writer  │    │ idempotency-gate│ (parallel)│
   │ (I-7.6, R-36)   │    │ (I-7.9, R-39)   │           │
   └────────┬────────┘    └──────────┬──────┘           │
            ▼                        │                   │
   ┌─────────────────┐               │                   │
   │ task-003-07b    │◄──────────────┼───────────────────┘
   │ call-upsert     │ (I-7.7b, R-37)
   └────────┬────────┘
            ▼
   ┌─────────────────┐
   │ task-003-08     │ (I-7.8, R-38)
   │ entity-refs     │
   └────────┬────────┘
            ▼
   ┌─────────────────┐
   │ task-003-10     │ (I-7.10, R-35)
   │ build-manifest  │
   └────────┬────────┘
            ▼
   ┌─────────────────┐
   │ task-003-11     │ (I-7.11, R-41) — imports from 003-00
   │ indexer-dispatch│
   └────────┬────────┘
            ▼
   ┌─────────────────┐      ┌─────────────────┐
   │ task-003-12     │      │ task-003-13     │ (parallel)
   │ unit-tests      │      │ integration-test│
   │ (I-7.12)        │      │ (I-7.13)        │
   └────────┬────────┘      └────────┬────────┘
            └──────────┬─────────────┘
                       ▼
            ┌─────────────────────────┐
            │ task-003-14 mypy+sweep  │  (I-7.14) — ACCEPTANCE GATE
            └─────────────────────────┘
```

**Critical path** (longest blocking chain): 00 → 01 → 03 → 04 → 05 → 06 → 07b → 08 → 10 → 11 → 12/13 → 14.
**Parallel-safe pairs**:
- After 00: {01, 02, 07a}
- After 01: {09} (parallel with 03→04→05→06 chain)
- After 11: {12, 13}

---

## 3. Stub-First Application (per `skill-tdd-stub-first`)

| Bead | Code surface? | Phase-1 stub | Phase-1 test (Red→Green on stub) | Phase-2 logic |
|---|---|---|---|---|
| 003-00 | yes (move + back-compat) | `_manifest_consumer.py` with three `def`/`class` stubs raising `NotImplementedError` | `tests/test_manifest_consumer.py` — 4 tests assert `NotImplementedError` raised initially | move function bodies verbatim from `wiki_enrich.py`; add re-export + alias; tests now pass with real behavior |
| 003-01 | yes (argparse + helper stubs) | `main(argv)` with full argparse; every helper (`load_known_entities`, `extract_concepts_llm`, `classify_candidates`, `write_concept_page`, `upsert_extracted_entity`, `upsert_entity_refs`, `check_idempotency`, `build_manifest`, `dispatch_to_indexer`) `raise NotImplementedError` | E2E test: `main(["--vault","missing-arg"])` returns exit 1; help text contains `--ingest`; importing module does not raise | helpers replaced one-by-one by 003-03..003-11 |
| 003-02 | **no — docs** | n/a | n/a | direct write of SKILL.md + command file + symlinks |
| 003-03 | yes | replace `load_known_entities` stub with `NotImplementedError` (already there from 003-01); new test added | unit test `test_load_known_entities_empty_vault` asserts `NotImplementedError` → then real impl asserts `[]` returned | SELECT query + serialization |
| 003-04 | yes | LLM call gated by `if known_entities is None: raise NotImplementedError`; prompt-builder stub | unit test `test_build_prompt_includes_known_concepts` mocks Anthropic SDK; asserts prompt string contains every known slug | Anthropic API call + JSON schema validation |
| 003-05 | yes | `classify_candidates` returns `([], [])` placeholder | unit test with known slug set + 2 novel + 1 existing → asserts proper split | slug-set diff implementation |
| 003-06 | yes | `write_concept_page` returns `vault_root / "_concepts" / f"{slug}.md"` without writing | unit test asserts return path; Phase-2 test asserts file actually exists + frontmatter parses | atomic tempfile + `os.replace` + frontmatter + body assembly |
| 003-07a | yes (DAL) | abstract method on `IndexRepository`; SQLiteRepository impl raises `NotImplementedError` | `test_upsert_entity_not_implemented` (Red) → after impl, `test_upsert_entity_inserts_new_row` + `test_upsert_entity_no_downgrade` (Green) | atomic INSERT … ON CONFLICT DO UPDATE with SQL-level downgrade guard |
| 003-07b | yes | call site wraps stub (`upsert_entity` from 003-07a) | unit test patches `repo.upsert_entity` and asserts called once with `is_candidate=1` | defensive check + real call |
| 003-08 | yes | `upsert_entity_refs` returns None without calling repo | unit test asserts `replace_refs` called once with parsed `(line_start, line_end)` integer pairs | parse `"Lstart-Lend"` + collect refs + call repo |
| 003-09 | yes | `check_idempotency` returns `False` placeholder | unit test asserts `False` on no prior state; mocks `source_state` row to assert `True` on match | source_state SELECT + UPDATE |
| 003-10 | yes | `build_manifest` returns minimal `{"status":"ok","vault_id":...}` | unit test asserts the round-trip through `validate_manifest` accepts the stub output | full manifest assembly |
| 003-11 | yes | `dispatch_to_indexer` calls real `validate_manifest` + `index_from_manifest` from day 1 (the symbols exist after 003-00) | unit test patches `scripts.wiki_skills.wiki_extract_concepts.index_from_manifest`; asserts called once when `--ingest`, zero times without | wire combined emit `{"extraction":...,"index":...}` + error mapping (exit 5/6) |
| 003-12 | yes (tests only) | n/a (consolidates per-bead unit tests) | n/a | confirm patch points + fixture + 100% helper coverage |
| 003-13 | yes (tests + fixture) | placeholder fixture file with 3 mentionable concepts; tests `pytest.skip("phase-2")` | collection succeeds | unskip; mock LLM; assert manifest content + `unchanged` on re-run + `--ingest` indexed-count |
| 003-14 | **no — verify** | n/a | n/a | run `mypy --strict`, `pytest tests/`, smoke recipe |

**Note on the I-7.0 back-compat alias (Decision-16 carryover)**: per TASK.md §4 I-7.0 acceptance bullet (c), the existing `tests/test_wiki_enrich.py` imports of `_validate_manifest` (lines 21, 98, 104, 112; dynamic import at line 467) STAY POINTED AT `wiki_enrich._validate_manifest` for one release cycle so the alias is exercised by the test suite — not dead code. The NEW `tests/test_manifest_consumer.py` (003-00) imports from `_manifest_consumer` directly. Follow-up bead post-release will deprecate the alias.

---

## 4. Use Case Coverage

| Use Case | Description | Beads |
|---|---|---|
| **UC-08** (main, without `--ingest`) | Operator extracts concepts; manifest emitted to stdout for inspection | 003-01, 003-03, 003-04, 003-05, 003-06, 003-07a, 003-07b, 003-08, 003-09, 003-10 |
| **UC-08** (main, with `--ingest`) | Operator extracts concepts; in-process indexer call mirrors manifest into DB | 003-00 (precondition), 003-11, plus all of UC-08 main-without-ingest |
| **UC-08 A1** (already-confirmed concept) | Slug match → `mention` action only; no downgrade | 003-05 (classifier), 003-07a (SQL downgrade guard), 003-07b (defensive guard), 003-08 (ref still inserted) |
| **UC-08 A2** (LLM malformed JSON) | `EXTRACTION_PARSE_ERROR` exit 4 | 003-04 |
| **UC-08 A3** (Anthropic API down) | `LLM_API_UNAVAILABLE` exit 3 | 003-04 |
| **UC-08 A4** (no `_concepts/` dir) | `mkdir -p` before first write | 003-06 |
| **UC-08 A5** (`--ingest` with `WikiIngestError`) | Exit 6 + `MANIFEST_INVALID` envelope | 003-11 |
| **UC-09** (re-extract on unchanged body) | Idempotency short-circuit | 003-09 |
| **UC-09** (re-extract on changed body) | `replace_refs` atomic delete + insert | 003-08, 003-09 |

---

## 5. RTM Coverage Matrix

| RTM ID | Requirement | Bead(s) | Phase |
|---|---|---|---|
| R-30 | New skill `wiki-extract-concepts` with slash-command entry point | task-003-01, task-003-02 | 1 |
| R-31 | `--vault`, `--source-page`, `--vault-root`, `--db-path`, `--ingest`, `--model` argparse surface | task-003-01 | 1 |
| R-32 | Pre-extraction known-entities query | task-003-03 | 2 |
| R-33 | LLM extraction call (Claude Sonnet 4.6, `temperature=0`, structured output) | task-003-04 | 2 |
| R-34 | De-duplication at extraction time (known-concepts in prompt + classifier) | task-003-04, task-003-05 | 2 |
| R-35 | Manifest output (v1.1-compatible) | task-003-10 | 3 |
| R-36 | Concept-page generation (`_concepts/<slug>.md` atomic write + frontmatter) | task-003-06 | 2 |
| R-37 | Entity row upsert with `is_candidate=1` + downgrade guard | task-003-07a, task-003-07b | 1, 2 |
| R-38 | `page_entity_refs` rows with `trust_level='medium'` + provenance + `(line_start, line_end)` | task-003-08 | 2 |
| R-39 | Idempotency via `source_state` | task-003-09 | 2 |
| R-40 | Multi-vault `vault_id` enforcement | task-003-06, task-003-08 | 2 |
| R-41 | In-process indexer dispatch via neutral module (Decision-15 + Decision-16) | task-003-00, task-003-11 | 0, 3 |
| R-42 | Error handling and exit codes (0/1/2/3/4/5/6) | task-003-01 (argparse), task-003-04 (3/4), task-003-11 (5/6) | 1, 2, 3 |
| R-43 | Unit + integration tests + mypy + regression sweep | task-003-00 (4 new tests), task-003-12, task-003-13, task-003-14 | 0, 4 |
| ~~R-44~~ | ~~`wiki-enrich --manifest-*` flags~~ | **DROPPED** (Decision-15) | — |

**1-1 issue mapping** (no orphans): R-30→I-7.1+I-7.2, R-31→I-7.1, R-32→I-7.3, R-33→I-7.4, R-34→I-7.4+I-7.5, R-35→I-7.10, R-36→I-7.6, R-37→I-7.7a+I-7.7b, R-38→I-7.8, R-39→I-7.9, R-40→I-7.6+I-7.8, R-41→I-7.0+I-7.11, R-42→I-7.1+I-7.4+I-7.11, R-43→I-7.0+I-7.12+I-7.13+I-7.14.

---

## 6. Risk Register

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| **R-1** | **I-7.0 move surface > 200 LoC ceiling** — the mechanical extract pulls more shared helpers than estimated, blowing the per-bead size guard | Low-Medium | Medium | Reviewer caveat 3 already relaxed the ceiling from initial estimate to 200 LoC. If the actual diff exceeds 200, split into 003-00a (extract `validate_manifest` only) and 003-00b (extract `index_from_manifest` + `WikiIngestError`). Both still ship before I-7.1. |
| **R-2** | **Patch-target drift in I-7.12** — operator forgets the patch must target `scripts.wiki_skills.wiki_extract_concepts.index_from_manifest` (the bound module-top name) and not `_manifest_consumer` (where the source lives) — leads to tests passing locally but failing under refactor | Medium | Medium | Patch-target lock documented in I-7.11 acceptance + I-7.12 test plan + this PLAN.md §3 row 003-11. Lint check: `grep -rn "patch.*_manifest_consumer.index_from_manifest" tests/` MUST be empty. |
| **R-3** | **Test-import drift on back-compat alias** — someone migrates `tests/test_wiki_enrich.py` imports off `_validate_manifest` during this task, leaving the alias as dead code earlier than scheduled | Low | Low | I-7.0 acceptance bullet (c) + PLAN.md §3 note explicitly say "STAY POINTED AT wiki_enrich._validate_manifest for one release cycle". Plan-reviewer gate enforces. |
| **R-4** | **LLM extraction non-determinism** — `temperature=0` does not fully guarantee reproducible output across Anthropic model versions; integration test (003-13) flakes | Medium | Medium | Mock the Anthropic SDK in I-7.13 (not a live call). Use a fixed JSON response fixture for the LLM call so the test exercises the parser + classifier deterministically. Live LLM smoke is operator-driven (TASK.md §7 step 3b/4), not in CI. |
| **R-5** | **`upsert_entity` SQL downgrade guard regression** — a future schema migration breaks the `MIN(excluded.is_candidate, entities.is_candidate)` clause silently | Medium | High (would corrupt confirmed entities) | I-7.7a unit test `test_upsert_entity_no_downgrade` covers the SQL guard. Plus I-7.7b defensive call-layer check is double-belt. Schema migrations must run the test suite before merge. |
| **R-6** | **Source-state row collision across source kinds** — `source_state` rows for `source_kind='extract-concepts'` collide with the transcript adapter's rows on the same `(vault_id, scope)` | Low | Medium | TASK.md §6 explicitly notes `source_state.source_kind` is `TEXT NOT NULL` with no CHECK constraint and the new value is allowed without DDL change. I-7.9 acceptance bullet asserts the primary key includes `source_kind`. |

---

## 7. Definition of Done (acceptance gate — task-003-14)

The task is "Done" iff **all** of the following hold:

- [ ] All 16 beads (task-003-00..task-003-14) marked complete with green acceptance bullets.
- [ ] `pytest tests/ -q` → **332+ passed, 0 failed** (baseline 328 from TASK 004 + 4 new tests from I-7.0 + N new tests from I-7.7a/I-7.12/I-7.13).
- [ ] `mypy --strict scripts/` (full tree) → **Success: no issues found**.
- [ ] Smoke 1 (baseline candidate count = 0) → expected.
- [ ] Smoke 2 (pick a source page) → returns one slug.
- [ ] Smoke 3a (inspection mode without `--ingest`) → exit 0, manifest JSON on stdout.
- [ ] Smoke 3b (manifest passes `_manifest_consumer.validate_manifest`) → no exception.
- [ ] Smoke 4 (`--ingest` end-to-end) → exit 0, combined `{"extraction":...,"index":...}` JSON.
- [ ] Smoke 5 (`is_candidate=1` count) → >= N (new concepts in manifest).
- [ ] Smoke 6 (`page_entity_refs` with `trust_level='medium'` + non-null `source_quote` + `(line_start, line_end)`) → >= N.
- [ ] Smoke 7 (idempotency re-run) → `action='unchanged'`, no LLM call.
- [ ] Smoke 8 (concept pages on disk) → N new files in `_concepts/`.
- [ ] Smoke 9 (`wiki-enrich` CLI surface unchanged — no `--manifest-*` flags appear in `--help`) → "OK: wiki-enrich surface preserved" (Decision-15 invariant).
- [ ] Smoke 10 (`_manifest_consumer` canonical + `wiki_enrich` re-exports correctly — back-compat alias `_validate_manifest` survives) → "OK" (Decision-16 invariant).
- [ ] Smoke 11 (full test suite) → 332+ green.
- [ ] Smoke 12 (mypy strict on the two new modules) → no issues.

**Reference**: smoke recipe full steps in [docs/TASK.md §7](./TASK.md).

---

## 8. Effort Summary

| Metric | Value |
|---|---|
| Beads count | 16 |
| Total working-time estimate (single-developer, sequential) | ~7.0 days |
| Critical-path estimate (with parallelization where DAG permits) | ~5.5 days |
| Acceptance-gate effort (task-003-14 alone) | 0.5 day |

---

## 9. Open Issues / Planner Judgement Calls

1. **Phase 0 size discipline** — I-7.0 is sized at ~131 LoC mechanical extract per architecture-reviewer measurement (TASK.md §4 I-7.0). The 200-LoC net-diff ceiling acts as a "did something unexpected happen?" guard, not as a hard limit on the legitimate move. If the ceiling is breached during implementation, split per Risk R-1 — both halves still ship before I-7.1.
2. **I-7.6 atomic-write primitive choice** — TASK.md §0.1 row "Optional reuse of vendored primitives" + I-7.6 note both call this a planner-level micro-decision. PLAN.md defaults to **repo-local primitive** (`tempfile + os.replace`) to minimise vendored-snapshot coupling per Decision-12. Operator may override during 003-06 implementation if scope-creep emerges; choice does not affect any other bead.
3. **I-7.9 ordering (parallel-safe with 003-04/05/06)** — placed in the DAG as a side-branch from 003-01 because it only touches `source_state` queries, not the extraction core. Operator may execute it any time after 003-01 lands (recommended: early, to surface schema integration issues quickly).
4. **I-7.13 LLM-mocking strategy** — `pytest-mock` is the project's existing test framework. The fixture LLM-response file lives in `tests/fixtures/source_extract/llm-response.json` so re-runs are byte-identical. Live LLM call is **operator-driven** via TASK.md §7 step 3b — NOT part of CI.
5. **Phase 2 chain length (003-03 → 04 → 05 → 06 → 07b → 08)** — strict ordering enforced by Stub-First (each replaces the prior's output stub) but each bead is small (≤0.5 day) so the chain still fits in ~3 working days even sequential.

---

## 10. Start Signal

Plan-reviewer gate next. After sign-off, start with **task-003-00** (manifest-consumer-refactor). No parallel work permitted until 003-00 lands. After 003-00 ships, Phase 1 beads {003-01, 003-02, 003-07a} may begin in parallel.
