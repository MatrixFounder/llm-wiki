# TASK: wiki-extract-concepts — Epic 7 Entity Resolver Entry-Point

### 0. Meta Information

- **Task ID:** 003
- **Slug:** `wiki-extract-concepts`
- **Mode:** Standard
- **Status:** `PAUSED` (2026-05-27) — awaiting TASK 004 `wiki-ingest-vendoring` ship. Operator decided to vendor wiki-ingest Python module into this repo (Option 5: Python-import-only vendor) before R-3 implementation, so TASK 003 can be planned on an in-process API foundation (Decision-9 `--manifest-stdin` becomes a direct function call; I-7.11 `dispatch_to_wiki_enrich` becomes a direct import — both simpler than the subprocess-flavor currently specified). Resume after TASK 004 ship with a mini-revision pass on Decision-9 / I-7.11.
- **Epic:** Epic 7 — Entity Resolver (R-3 only; R-4/R-5 deferred)
- **Predecessor:** [docs/tasks/task-002-wiki-mvp.md](./tasks/task-002-wiki-mvp.md) (Phase 3a complete, 2026-05-27)
- **Related artifacts:**
  - [docs/ROADMAP.md](./ROADMAP.md) — §P1 Epic 7 entry-point
  - [docs/ARCHITECTURE.md](./ARCHITECTURE.md) — §2 Functional Components, §3 Data Model
  - [docs/SCHEMA-v2.sql](./SCHEMA-v2.sql) — entities / entity_aliases / page_entity_refs DDL
  - [docs/WIKI-INGEST-V1.1-CONTRACT.md](./WIKI-INGEST-V1.1-CONTRACT.md) — manifest schema, §2 known-concepts injection, §6 idempotency
  - [docs/adr/ADR-001-wiki-ingest-integration.md](./adr/ADR-001-wiki-ingest-integration.md) — Option I (Wrap + Index)
  - [docs/adr/ADR-002-multi-vault-bottleneck-corrections.md](./adr/ADR-002-multi-vault-bottleneck-corrections.md) — vault_id partitioning, Class A/B/C layering
  - [skills/wiki-enrich/SKILL.md](../skills/wiki-enrich/SKILL.md) — bridge skill (manifest consumer)
  - [scripts/wiki_skills/wiki_enrich.py](../scripts/wiki_skills/wiki_enrich.py) — bridge implementation
- **Decisions carried forward from Task 001/002:**
  - **Decision-1 (2026-05-25)**: Option I (Wrap + Index) — `wiki-ingest` owns file synthesis; this repo owns SQLite index. See ADR-001.
  - **Decision-2 (2026-05-26)**: Single global DB with `vault_id` partitioning. See ADR-002.
  - **Decision-3 (2026-05-26)**: `vault_id` REQUIRED explicit in `WIKI_SCHEMA.md`. No hash fallback. See ADR-002 §D1.1.
  - **Decision-4 (2026-05-26)**: Data Layering Contract — Class A (vault canonical) / B (rebuildable cache) / C (DB-only operational). See ADR-002 §D8.
  - **Decision-5 (2026-05-27)**: UC-06/UC-07 superseded by `/wiki-enrich` bridge. R-06.3 and R-24 marked SUPERSEDED in Task 001 RTM.
- **New decisions for this task:**
  - **Decision-6 (2026-05-27)**: `wiki-extract-concepts` lives in **this repo** (`obsidian-llm-wiki`), not a separate package. Rationale: the `entities`, `entity_aliases`, and `page_entity_refs` schema is already fully implemented (Phase 3a); a separate repo would either duplicate the SQLite DAL or impose a wiki-ingest-style contract for no benefit. Closes the ROADMAP open question "Does Epic 7 happen here or in a separate repo?"
  - **Decision-7 (2026-05-27)**: Ship R-3 only first. R-4 (candidate/confirmed promotion CLI `wiki-confirm`) and R-5 (alias CLI `wiki-alias` + search expansion + alias-collision lint) are deferred until R-3 real-world quality is observed. Rationale: designing dedup/alias heuristics blind to LLM extraction quality produces over-engineering; LLM extraction patterns on real vaults must be seen first.
  - **Decision-8 (2026-05-27)**: File-write ownership for new `_concepts/<slug>.md` pages — **Option A** (operator-confirmed): `wiki-extract-concepts` writes the concept files itself (frontmatter + body, atomic write-and-rename), emits a manifest, and `/wiki-enrich` performs index-only upsert. Rationale: concept-page generation is trivial (frontmatter template + LLM-derived body), does not require wiki-ingest's raw-source synthesis pipeline, and avoids scope creep into the Universal-skills repo. ADR-001 ("wiki-ingest owns file layer") is **clarified**, not violated: it governs **raw-source** file synthesis. Downstream skills (e.g., `wiki-extract-concepts`) may write derivative pages **provided** they emit a wiki-ingest-compatible manifest for `/wiki-enrich` consumption.
  - **Decision-9 (2026-05-27)**: `--manifest-file` / `--manifest-stdin` flag on `wiki-enrich` — **in scope for Task 003** (operator-confirmed). Required so `wiki-extract-concepts --ingest` auto-dispatch works without re-running `wiki-ingest` on the already-indexed source page. Implementation: small extension to `wiki-enrich` (~30 LoC) — two mutually exclusive input flags (`--source` XOR `--manifest-{file,stdin}`); when manifest is provided, skip the `wiki-ingest` subprocess and go straight to manifest validation + indexing. New RTM row R-44 and Issue I-7.15 track this scope.
  - **Decision-10 (2026-05-27)**: LLM prompt format for `source_span` — **human-readable `"L12-L18"`** (operator-confirmed). Parsed on consumption to `line_start=12, line_end=18` for storage in `page_entity_refs.line_start` / `line_end` integer columns. Rationale: more robust to LLM output variance than nested JSON; one-line regex parse covers it.

---

### 1. General Description

#### 1.1 Goal

Implement the first working piece of Epic 7 (entity resolver): an LLM-driven extraction pass that reads a summary page already in a vault, identifies candidate concept entities mentioned in it, de-duplicates against known entities already in the DB, and emits a wiki-ingest-compatible manifest listing proposed new `_concepts/<slug>.md` pages and entity rows. The manifest is then consumed by `/wiki-enrich`, which ingests the concept pages into the vault filesystem and SQLite index — no new code path is required in the consumer.

The Karpathy promise: each source ingest touches 1 source page + a handful of concept pages. Closing the gap to "10-15 pages per ingest" (Karpathy's compounding target) requires the entity layer to be activated. This task activates it, with candidate rows remaining in `is_candidate=1` quarantine until R-4 promotion logic is implemented.

#### 1.2 Scope

- **In scope (R-3 only):**
  - New skill `wiki-extract-concepts` (slash command `/wiki-extract-concepts`).
  - New Python entry point `scripts/wiki_skills/wiki_extract_concepts.py`.
  - LLM extraction pass (Claude Sonnet 4.6): reads a single source page body, returns candidate concept slugs + definitions + provenance spans.
  - Pre-extraction de-duplication: query `entities` table for the vault before LLM call; pass canonical names to LLM as known-concepts, using the `--known-concepts-stdin` integration seam from wiki-ingest CONTRACT §2.
  - Manifest emission: output a wiki-ingest v1.1-compatible JSON manifest for `/wiki-enrich` to consume.
  - Idempotency: re-extraction on same source page (same `file_hash`) returns `status=unchanged`.
  - All new entity rows written with `is_candidate=1`.
  - All new `page_entity_refs` rows carry `trust_level='medium'`, `source_quote`, and `source_span` populated from LLM output.
  - Multi-vault: `vault_id` required on every call; no cross-vault entity bleed.

- **Out of scope (deferred):**
  - R-4: `wiki-confirm <slug>` CLI for candidate→confirmed promotion.
  - R-4: automatic promotion on N mentions threshold.
  - R-5: `wiki-alias` CLI to register aliases.
  - R-5: `wiki-search` alias expansion.
  - R-5: `wiki-lint` alias-collision detection.
  - Vector search / semantic de-duplication (Epic 8).
  - Batch extraction across multiple source pages (can be scripted externally using the new skill).

#### 1.3 Non-goals

- This task does not introduce new DB tables. All required schema (`entities`, `entity_aliases`, `page_entity_refs`) is already present from Phase 3a.
- This task does not change the `resolve_entity` stub in `IndexRepository` — that method will remain `NotImplementedError` until R-4 is implemented.
- This task does not change `/wiki-enrich` internals — the existing manifest-consumer code handles the output of this task without modification.

---

### 2. Requirements Traceability Matrix (RTM)

> Numbering continues after R-29 (last requirement in Phase 3a).

| ID | Requirement | Status | Acceptance Bullets |
|---|---|---|---|
| **R-30** | New skill `wiki-extract-concepts` with slash command entry point | planned | (a) `skills/wiki-extract-concepts/SKILL.md` exists and follows existing skill template; (b) `.claude/commands/wiki-extract-concepts.md` symlinked; (c) `scripts/wiki_skills/wiki_extract_concepts.py` entry point with `main(argv)` signature consistent with other wiki skills |
| **R-31** | `--vault` and `--source-page` required arguments; `--vault-root` required for vault filesystem operations | planned | (a) Missing `--vault` → argparse error + non-zero exit; (b) Missing `--source-page` → argparse error + non-zero exit; (c) `--source-page` validated inside vault root via `validate_inside_vault` (R-26 guard); (d) `--db-path` optional override mirrors `wiki-enrich` pattern |
| **R-32** | Pre-extraction query: read known entities from DB before LLM call | planned | (a) `SELECT slug, name FROM entities WHERE vault_id = ?` (plus aliases JOIN) executes before any LLM API call; (b) Result serialised to JSON matching CONTRACT §2 known-concepts format `[{"slug": ..., "name": ..., "aliases": [...]}]`; (c) Empty vault (0 entities) handled gracefully — LLM call proceeds with empty list |
| **R-33** | LLM extraction call: Claude Sonnet 4.6, deterministic temperature, structured output | planned | (a) Model = `claude-sonnet-4-6` (default; overridable via `--model`); (b) `temperature=0` on API call (reproducibility); (c) `max_tokens` ≤ 4096 for extraction response; (d) Prompt instructs LLM to return JSON array of candidate concepts with fields: `slug`, `name`, `definition` (1-3 sentences), `source_quote` (10-50 words from source body), `source_span` (`Lstart-Lend`), `entity_type` (from `entities.type` CHECK enum); (e) LLM response validated against expected schema before use — malformed JSON → `EXTRACTION_PARSE_ERROR` with raw response in error details |
| **R-34** | De-duplication at extraction time: LLM receives known-concept list; returns exact existing slug where match | planned | (a) Known-concepts JSON passed in LLM prompt as "use exact slug/name where concept is already known"; (b) LLM response items whose `slug` matches an existing entity in the vault are classified as `action=mention` (ref only, no new concept page); (c) Items with novel slug are classified as `action=create`; (d) Classification logged in manifest `extraction_summary` field for operator visibility |
| **R-35** | Manifest output: wiki-ingest v1.1-compatible JSON | planned | (a) Manifest `status` field is `"ok"` on success; (b) `vault_id` matches caller's `--vault`; (c) `written[]` array contains one entry per `action=create` concept, `kind="concept"`, `path="_concepts/<slug>.md"`, `action="created"`; (d) `source` object carries source page `slug` and `hash`; (e) `log_event` object present with `event_type="ingest"`, `subject=<source-page-title>`; (f) Manifest is emitted to stdout as JSON (same as wiki-ingest `--output-format json`); (g) No manifest emitted on failure — error envelope only |
| **R-36** | Concept page generation: write `_concepts/<slug>.md` files into vault | planned | (a) Each new concept page written to `<vault_root>/_concepts/<slug>.md` before manifest emission; (b) Frontmatter includes: `type: concept`, `vault_id: <vault-id>` (ADR-002 §D1.1 invariant), `slug`, `name`, `date: <today>`, `tags: [concept, candidate]`, `is_candidate: true`, `source_page: <source-slug>`, `trust_level: medium`; (c) Body includes: `# <name>`, definition paragraph from LLM, `## Mentions`, provenance block referencing source page with `source_quote`; (d) File written atomically (write to tempfile, rename); (e) Existing file at target path → skip write, include in manifest with `action="unchanged"` |
| **R-37** | Entity row upsert: `is_candidate=1` for all R-3 extracted entities | planned | (a) After concept page written, `repo.upsert_entity(...)` called with `is_candidate=1`; (b) Existing confirmed entity (`is_candidate=0`) for same `(vault_id, slug)` → no downgrade; `action` in manifest = `"mentioned"`, no page write; (c) `canonicalized_by` field set to `"llm:claude-sonnet-4-6@<date>"`; (d) `first_seen` and `last_updated` set to extraction timestamp |
| **R-38** | `page_entity_refs` rows: `trust_level='medium'`, provenance populated | planned | (a) For each extracted entity (both `create` and `mention`), insert a `page_entity_refs` row linking source page to entity; (b) `trust_level='medium'`; (c) `source_quote` populated from LLM output (10-50 words); (d) `source_span` populated as `Lstart-Lend` from LLM output; (e) `ref_type='mentioned'`; (f) Uses `repo.replace_refs(...)` semantics for the source page's entity refs (atomic delete + insert for re-extraction idempotency) |
| **R-39** | Idempotency: same source page (same file_hash) → `status=unchanged`, no LLM call | planned | (a) Before LLM call, compute `sha256(source_page_body)` and compare against `source_state` table entry `(vault_id, source_kind='extract-concepts', scope=<source_slug>, key='source_hash')`; (b) Match → return `{"status": "ok", "action": "unchanged", "manifest": null}`, exit 0, no LLM API call; (c) Mismatch or no prior record → proceed with extraction, update `source_state` row after success |
| **R-40** | Multi-vault partitioning: `vault_id` enforced throughout | planned | (a) All DB queries include `vault_id = ?` predicate; (b) Concept pages written under `vault_root` provided by `--vault-root`; (c) No cross-vault entity lookup; (d) `validate_inside_vault` applied to every file path written |
| **R-41** | Integration with `/wiki-enrich`: manifest emitted by this skill is consumed by `/wiki-enrich` without code changes | planned | (a) Running `/wiki-extract-concepts --vault V --vault-root P --source-page S` followed by piping its stdout manifest into `/wiki-enrich --manifest-stdin` (or saving to file and passing via `--manifest-file`) triggers full index upsert; (b) Alternatively: `wiki-extract-concepts` calls `wiki-enrich` as a subprocess after manifest generation (preferred — see §3 Integration Decision); (c) After full pipeline: `SELECT count(*) FROM entities WHERE vault_id=V AND is_candidate=1` increases by count of new concepts |
| **R-42** | Error handling and exit codes | planned | (a) Exit 0 = full success or `unchanged`; (b) Exit 1 = argument/usage error; (c) Exit 2 = source page not found in vault or not indexed; (d) Exit 3 = LLM API unavailable or auth failed; (e) Exit 4 = `EXTRACTION_PARSE_ERROR` (LLM returned malformed JSON); (f) Exit 5 = partial write (some concept pages written, index upsert failed for some); (g) All failures emit JSON error envelope to stdout: `{"error": "<CODE>", "message": "...", "details": {...}}`; (h) Exit-5 envelope MUST include `"written_so_far": [<paths>]` and `"index_failed": [<paths>]` arrays so operator can manually roll back the on-disk files that did not reach the index (mirror wiki-ingest CONTRACT §3 partial-success contract) |
| **R-43** | Tests: unit + integration coverage | planned | (a) Unit: LLM prompt construction tested with mock known-concepts list; (b) Unit: manifest schema validation (round-trip serialize/deserialize); (c) Unit: idempotency short-circuit (mock `source_state` hit); (d) Integration: extraction on a real-form fixture source page (`tests/fixtures/source_extract/`) → manifest contains ≥ 1 concept with correct fields; (e) Integration: re-run on same fixture → `status=unchanged`, 0 LLM calls; (f) `mypy --strict` clean for `scripts/wiki_skills/wiki_extract_concepts.py` |
| **R-44** | `wiki-enrich` accepts a pre-built manifest via `--manifest-file PATH` or `--manifest-stdin`, skipping the `wiki-ingest` subprocess (Decision-9) | planned | (a) New flags `--manifest-file PATH` and `--manifest-stdin` added to `wiki-enrich` argparse; (b) Mutually exclusive with `--source`; argparse error if both passed; (c) When manifest input is used, `wiki-enrich` skips the `check_wiki_ingest_version` / `wiki-ingest` subprocess call; loads JSON directly; (d) `_validate_manifest` still applied (path traversal, vault_id match, status="ok"); (e) `index_from_manifest` and `log_event` mirror behave identically to the wiki-ingest-fed path; (f) Existing `--source` path remains the default and unchanged; (g) Regression: all current `tests/test_wiki_enrich.py` cases still pass; new test covers both manifest-input branches |

---

### 3. Integration Choice: New Skill + `/wiki-enrich` Dispatch

**Decision**: Implement `wiki-extract-concepts` as a **standalone new skill** that emits a manifest, then optionally invokes `/wiki-enrich` as a subprocess to consume it.

**Rationale for standalone (not extending `/wiki-enrich`):**
1. `/wiki-enrich` is an ADR-001 Option I bridge: its contract is "given a raw source, call `wiki-ingest` for synthesis, then index the manifest." `wiki-extract-concepts` does not call `wiki-ingest` — it IS the synthesis step (for concept extraction). The responsibilities do not compose cleanly under the existing `wiki-enrich` flag surface.
2. A `--extract-concepts` flag on `/wiki-enrich` would conflate two distinct phases: (a) source summarisation (wiki-ingest's job) and (b) concept extraction from an already-ingested summary page. Mixing them violates the single-responsibility principle and makes the skill's mental model harder.
3. A new skill is trivially composable in a workflow: `wiki-enrich` first (ingest), then `wiki-extract-concepts` (enrich entity layer). Each skill can be tested and run independently.
4. The existing `/wiki-enrich` manifest-consumer code (lines ~100-200 of `wiki_enrich.py`) handles concept pages (`kind="concept"`) correctly already — no change needed.

**Invocation flow (operator perspective):**
```
# Step 1: ingest source page (existing flow, no change)
/wiki-enrich --vault trade-agents --vault-root /path --source /raw/lesson.md

# Step 2: extract concepts from the indexed source page (new skill)
/wiki-extract-concepts --vault trade-agents --vault-root /path \
    --source-page self-improving-trading-agent-on-hermes
# → emits manifest to stdout
# → if --ingest flag passed, auto-calls /wiki-enrich to consume manifest
```

**Subprocess auto-dispatch option** (`--ingest` flag on the new skill): when passed, `wiki-extract-concepts` calls `wiki-enrich` as a subprocess with the manifest piped in, so the operator can do the full two-step in one command. This is ergonomic and does not change either skill's contract.

---

### 4. Epics & Issues

#### Epic E7: wiki-extract-concepts (R-3)

- **I-7.1** Python entry point `scripts/wiki_skills/wiki_extract_concepts.py`. Implement argparse surface: `--vault`, `--vault-root`, `--source-page` (slug or relative path), `--db-path` override, `--model` (default `claude-sonnet-4-6`), `--ingest` (auto-dispatch flag). Implement `main(argv)` consistent with other wiki skills. Stub all internal functions initially (Stub-First). → R-30, R-31, R-42

- **I-7.2** Skill wrapper `skills/wiki-extract-concepts/SKILL.md` and slash command `.claude/commands/wiki-extract-concepts.md`. Follow existing skill template (see `skills/wiki-enrich/SKILL.md`). Create symlinks into `.agent/skills/`. → R-30

- **I-7.3** Pre-extraction DB query: implement `load_known_entities(repo, vault_id) → list[dict]`. Query `entities` LEFT JOIN `entity_aliases` for the vault; serialize to CONTRACT §2 format. Handle empty result gracefully. → R-32

- **I-7.4** LLM extraction: implement `extract_concepts_llm(source_body, known_entities, model, max_tokens) → list[dict]`. Build prompt with source body + known-concepts JSON block. Call Anthropic API with `temperature=0`. Validate response JSON schema. Return structured list with `slug`, `name`, `definition`, `source_quote`, `source_span`, `entity_type`, `action` fields. → R-33, R-34

- **I-7.5** De-duplication classifier: implement `classify_candidates(llm_results, known_slugs) → tuple[list_create, list_mention]`. Items whose slug exists in vault entities → `mention` (ref only). Novel slugs → `create`. Log classification in extraction summary. → R-34

- **I-7.6** Concept page writer: implement `write_concept_page(vault_root, candidate, source_slug, today) → Path`. Write `_concepts/<slug>.md` atomically. Frontmatter per R-36 spec. Body: `# <name>`, definition, `## Mentions` provenance block. Skip-and-return-unchanged if file exists. → R-36

- **I-7.7a** DAL extension: add `upsert_entity(vault_id, slug, name, type, is_candidate, canonicalized_by, first_seen, last_updated) → None` to `IndexRepository` ABC (`scripts/wiki_index/repository.py`) and implement in `SQLiteRepository` (atomic INSERT … ON CONFLICT DO UPDATE; `is_candidate` downgrade-guard at SQL level: `is_candidate = MIN(excluded.is_candidate, pages.is_candidate)`). Add unit tests in `tests/test_sqlite_repository.py`. Phase 3a left this method out (only `resolve_entity` read-path exists per `repository.py:260`); confirmed absent by grep before scoping. → R-37

- **I-7.7b** Call site in skill: implement `upsert_extracted_entity(repo, vault_id, candidate, source_slug, today) → str`. Call `repo.upsert_entity(...)` with `is_candidate=1`. Guard against downgrading confirmed entities (`is_candidate=0`) at the call layer too (defensive — SQL guard from I-7.7a is primary). → R-37

- **I-7.8** `page_entity_refs` upsert: implement `upsert_entity_refs(repo, vault_id, source_slug, source_project, all_candidates)`. Collect `(entity_slug, ref_type='mentioned', source_quote, source_span, trust_level='medium')` for all extracted candidates (create + mention). Call `repo.replace_refs(...)` atomically. → R-38

- **I-7.9** Idempotency gate: implement `check_idempotency(repo, vault_id, source_slug, current_hash) → bool`. Query `source_state` with `source_kind='extract-concepts'`. Return True if unchanged. After successful extraction, update `source_state` row. → R-39

- **I-7.10** Manifest builder: implement `build_manifest(vault_id, source_slug, source_hash, create_list, mention_list, log_event) → dict`. Output structure per R-35. Emit to stdout as JSON. → R-35

- **I-7.11** Optional subprocess dispatch: implement `dispatch_to_wiki_enrich(manifest_dict, vault_id, vault_root, wiki_enrich_bin) → dict`. When `--ingest` flag passed, write manifest to tempfile and call `wiki-enrich --manifest-file <path>` (or pipe via stdin). Parse result. → R-41

- **I-7.12** Unit tests: `tests/test_wiki_extract_concepts.py`. Cover: prompt construction, manifest schema round-trip, idempotency short-circuit, de-duplication classifier, concept page writer (existing file skip). Use in-memory `SQLiteRepository` fixture (same pattern as existing tests). → R-43

- **I-7.13** Integration test: `tests/test_wiki_extract_concepts_integration.py`. Fixture: a small source page in `tests/fixtures/source_extract/source-page.md` with 3 mentionable concepts. Test: extraction → manifest has 3 items → re-run → `unchanged`. LLM call mocked via `pytest-mock` or `responses`. → R-43

- **I-7.14** `mypy --strict` compliance and `wiki-enrich.py` regression: verify `wiki_enrich.py` still handles `kind="concept"` pages from the new manifest without modification. Run `pytest tests/` (295+ tests must stay green). → R-43, R-41

- **I-7.15** Extend `wiki-enrich` with manifest-input flags (Decision-9): add `--manifest-file PATH` and `--manifest-stdin` to argparse; make mutually exclusive with `--source` (today `required=True` at `wiki_enrich.py:259`; relax to mutually-exclusive group); when manifest-input used, skip `check_wiki_ingest_version` + `wiki-ingest` subprocess and version check; load JSON, validate, index. Add 3 unit tests: (a) `--manifest-file` happy path against `registered_vault`; (b) mutual-exclusion argparse error (`--source` AND `--manifest-file` together → exit 1); (c) `--manifest-file` succeeds **with `wiki-ingest` absent from PATH** (mock `shutil.which → None`) — proves Decision-9 actually decouples the dependency. Update `skills/wiki-enrich/SKILL.md` with the new flags. → R-44, R-41

---

### 5. Use Cases

#### 5.1 UC-08: Extract concepts from a single source page

**Actors:**
- Operator (user or sub-agent)
- System (`wiki-extract-concepts` skill)
- LLM (Claude Sonnet 4.6 via Anthropic API)
- SQLite (`IndexRepository`)
- Filesystem (vault `_concepts/` directory)

**Preconditions:**
- Vault is registered (`wiki-init --register-existing` run).
- Source page is already indexed in `pages` table (either via `/wiki-enrich` or `/wiki-index-upsert`).
- `ANTHROPIC_API_KEY` is set in environment.
- `wiki-ingest` v1.1+ on PATH (required only if `--ingest` flag is used).

**Main Scenario:**
1. Operator: `/wiki-extract-concepts --vault trade-agents --vault-root /path/to/vault --source-page self-improving-trading-agent-on-hermes`
2. System: Resolves `--source-page` to absolute path; validates inside vault root (R-26 path guard).
3. System: Reads source page body from filesystem; computes `sha256(body)`.
4. System: Queries `source_state` for `(vault_id='trade-agents', source_kind='extract-concepts', scope='self-improving-trading-agent-on-hermes', key='source_hash')`. No prior record → proceed.
5. System: Queries `entities` + `entity_aliases` for `vault_id='trade-agents'`; serialises known-concepts list.
6. System: Calls Anthropic API (`claude-sonnet-4-6`, `temperature=0`): sends source body + known-concepts. Prompt instructs: "identify 3-10 key concepts; use exact slug/name for known concepts; for novel concepts provide slug, name, 1-3 sentence definition, source_quote (10-50 words), source_span (line numbers), entity_type."
7. System: Validates LLM response JSON; classifies into `create` / `mention` lists.
8. System: For each `create` item: writes `_concepts/<slug>.md` atomically; calls `repo.upsert_entity(is_candidate=1)`.
9. System: Calls `repo.replace_refs(...)` for all extracted entities (create + mention) against the source page.
10. System: Updates `source_state` with new `source_hash`.
11. System: Builds manifest; emits JSON to stdout.
12. Operator (optional): pipes stdout to `/wiki-enrich --manifest-stdin` or uses `--ingest` flag to auto-dispatch.

**Alternative Scenarios:**

- **A1: Concept already exists as confirmed (`is_candidate=0`)**
  1. De-duplication classifier identifies slug match.
  2. No concept page written, no entity downgrade.
  3. `page_entity_refs` row still created (`ref_type='mentioned'`).
  4. Manifest lists concept with `action="mentioned"`.

- **A2: LLM returns malformed JSON**
  1. System: JSON parse fails.
  2. System: Emits `{"error": "EXTRACTION_PARSE_ERROR", "message": "...", "details": {"raw_response": "<first 500 chars>"}}`.
  3. System: Exits with code 4. No files written, no DB mutations.

- **A3: Anthropic API unavailable**
  1. System: API call raises connection error after 1 retry.
  2. System: Emits `{"error": "LLM_API_UNAVAILABLE", ...}`, exits 3.

- **A4: `_concepts/` directory does not exist in vault**
  1. System: `mkdir -p <vault_root>/_concepts/` before first write.
  2. Proceeds normally.

- **A5: `--ingest` flag passed**
  1. After manifest built and emitted to stdout, system calls `/wiki-enrich` subprocess with manifest.
  2. wiki-enrich indexes concept pages and creates log_event row.
  3. Combined result `{"extraction": <manifest>, "index": <enrich_result>}` emitted.

**Postconditions:**
- 0 or more `_concepts/<slug>.md` files written in vault.
- `entities` table rows created with `is_candidate=1` for new concepts.
- `page_entity_refs` rows created for all extracted entities (create + mention) referencing source page.
- `source_state` row upserted with current `source_hash`.
- Manifest emitted to stdout.

**Acceptance Criteria:**
- After running on `trade-agents` vault with a real source page: `SELECT count(*) FROM entities WHERE vault_id='trade-agents' AND is_candidate=1` >= N (where N = count of novel concepts in manifest).
- `SELECT trust_level FROM page_entity_refs WHERE vault_id='trade-agents' AND page_slug='<source-slug>'` returns `'medium'` for all rows inserted by this skill.
- `SELECT source_quote FROM page_entity_refs WHERE entity_slug='<slug>'` is non-NULL and 10-50 words.
- Each written `_concepts/<slug>.md` has parseable YAML frontmatter with `is_candidate: true`.
- RTM rows covered: R-30, R-31, R-32, R-33, R-34, R-35, R-36, R-37, R-38, R-39, R-40, R-41, R-42.

---

#### 5.2 UC-09: Re-extract on source page change (idempotency)

**Actors:**
- Operator (user or sub-agent)
- System (`wiki-extract-concepts` skill)
- SQLite (`source_state` table)

**Preconditions:**
- UC-08 was run previously on the same source page (successful extraction recorded in `source_state`).

**Main Scenario A — Body unchanged:**
1. Operator: runs `/wiki-extract-concepts --vault V --vault-root P --source-page S` again.
2. System: Reads source page body; computes `sha256(body)`.
3. System: Queries `source_state`; finds matching hash.
4. System: Returns `{"status": "ok", "action": "unchanged", "manifest": null}`, exit 0.
5. No LLM API call made. No DB mutations.

**Main Scenario B — Body changed (e.g., operator corrected transcript):**
1. Operator: edits source page body (corrects typo, adds paragraph).
2. Operator: runs `/wiki-extract-concepts --vault V --vault-root P --source-page S`.
3. System: Reads body; computes new hash; mismatch with stored hash.
4. System: Proceeds with full extraction (steps 5-11 of UC-08 main scenario).
5. System: Calls `repo.replace_refs(...)` — atomically replaces all prior `page_entity_refs` for this source page with new extraction results.
6. System: Updates `source_state` with new hash.
7. New candidate entities created if LLM found novel concepts; existing ones not duplicated.

**Postconditions (Scenario A):**
- No files written. No DB mutations. No LLM API call. Fast exit (< 50ms).

**Postconditions (Scenario B):**
- Entity refs for source page reflect current body content.
- New concept pages created for any concepts not previously extracted.
- Previously extracted concepts not re-created (file exists → skip).

**Acceptance Criteria:**
- `SELECT count(*) FROM source_state WHERE vault_id=V AND source_kind='extract-concepts' AND scope=S` = 1 (single row, upserted).
- Re-run with unchanged body: `llm_calls` in response = 0 (or absent field if 0).
- Re-run with changed body: `SELECT count(*) FROM page_entity_refs WHERE vault_id=V AND page_slug=S` reflects updated extraction (no duplicate rows for same entity).
- RTM rows covered: R-39.

---

### 6. Schema and API Impact

**No new tables.** All required schema is already in place from Phase 3a:

| Table | Phase 3a status | R-3 usage |
|---|---|---|
| `entities` | Active; `is_candidate` field present (default 0) | New rows written with `is_candidate=1` |
| `entity_aliases` | Active; schema exists | Not written by R-3; read for known-concept de-dup |
| `page_entity_refs` | Active; `trust_level`, `source_quote`, `source_span` fields present | New rows with `trust_level='medium'`, provenance populated |
| `source_state` | Active; used by transcript adapter for idempotency | New rows with `source_kind='extract-concepts'` (verified: `source_state.source_kind` is `TEXT NOT NULL`, no CHECK constraint — `SCHEMA-v2.sql:378`; new value is allowed without DDL change) |
| `pages` | Active | Read-only (source page lookup); no new write |

**Possible schema clarification (not a change):** `page_entity_refs.source_span` column is in the `extracted_items` table DDL (line ~326 of SCHEMA-v2.sql) but NOT in `page_entity_refs` DDL (which has `line_start INTEGER` and `line_end INTEGER` separately). Resolution: R-3 uses `line_start` + `line_end` integer columns in `page_entity_refs`, not a combined `source_span` string. The LLM prompt will request separate start/end line numbers; the `source_span` field mentioned in the ROADMAP description refers to the conceptual span, not a literal DB column name.

**`IndexRepository` extension:** The DAL may need a new method `upsert_entity(...)` if one does not already exist. Phase 3a's `resolve_entity` stub is not this — that method resolves an entity by name/alias; what R-3 needs is a write-path upsert for newly discovered candidate entities. Check existing DAL methods before implementing; if `upsert_entity` is absent, add it to `IndexRepository` ABC and `SQLiteRepository` concrete class as part of I-7.7.

---

### 7. Acceptance Criteria (End-to-End Smoke Recipe)

The following recipe constitutes the Phase-3b gate for this task. Run against the `trade-agents` vault (already dogfooded in Phase 3a):

```bash
# Prerequisites
source .venv/bin/activate
export VAULT=trade-agents
export VAULT_ROOT=/path/to/trade-agents

# 1. Confirm baseline: existing candidate count (should be 0 after Phase 3a)
sqlite3 ~/.local/share/wiki-index/global.db \
  "SELECT count(*) FROM entities WHERE vault_id='$VAULT' AND is_candidate=1;"
# Expected: 0

# 2. Pick a source page that's already indexed
sqlite3 ~/.local/share/wiki-index/global.db \
  "SELECT slug FROM pages WHERE vault_id='$VAULT' AND type='summary' LIMIT 1;"
# Note the slug, e.g. SOURCE_SLUG=self-improving-trading-agent-on-hermes

# 3. Run extraction
python -m scripts.wiki_skills.wiki_extract_concepts \
  --vault $VAULT \
  --vault-root $VAULT_ROOT \
  --source-page $SOURCE_SLUG \
  > /tmp/extract-manifest.json
echo "Exit code: $?"
# Expected: 0

# 4. Verify manifest structure
python -c "
import json, sys
m = json.load(open('/tmp/extract-manifest.json'))
assert m['status'] == 'ok'
assert m['vault_id'] == '$VAULT'
assert isinstance(m['written'], list)
print(f'Concepts in manifest: {len(m[\"written\"])}')
"
# Expected: Concepts in manifest: N >= 1

# 5. Verify entity rows created with is_candidate=1
sqlite3 ~/.local/share/wiki-index/global.db \
  "SELECT count(*) FROM entities WHERE vault_id='$VAULT' AND is_candidate=1;"
# Expected: >= N

# 6. Verify provenance on page_entity_refs
sqlite3 ~/.local/share/wiki-index/global.db \
  "SELECT count(*) FROM page_entity_refs
   WHERE vault_id='$VAULT' AND page_slug='$SOURCE_SLUG'
   AND trust_level='medium' AND source_quote IS NOT NULL;"
# Expected: >= N

# 7. Idempotency: re-run → unchanged
python -m scripts.wiki_skills.wiki_extract_concepts \
  --vault $VAULT \
  --vault-root $VAULT_ROOT \
  --source-page $SOURCE_SLUG \
  | python -c "import json,sys; m=json.load(sys.stdin); assert m['action']=='unchanged' and m.get('manifest') is None, m"
# Expected: no exception (assertion passes — `manifest is None` distinguishes idempotency hit from a real extraction that found 0 concepts)

# 8. Concept pages on disk
ls $VAULT_ROOT/_concepts/*.md | head -5
# Expected: N new files present

# 9. Full test suite still green
pytest tests/ -q
# Expected: 295+ passed, 0 failed

# 10. mypy strict
mypy --strict scripts/wiki_skills/wiki_extract_concepts.py
# Expected: Success: no issues found
```

---

### 8. Resolved Decisions (closed 2026-05-27)

All blocking questions raised during Analysis Phase have been resolved by the operator. Decisions encoded in Meta block §0:

| Q | Resolution | Encoded in |
|---|---|---|
| **Q1 — `upsert_entity` DAL method** | Add to `IndexRepository` ABC (no direct SQL bypass). Phase 3a `resolve_entity` is read-path only; no write-path entity method exists today. | I-7.7 (verified via `grep` against `scripts/wiki_index/repository.py` — confirmed absent) |
| **Q2 — `--manifest-file` on `wiki-enrich`** | In scope for Task 003. ~30 LoC extension, two mutually exclusive input flags (`--source` XOR `--manifest-{file,stdin}`). | Decision-9, R-44, I-7.15 |
| **Q3 — `source_span` LLM format** | Human-readable `"L12-L18"`; parser converts to `line_start=12, line_end=18` for `page_entity_refs` DB columns. | Decision-10, R-33 acceptance bullet (d), §6 Schema clarification |
| **Q4 — concept page file-write ownership** | Option A: `wiki-extract-concepts` writes `_concepts/<slug>.md` itself; `/wiki-enrich` performs index-only upsert (no file writes). ADR-001 clarified, not violated. | Decision-8, R-36, I-7.6 |

**Status**: Analysis Phase complete. Ready for `task-reviewer` gate before Architecture Phase.
