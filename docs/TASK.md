# TASK: wiki-extract-concepts — Epic 7 Entity Resolver Entry-Point (v2 / RESUMED post-TASK-004)

### 0. Meta Information

- **Task ID:** 003
- **Slug:** `wiki-extract-concepts`
- **Mode:** Standard
- **Status:** `COMPLETE` (2026-05-28) — all 15 beads shipped (003-00 manifest-consumer refactor → 003-14 mypy+regression sweep) via `/vdd-develop` (003-00) + `/vdd-develop-all` chain (003-01..003-14). `/vdd-multi` adversarial sweep applied 6 inline hardening fixes (C-1 idempotency-ordering CRITICAL, H-1 absolute-path rejection, H-2 TOCTOU `write_concept_page` tuple-return, H-3 source_slug kebab validation, M-1 LLM input-size + BadRequestError catch, M-2 schema slug regex) + 6 regression tests. **Final state**: 394 pytest passed / 4 skipped (was 328 baseline post-TASK-004; **+66 net new tests** across TASK 003 v2), `mypy --strict scripts/` clean on 55 files. 3 LOW findings deferred (L-1 datetime import style, L-3 defensive NULL check, security CWE-209 SDK-metadata deep sweep). v2 superseded the PAUSED v1 snapshot archived at [docs/tasks/task-003-wiki-extract-concepts.md](./tasks/task-003-wiki-extract-concepts.md); v1→v2 deltas catalogued in **Decision-15** + **Decision-16** + the **Post-TASK-004 mini-revision** section.
- **Epic:** Epic 7 — Entity Resolver (R-3 only; R-4/R-5 deferred)
- **Predecessor:** TASK 004 [docs/tasks/task-004-wiki-ingest-vendoring.md](./tasks/task-004-wiki-ingest-vendoring.md) — **COMPLETE** 2026-05-27 (Python-import-only vendor of `wiki_ingest`; in-process `ingest()` API available at `scripts.wiki_ingest.commands.ingest`).
- **Related artifacts:**
  - [docs/ROADMAP.md](./ROADMAP.md) — §P1 R-3 entry; promotes from 🟡 PAUSED → 🟢 ACTIVE on this task's revision
  - [docs/ARCHITECTURE.md](./ARCHITECTURE.md) — §2 "Concept Extractor" component; §3.4 UC-08 sequence diagram (post-TASK-004 NOTE to be resolved by this task's implementation phase)
  - [docs/SCHEMA-v2.sql](./SCHEMA-v2.sql) — `entities` / `entity_aliases` / `page_entity_refs` DDL
  - [docs/WIKI-INGEST-V1.1-CONTRACT.md](./WIKI-INGEST-V1.1-CONTRACT.md) — manifest schema (Class A producer contract); now applies to in-process consumers as well
  - [docs/adr/ADR-001-wiki-ingest-integration.md](./adr/ADR-001-wiki-ingest-integration.md) — Option I (Wrap + Index); §1.5.2 transport now in-process per Decision-14
  - [docs/adr/ADR-002-multi-vault-bottleneck-corrections.md](./adr/ADR-002-multi-vault-bottleneck-corrections.md) — vault_id partitioning + Class A/B/C layering
  - [scripts/wiki_skills/wiki_enrich.py](../scripts/wiki_skills/wiki_enrich.py) — host of the manifest consumer functions `_validate_manifest` + `index_from_manifest` (now imported in-process by this skill — see Decision-15)
  - [scripts/wiki_ingest/commands/ingest.py](../scripts/wiki_ingest/commands/ingest.py) — vendored programmatic API (R-46 of TASK 004); decorative `known_concepts` parameter is the future synthesiser-subagent hook (out-of-scope for this task — see §1.3 Non-goals)

- **Decisions carried forward from Tasks 001/002/004:**
  - **Decision-1 (2026-05-25)**: Option I (Wrap + Index). ADR-001.
  - **Decision-2 (2026-05-26)**: Single global DB with `vault_id` partitioning. ADR-002.
  - **Decision-3 (2026-05-26)**: `vault_id` REQUIRED explicit. ADR-002 §D1.1.
  - **Decision-4 (2026-05-26)**: Class A/B/C data layering contract. ADR-002 §D8.
  - **Decision-5 (2026-05-27)**: UC-06/UC-07 superseded by `/wiki-enrich`.
  - **Decision-11..14 (2026-05-27)**: TASK 004 vendoring decisions (Option 5 Python-import-only; snapshot policy; `ingest()` signature + `IngestError`; subprocess fallback path retained). All shipped — see [docs/tasks/task-004-*](./tasks/task-004-wiki-ingest-vendoring.md).

- **Decisions carried forward from TASK 003 v1 (unchanged):**
  - **Decision-6 (2026-05-27)**: `wiki-extract-concepts` lives in this repo, not a separate package.
  - **Decision-7 (2026-05-27)**: Ship R-3 only; R-4 (`wiki-confirm` promotion CLI) and R-5 (`wiki-alias` + search expansion + lint-collision) deferred until LLM extraction quality is observed on real vaults.
  - **Decision-8 (2026-05-27)**: File-write ownership for `_concepts/<slug>.md` — Option A: this skill writes the files itself, emits a manifest, and the index-only upsert step consumes it. ADR-001 **clarified** (not violated): wiki-ingest owns *raw-source* synthesis; derivative pages may be written by downstream skills provided they emit a v1.1-compatible manifest.
  - **Decision-10 (2026-05-27)**: LLM `source_span` format is human-readable `"L12-L18"`; parser converts to `line_start=12, line_end=18` integer columns in `page_entity_refs`.

- **New decisions for v2 of this task (post-TASK-004 mini-revision):**
  - **Decision-15 (2026-05-27)**: **In-process manifest consumption replaces subprocess dispatch.** In v1, two paths were proposed for handing the wiki-extract-concepts manifest off to the indexing step: (a) pipe stdout to `wiki-enrich --manifest-stdin` (operator-driven), or (b) `wiki-extract-concepts --ingest` subprocess-calls `wiki-enrich --manifest-file <tempfile>`. Both required adding a new `--manifest-{file,stdin}` flag pair to `wiki-enrich` (former Decision-9, R-44, I-7.15). After TASK 004 vendored wiki-ingest and refactored `wiki_enrich.py` to expose stable manifest-consumer functions, the cheaper path is to **import those functions in-process**. This: (i) eliminates the `--manifest-{file,stdin}` argparse expansion on `wiki-enrich` (R-44 and I-7.15 dropped from this task), (ii) eliminates subprocess JSON round-trip overhead in the `--ingest` auto-dispatch path, (iii) preserves the standalone usability — operators can still pipe `wiki-extract-concepts | jq ...` for inspection, but the auto-dispatch path is now direct, (iv) removes the wiki-enrich CLI surface coupling that v1 introduced. **Decision-9 from v1 is hereby retracted.** Decision-15 supersedes it. Effects on RTM/Issues: R-44 dropped; I-7.15 dropped; R-41 acceptance updated (in-process consumer call instead of subprocess); I-7.11 acceptance updated (in-process import, no subprocess). **See Decision-16 for the resolution of the cross-skill coupling Decision-15 would otherwise introduce.**

  - **Decision-16 (2026-05-27)**: **Extract manifest consumer to a neutral module — resolve cross-skill coupling before it lands.** Decision-15's first draft would have `wiki_extract_concepts.py` import `_validate_manifest` (note the leading underscore — Python convention for "internal") and `index_from_manifest` directly from `scripts.wiki_skills.wiki_enrich`. Promoting an underscore-prefixed function to "stable cross-skill API" by documentation alone is architecturally sour: the underscore says "internal", the import says "public", the docstring says "stable" — three contradictory sources of truth. The clean resolution is to **extract both functions plus `WikiIngestError` into a new neutral module** `scripts/wiki_skills/_manifest_consumer.py`, rename `_validate_manifest` → `validate_manifest` (no underscore — promote to public), and re-export the symbols from `wiki_enrich.py` for backward compatibility (preserves existing test imports without rename churn). After the refactor: both `wiki_enrich` (subprocess + vendored path consumer) and `wiki_extract_concepts` (manifest-producer consumer) import from `_manifest_consumer` — no skill depends on another skill. **Architecturally**: `_manifest_consumer.py` is a *sub-layer* below the skills layer (the leading underscore is on the MODULE name, signaling "internal infrastructure of the skill layer" — not on the symbols inside, which are public). Sized at ~130 LoC mechanical extract + ~20 LoC imports + back-compat shim (per architecture-reviewer measurement of `wiki_enrich.py:152-282`). **Scheduled as I-7.0 — the FIRST bead of this task, executed before any wiki_extract_concepts code lands**, so that I-7.11's import is from a clean module from the outset (no "import-from-sibling then refactor later" two-step). Pays for itself the first time a third consumer appears (likely soon: batch-ingest, background-reindex, or webhook-driven indexing). The choice between Option A (rename + split `WikiIngestError`/`ManifestValidationError`) and Option B (move-as-is, re-export `WikiIngestError`) is a planner-level micro-decision; **Option B is recommended** because it keeps the test-suite churn minimal and `WikiIngestError` is already the established catch-all name. Effects: new module `scripts/wiki_skills/_manifest_consumer.py` created; `wiki_enrich.py` re-exports for back-compat; `wiki_extract_concepts.py` imports from `_manifest_consumer`; the "private-prefix promoted to public" anti-pattern flagged in the v2 architecture critique is eliminated, not deferred.

    **Considered-and-rejected simpler alternative (per architecture-reviewer caveat 4):** "Rename `_validate_manifest` → `validate_manifest` *in place* inside `wiki_enrich.py`, keep `_validate_manifest` as a deprecation alias, and let `wiki_extract_concepts` import `validate_manifest` from `wiki_enrich` directly." Saves the new file (~10 LoC vs ~130). **Rejected on layering grounds, not on YAGNI cost**: skill-to-skill imports remain a smell even when the symbol is public — the principle "`scripts/wiki_skills/` is the user-facing skill layer; cross-imports between skills indicate missing sub-layer" still applies. The architecture-reviewer acknowledged this is a borderline call and would accept the simpler path too if the operator preferred a smaller diff. Operator chose Decision-16 (the layering-honest path) deliberately; future readers should see the choice was made with the simpler path on the table.

---

### 0.1 Post-TASK-004 mini-revision — change list (v1 → v2)

| Area | v1 (paused) | v2 (active) | Driver |
|---|---|---|---|
| Dispatch to indexer | `wiki-enrich --manifest-file <tempfile>` subprocess; or operator pipes to `--manifest-stdin` | In-process import from new neutral module: `from scripts.wiki_skills._manifest_consumer import validate_manifest, index_from_manifest` | Decision-15 + Decision-16 |
| Manifest consumer location | Inside `wiki_enrich.py` as private `_validate_manifest` + `index_from_manifest` | Extracted to neutral module `scripts/wiki_skills/_manifest_consumer.py`; `wiki_enrich.py` re-exports for back-compat | Decision-16 (cross-skill coupling resolution) |
| `wiki-enrich` CLI surface | Mutually-exclusive `--source` XOR `--manifest-{file,stdin}` group | **Unchanged from current state.** `--source` remains `required=True`. No new flags added by this task. | Decision-15 retracts Decision-9 |
| R-44 (`wiki-enrich` accepts manifest input) | Required; planned for I-7.15 | **DROPPED** — not needed under in-process call | Decision-15 |
| I-7.15 (extend wiki-enrich argparse) | Required (3 sub-tests) | **DROPPED** | Decision-15 |
| I-7.0 (manifest consumer extraction) | Not present | **Added as the FIRST bead** of this task — refactor lands before any wiki_extract_concepts code; ~30 LoC + 4 test-import updates | Decision-16 |
| I-7.11 (dispatch implementation) | `dispatch_to_wiki_enrich(manifest_dict, …)` subprocess call | `dispatch_to_indexer(manifest_dict, vault_id, vault_root, db_path) → dict` direct call into in-process `index_from_manifest` (validation via `validate_manifest`) — both imported from `_manifest_consumer` | Decision-15 + Decision-16 |
| R-41 acceptance bullet (b) | "subprocess after manifest generation (preferred)" | "in-process call into `index_from_manifest` after `validate_manifest`, both imported from `_manifest_consumer`" | Decision-15 + Decision-16 |
| Idempotency, schema, RTM rows R-30..R-43 (except R-41) | — | **Unchanged.** | Carried forward |
| Use Cases UC-08, UC-09 | — | UC-08 step 12 (operator subprocess) replaced by Postcondition note: when `--ingest` flag is set the indexing happens before manifest emission. UC-08 alt scenario A5 rewritten to reflect in-process flow. UC-09 unchanged. | Decision-15 |
| Anthropic API usage | Direct LLM call from this skill | **Unchanged.** Out of scope of TASK 004; TASK 003's responsibility. | Carried forward |
| `upsert_entity` DAL extension (I-7.7a) | Required | **Unchanged.** | Carried forward (still no write-path method on the DAL) |
| Optional reuse of vendored primitives | Not contemplated | **Optional**: `wiki_extract_concepts.py` MAY import `scripts.wiki_ingest._safety.slugify` and `atomic_write_text` for code reuse; alternatively, this repo's own primitives (`scripts/wiki_index/security.validate_inside_vault`, stdlib) suffice. **Planner-level micro-decision.** Either choice is acceptable; default is "use repo-local primitives" to minimise vendored-module coupling. | Decision-12 (vendored is a snapshot, not a stable API) — keeps coupling minimal |

---

### 1. General Description

#### 1.1 Goal

(Unchanged from v1.) Implement the first working piece of Epic 7 (entity resolver): an LLM-driven extraction pass that reads a summary page already in a vault, identifies candidate concept entities mentioned in it, de-duplicates against known entities already in the DB, and emits a wiki-ingest v1.1-compatible manifest listing proposed new `_concepts/<slug>.md` pages and entity rows. The manifest is consumed by `index_from_manifest()` — **in-process** (Decision-15) when `--ingest` is set, or by an external operator pipeline (`wiki-extract-concepts ... | jq ...`) when it is not.

The Karpathy promise: each source ingest touches 1 source page + a handful of concept pages. Closing the gap to "10-15 pages per ingest" (Karpathy's compounding target) requires the entity layer to be activated. This task activates it, with candidate rows remaining in `is_candidate=1` quarantine until R-4 promotion logic is implemented.

#### 1.2 Scope

- **In scope (R-3 only):**
  - New skill `wiki-extract-concepts` (slash command `/wiki-extract-concepts`).
  - New Python entry point `scripts/wiki_skills/wiki_extract_concepts.py`.
  - LLM extraction pass (Claude Sonnet 4.6): reads a single source page body, returns candidate concept slugs + definitions + provenance spans.
  - Pre-extraction de-duplication: query `entities` table for the vault before LLM call; pass canonical names to LLM as known-concepts, matching the structural shape of CONTRACT §2 known-concepts (the vendored `ingest()` accepts the same shape via its `known_concepts` parameter — useful for cross-process consistency even though that parameter is currently decorative).
  - Manifest emission: output a wiki-ingest v1.1-compatible JSON manifest to stdout.
  - **In-process dispatch to indexer** (Decision-15): when `--ingest` is set, call `_validate_manifest(manifest, vault_id, vault_root)` and `index_from_manifest(manifest, vault_id, vault_root, db_path)` from `scripts.wiki_skills.wiki_enrich` directly (no subprocess).
  - Idempotency: re-extraction on same source page (same `file_hash`) returns `status=unchanged`.
  - All new entity rows written with `is_candidate=1`.
  - All new `page_entity_refs` rows carry `trust_level='medium'`, `source_quote`, and `(line_start, line_end)` populated from LLM output (parsed from `"Lstart-Lend"` per Decision-10).
  - Multi-vault: `vault_id` required on every call; no cross-vault entity bleed.
  - DAL extension: `upsert_entity(vault_id, slug, name, type, is_candidate, canonicalized_by, first_seen, last_updated)` added to `IndexRepository` ABC + `SQLiteRepository` impl (I-7.7a — still required; Phase 3a only shipped the read-path `resolve_entity` stub).

- **Out of scope (deferred):**
  - R-4: `wiki-confirm <slug>` CLI for candidate→confirmed promotion.
  - R-4: automatic promotion on N mentions threshold.
  - R-5: `wiki-alias` CLI to register aliases.
  - R-5: `wiki-search` alias expansion.
  - R-5: `wiki-lint` alias-collision detection.
  - Vector search / semantic de-duplication (Epic 8).
  - Batch extraction across multiple source pages (can be scripted externally using the new skill).
  - **`--manifest-file`/`--manifest-stdin` on `wiki-enrich`** (was v1 R-44/I-7.15) — dropped under Decision-15.
  - Synthesiser-subagent hook into vendored `ingest()` (the decorative `known_concepts` parameter): future TASK; not this one.

#### 1.3 Non-goals

- This task does not introduce new DB tables. All required schema (`entities`, `entity_aliases`, `page_entity_refs`) is already present from Phase 3a.
- This task does not change `resolve_entity` (read-path stub remains `NotImplementedError` until R-4 lands).
- This task does not modify `wiki_enrich.py` argparse or core flow. It only **imports** two of its functions (`_validate_manifest`, `index_from_manifest`). Those functions' signatures are inherited as the integration contract; any future refactor of `wiki_enrich.py` that breaks them is a coordinated change.
- This task does not touch the vendored `scripts/wiki_ingest/` package. Decision-12 (snapshot, no local divergence) is preserved.

---

### 2. Requirements Traceability Matrix (RTM)

> Numbering continues from R-29 (last requirement in Phase 3a) through R-43. **R-44 is dropped** (v1 scope retracted by Decision-15). New requirements added by v2: none — the change is reductive.

| ID | Requirement | Status | Acceptance Bullets |
|---|---|---|---|
| **R-30** | New skill `wiki-extract-concepts` with slash command entry point | planned | (a) `skills/wiki-extract-concepts/SKILL.md` exists and follows existing skill template; (b) `.claude/commands/wiki-extract-concepts.md` symlinked; (c) `scripts/wiki_skills/wiki_extract_concepts.py` entry point with `main(argv)` signature consistent with other wiki skills |
| **R-31** | `--vault` and `--source-page` required arguments; `--vault-root` required for vault filesystem operations | planned | (a) Missing `--vault` → argparse error + non-zero exit; (b) Missing `--source-page` → argparse error + non-zero exit; (c) `--source-page` validated inside vault root via `validate_inside_vault` (R-26 guard); (d) `--db-path` optional override mirrors `wiki-enrich` pattern; (e) `--ingest` optional boolean flag for in-process auto-dispatch (Decision-15) |
| **R-32** | Pre-extraction query: read known entities from DB before LLM call | planned | (a) `SELECT slug, name FROM entities WHERE vault_id = ?` (plus aliases JOIN via `entity_aliases`) executes before any LLM API call; (b) Result serialised to JSON matching CONTRACT §2 known-concepts format `[{"slug": ..., "name": ..., "aliases": [...]}]`; (c) Empty vault (0 entities) handled gracefully — LLM call proceeds with empty list |
| **R-33** | LLM extraction call: Claude Sonnet 4.6, deterministic temperature, structured output | planned | (a) Model = `claude-sonnet-4-6` (default; overridable via `--model`); (b) `temperature=0` on API call (reproducibility); (c) `max_tokens` ≤ 4096 for extraction response; (d) Prompt instructs LLM to return JSON array of candidate concepts with fields: `slug`, `name`, `definition` (1-3 sentences), `source_quote` (10-50 words from source body), `source_span` (`Lstart-Lend` — Decision-10), `entity_type` (from `entities.type` CHECK enum); (e) LLM response validated against expected schema before use — malformed JSON → `EXTRACTION_PARSE_ERROR` with raw response in error details |
| **R-34** | De-duplication at extraction time: LLM receives known-concept list; returns exact existing slug where match | planned | (a) Known-concepts JSON passed in LLM prompt as "use exact slug/name where concept is already known"; (b) LLM response items whose `slug` matches an existing entity in the vault are classified as `action=mention` (ref only, no new concept page); (c) Items with novel slug are classified as `action=create`; (d) Classification logged in manifest `extraction_summary` field for operator visibility |
| **R-35** | Manifest output: wiki-ingest v1.1-compatible JSON | planned | (a) Manifest `status` field is `"ok"` on success; (b) `vault_id` matches caller's `--vault`; (c) `written[]` array contains one entry per `action=create` concept, `kind="concept"`, `path="_concepts/<slug>.md"`, `action="created"`; existing-file skips emit `action="unchanged"`; (d) `source` object carries source page `slug` and `hash`; (e) `log_event` object present with `event_type="ingest"`, `subject=<source-page-title>`; (f) Manifest is emitted to stdout as JSON; (g) No manifest emitted on failure — error envelope only; (h) Manifest passes `_validate_manifest(...)` from `scripts.wiki_skills.wiki_enrich` (proves contract compatibility before in-process indexer dispatch) |
| **R-36** | Concept page generation: write `_concepts/<slug>.md` files into vault | planned | (a) Each new concept page written to `<vault_root>/_concepts/<slug>.md` before manifest emission; (b) Frontmatter includes: `type: concept`, `vault_id: <vault-id>` (ADR-002 §D1.1 invariant), `slug`, `name`, `date: <today>`, `tags: [concept, candidate]`, `is_candidate: true`, `source_page: <source-slug>`, `trust_level: medium`; (c) Body includes: `# <name>`, definition paragraph from LLM, `## Mentions`, provenance block referencing source page with `source_quote`; (d) File written atomically (write to tempfile, rename — repo-local primitive or optional reuse of vendored `_safety.atomic_write_text`); (e) Existing file at target path → skip write, include in manifest with `action="unchanged"` |
| **R-37** | Entity row upsert: `is_candidate=1` for all R-3 extracted entities | planned | (a) After concept page written, `repo.upsert_entity(...)` called with `is_candidate=1`; (b) Existing confirmed entity (`is_candidate=0`) for same `(vault_id, slug)` → no downgrade; `action` in manifest = `"mentioned"`, no page write; (c) `canonicalized_by` field set to `"llm:claude-sonnet-4-6@<date>"`; (d) `first_seen` and `last_updated` set to extraction timestamp |
| **R-38** | `page_entity_refs` rows: `trust_level='medium'`, provenance populated | planned | (a) For each extracted entity (both `create` and `mention`), insert a `page_entity_refs` row linking source page to entity; (b) `trust_level='medium'`; (c) `source_quote` populated from LLM output (10-50 words); (d) `line_start` + `line_end` integer columns populated from parsing `"Lstart-Lend"` (Decision-10); (e) `ref_type='mentioned'`; (f) Uses `repo.replace_refs(...)` semantics for the source page's entity refs (atomic delete + insert for re-extraction idempotency) |
| **R-39** | Idempotency: same source page (same file_hash) → `status=unchanged`, no LLM call | planned | (a) Before LLM call, compute `sha256(source_page_body)` and compare against `source_state` table entry `(vault_id, source_kind='extract-concepts', scope=<source_slug>, key='source_hash')`; (b) Match → return `{"status": "ok", "action": "unchanged", "manifest": null}`, exit 0, no LLM API call; (c) Mismatch or no prior record → proceed with extraction, update `source_state` row after success |
| **R-40** | Multi-vault partitioning: `vault_id` enforced throughout | planned | (a) All DB queries include `vault_id = ?` predicate; (b) Concept pages written under `vault_root` provided by `--vault-root`; (c) No cross-vault entity lookup; (d) `validate_inside_vault` applied to every file path written |
| **R-41** | Integration with the indexing layer: manifest emitted by this skill is consumed in-process by `index_from_manifest` (Decision-15) | planned | (a) Running `/wiki-extract-concepts --vault V --vault-root P --source-page S` emits a manifest dict to stdout that — when passed to `_validate_manifest(m, V, P)` — does not raise `WikiIngestError`; (b) When `--ingest` flag is passed, this skill calls `_validate_manifest` then `index_from_manifest(m, V, P, db_path)` in-process (no subprocess); the combined output emitted to stdout is `{"extraction": <manifest>, "index": <enrich_summary>}` mirroring the v1 contract shape; (c) After full pipeline: `SELECT count(*) FROM entities WHERE vault_id=V AND is_candidate=1` increases by count of new concepts; (d) If `--ingest` is NOT set, only the manifest is emitted; operator may inspect it or pipe into a future tool — no implicit indexing; (e) `wiki_enrich.py`'s `--source` CLI surface is NOT modified by this task; (f) Failure inside `index_from_manifest` returns `partial`/`error` envelope mirroring `wiki-enrich`'s existing partial-success contract |
| **R-42** | Error handling and exit codes | planned | (a) Exit 0 = full success or `unchanged`; (b) Exit 1 = argument/usage error; (c) Exit 2 = source page not found in vault or not indexed; (d) Exit 3 = LLM API unavailable or auth failed; (e) Exit 4 = `EXTRACTION_PARSE_ERROR` (LLM returned malformed JSON); (f) Exit 5 = partial write (some concept pages written, index upsert failed for some — `PARTIAL_INDEX_FAILURE` envelope mirrors wiki-enrich's shape including `written_so_far` + `index_failed` arrays); (g) Exit 6 = manifest validation failed (`WikiIngestError` from `_validate_manifest`); (h) All failures emit JSON error envelope to stdout: `{"error": "<CODE>", "message": "...", "details": {...}}` |
| **R-43** | Tests: unit + integration coverage | planned | (a) Unit: LLM prompt construction tested with mock known-concepts list; (b) Unit: manifest schema round-trip + acceptance by `_validate_manifest` (live import; not duplicated locally); (c) Unit: idempotency short-circuit (mock `source_state` hit); (d) Unit: in-process dispatch path — patch `scripts.wiki_skills.wiki_enrich.index_from_manifest` and assert it is called once with the correct manifest dict when `--ingest` is set; assert it is NOT called when `--ingest` is absent; (e) Integration: extraction on a real-form fixture source page (`tests/fixtures/source_extract/`) → manifest contains ≥ 1 concept with correct fields; (f) Integration: re-run on same fixture → `status=unchanged`, 0 LLM calls; (g) `mypy --strict` clean for `scripts/wiki_skills/wiki_extract_concepts.py`; (h) Regression: all existing tests (328 baseline post-TASK-004) continue to pass |
| ~~**R-44**~~ | ~~`wiki-enrich` accepts pre-built manifest via `--manifest-file PATH` or `--manifest-stdin`~~ | **DROPPED (v2)** | Superseded by Decision-15 — in-process import replaces CLI-flag dispatch. |

---

### 3. Integration Choice: New Skill + In-Process Indexer Dispatch (Decision-15 + Decision-16)

**Decision**: Implement `wiki-extract-concepts` as a **standalone new skill** that emits a manifest, then optionally calls `validate_manifest` + `index_from_manifest` from the **neutral module** `scripts.wiki_skills._manifest_consumer` **in-process** (when `--ingest` flag is set). The neutral module is created by I-7.0 — the first bead — as a precondition for all wiki_extract_concepts work, so no skill depends on another skill for manifest consumption.

**Rationale for standalone (not extending `/wiki-enrich`)** — unchanged from v1:
1. `/wiki-enrich` is an ADR-001 Option I bridge: its contract is "given a raw source, call `wiki-ingest` (now in-process per TASK 004) for synthesis, then index the manifest." `wiki-extract-concepts` does not call `wiki-ingest` — it IS the synthesis step (for concept extraction). The responsibilities do not compose cleanly under the existing `wiki-enrich` flag surface.
2. A `--extract-concepts` flag on `/wiki-enrich` would conflate two distinct phases: (a) source summarisation (wiki-ingest's job) and (b) concept extraction from an already-ingested summary page.
3. A new skill is trivially composable: `wiki-enrich` first (ingest), then `wiki-extract-concepts` (enrich entity layer). Each skill can be tested and run independently.

**Rationale for in-process dispatch (new in v2)** — see Decision-15:
1. After TASK 004, `validate_manifest` and `index_from_manifest` are stable in-process callables. No subprocess overhead, no manifest tempfile, no JSON round-trip beyond what `index_from_manifest`'s internal `upsert_main` capture already does.
2. No new CLI flags on `wiki-enrich`. Decision-15 explicitly retracts v1 Decision-9.
3. The auto-dispatch path is now a direct function call; the import surface is small (three symbols) and lives in the neutral `_manifest_consumer` module (Decision-16) — not in a sibling skill.

**Invocation flow (operator perspective):**

```
# Step 1: ingest source page (existing flow, no change — TASK 004 in-process path)
/wiki-enrich --vault trade-agents --vault-root /path --source /raw/lesson.md

# Step 2: extract concepts; choose ONE of:

# (a) inspection mode — emit manifest only, do not index
/wiki-extract-concepts --vault trade-agents --vault-root /path \
    --source-page self-improving-trading-agent-on-hermes

# (b) auto-dispatch — in-process indexing (Decision-15)
/wiki-extract-concepts --vault trade-agents --vault-root /path \
    --source-page self-improving-trading-agent-on-hermes --ingest
# → emits {"extraction": <manifest>, "index": <summary>}
```

---

### 4. Epics & Issues

#### Epic E7: wiki-extract-concepts (R-3) — revised issue set

- **I-7.0** **(NEW, blocking-first; Decision-16)** Extract manifest consumer to neutral module `scripts/wiki_skills/_manifest_consumer.py` **before any wiki_extract_concepts code is written**. This bead is a pure refactor of the post-TASK-004 wiki_enrich.py; it lands by itself, gets reviewed, and is the only prerequisite all subsequent beads (I-7.1..I-7.14) share. **Move-surface size confirmed by architecture-reviewer**: `wiki_enrich.py:152-282` carries ~131 LoC across `_validate_manifest` (~26 LoC), `index_from_manifest` (~103 LoC), `WikiIngestError` (~2 LoC), plus ~20 LoC of shared imports. Acceptance: (a) new file `scripts/wiki_skills/_manifest_consumer.py` created with three public symbols: `validate_manifest(manifest: dict[str, Any], expected_vault_id: str, vault_root: Path) -> None` (no underscore — promoted from `wiki_enrich._validate_manifest`), `index_from_manifest(manifest: dict[str, Any], vault_id: str, vault_root: Path, db_path: str | None = None) -> dict[str, Any]` (moved verbatim from `wiki_enrich.index_from_manifest`), and `WikiIngestError(Exception)` (moved verbatim from `wiki_enrich.WikiIngestError`); (b) `scripts/wiki_skills/wiki_enrich.py` updated to `from scripts.wiki_skills._manifest_consumer import validate_manifest, index_from_manifest, WikiIngestError` and assigns `_validate_manifest = validate_manifest` for backward compat with existing test imports; the internal call at `wiki_enrich.py:388` switches to `validate_manifest(...)` (no underscore); (c) **back-compat alias lifecycle (reviewer caveat 2)**: existing `tests/test_wiki_enrich.py` imports of `_validate_manifest` (lines 21, 98, 104, 112; dynamic import at line 467) STAY POINTED AT `wiki_enrich._validate_manifest` for one release cycle so the alias is exercised by the test suite — not dead code. The NEW `tests/test_manifest_consumer.py` (bullet d) imports from `_manifest_consumer` directly. After one release cycle, a follow-up bead deprecates the alias with a `DeprecationWarning` and migrates the tests; (d) new file `tests/test_manifest_consumer.py` adds 4 unit tests: validate_manifest happy path, status≠ok rejection, vault_id mismatch rejection, path-traversal rejection — exercising the public surface directly via the neutral module; (e) `pytest tests/ -q` passes with the 328 baseline + 4 new tests = **332 passed**; (f) `mypy --strict scripts/wiki_skills/` clean; (g) `git diff --stat` shows net change ≤ **200 LoC** (relaxed from initial estimate per architecture-reviewer caveat 3 — the move surface is ~130 LoC, plus imports + back-compat shim; 200-LoC ceiling preserves the "split if growth is surprising" guard without false-alarming on the legitimate move); (h) **stale-doc sweep (reviewer caveat 1)**: any residual references to `--manifest-file PATH` / `--manifest-stdin`, R-44, I-7.15, `dispatch_to_wiki_enrich`, or "private-prefix `_validate_manifest`" that contradict Decisions 15+16 are removed from `docs/ARCHITECTURE.md` and any other doc. The reviewer flagged lines 179 (Phase 3b extension note) and 429 (wiki-enrich skill entry) — both were swept inline before I-7.0 started, but the bead's PR diff should grep-verify no residue remains. → R-41 (refactor that enables clean in-process dispatch)

- **I-7.1** Python entry point `scripts/wiki_skills/wiki_extract_concepts.py`. Implement argparse surface: `--vault`, `--vault-root`, `--source-page` (slug or relative path), `--db-path` override, `--model` (default `claude-sonnet-4-6`), `--ingest` (auto-dispatch flag — Decision-15). Implement `main(argv)` consistent with other wiki skills. Stub all internal functions initially (Stub-First). **Depends on I-7.0.** → R-30, R-31, R-42

- **I-7.2** Skill wrapper `skills/wiki-extract-concepts/SKILL.md` and slash command `.claude/commands/wiki-extract-concepts.md`. Follow existing skill template (see `skills/wiki-enrich/SKILL.md`). Create symlinks into `.agent/skills/`. → R-30

- **I-7.3** Pre-extraction DB query: implement `load_known_entities(repo, vault_id) → list[dict]`. Query `entities` LEFT JOIN `entity_aliases` for the vault; serialize to CONTRACT §2 format. Handle empty result gracefully. → R-32

- **I-7.4** LLM extraction: implement `extract_concepts_llm(source_body, known_entities, model, max_tokens) → list[dict]`. Build prompt with source body + known-concepts JSON block. Call Anthropic API with `temperature=0`. Validate response JSON schema. Return structured list with `slug`, `name`, `definition`, `source_quote`, `source_span`, `entity_type`, `action` fields. → R-33, R-34

- **I-7.5** De-duplication classifier: implement `classify_candidates(llm_results, known_slugs) → tuple[list_create, list_mention]`. Items whose slug exists in vault entities → `mention` (ref only). Novel slugs → `create`. Log classification in extraction summary. → R-34

- **I-7.6** Concept page writer: implement `write_concept_page(vault_root, candidate, source_slug, today) → Path`. Write `_concepts/<slug>.md` atomically. Frontmatter per R-36 spec. Body: `# <name>`, definition, `## Mentions` provenance block. Skip-and-return-unchanged if file exists. **Planner-level micro-decision**: use repo-local `tempfile + os.replace` primitive **or** import `scripts.wiki_ingest._safety.atomic_write_text`. Default to repo-local to minimise vendored-snapshot coupling (Decision-12). → R-36

- **I-7.7a** DAL extension: add `upsert_entity(vault_id, slug, name, type, is_candidate, canonicalized_by, first_seen, last_updated) → None` to `IndexRepository` ABC (`scripts/wiki_index/repository.py`) and implement in `SQLiteRepository` (atomic INSERT … ON CONFLICT DO UPDATE; `is_candidate` downgrade-guard at SQL level: `is_candidate = MIN(excluded.is_candidate, entities.is_candidate)`). Add unit tests in `tests/test_sqlite_repository.py`. Phase 3a left this method out (only `resolve_entity` read-path exists). → R-37

- **I-7.7b** Call site in skill: implement `upsert_extracted_entity(repo, vault_id, candidate, source_slug, today) → str`. Call `repo.upsert_entity(...)` with `is_candidate=1`. Guard against downgrading confirmed entities (`is_candidate=0`) at the call layer too (defensive — SQL guard from I-7.7a is primary). → R-37

- **I-7.8** `page_entity_refs` upsert: implement `upsert_entity_refs(repo, vault_id, source_slug, source_project, all_candidates)`. Parse `"Lstart-Lend"` strings into `(line_start, line_end)` integer pairs (Decision-10). Collect `(entity_slug, ref_type='mentioned', source_quote, line_start, line_end, trust_level='medium')` for all extracted candidates (create + mention). Call `repo.replace_refs(...)` atomically. → R-38

- **I-7.9** Idempotency gate: implement `check_idempotency(repo, vault_id, source_slug, current_hash) → bool`. Query `source_state` with `source_kind='extract-concepts'`. Return True if unchanged. After successful extraction, update `source_state` row. → R-39

- **I-7.10** Manifest builder: implement `build_manifest(vault_id, source_slug, source_hash, create_list, mention_list, log_event, vault_root) → dict`. Output structure per R-35. Emit to stdout as JSON when `--ingest` is NOT set. → R-35

- **I-7.11** **In-process indexer dispatch (REVISED, Decision-15 + Decision-16)**: implement `dispatch_to_indexer(manifest_dict, vault_id, vault_root, db_path) → dict`. Inside, do (1) `from scripts.wiki_skills._manifest_consumer import validate_manifest, index_from_manifest, WikiIngestError` (NEUTRAL module, not the wiki_enrich skill — Decision-16), (2) call `validate_manifest(manifest_dict, vault_id, vault_root)` (raises `WikiIngestError` on contract violation — converted to exit 6 by caller), (3) call `index_from_manifest(manifest_dict, vault_id, vault_root, db_path=db_path)`, (4) return the summary dict. **No subprocess.** No tempfile. **Import target locked at module top** (not inside `dispatch_to_indexer` body) so that `unittest.mock.patch` test sites are stable — see I-7.12 patch-target note. The combined emit in `main()` becomes `{"extraction": <manifest>, "index": <summary>}`. → R-41

- **I-7.12** Unit tests: `tests/test_wiki_extract_concepts.py`. Cover: prompt construction, manifest schema round-trip + `validate_manifest` acceptance (live import from `_manifest_consumer` — exercises Decision-15+16 contract directly), idempotency short-circuit, de-duplication classifier, concept page writer (existing file skip), in-process dispatch (`unittest.mock.patch('scripts.wiki_skills.wiki_extract_concepts.index_from_manifest')` to assert exactly-once call when `--ingest` set and zero calls when absent). **Patch-target note**: because I-7.11 imports at module top, the bound name lives in `scripts.wiki_skills.wiki_extract_concepts` — patch *there*, not at `_manifest_consumer`. Use in-memory `SQLiteRepository` fixture (same pattern as existing tests). → R-43

- **I-7.13** Integration test: `tests/test_wiki_extract_concepts_integration.py`. Fixture: a small source page in `tests/fixtures/source_extract/source-page.md` with 3 mentionable concepts. Test: extraction → manifest has 3 items → re-run → `unchanged`. LLM call mocked via `pytest-mock` or `responses`. Add a `--ingest` end-to-end variant that exercises the in-process dispatch path against the in-memory SQLite fixture and asserts the indexed-entities count. → R-43

- **I-7.14** `mypy --strict` compliance and regression sweep: verify `wiki_enrich.py` still works against all existing tests; verify importing `_validate_manifest`/`index_from_manifest` from a sibling module passes mypy with no new ignores. Run `pytest tests/` (328+ tests must stay green). → R-43, R-41

- ~~**I-7.15**~~ (Extend `wiki-enrich` with `--manifest-file` / `--manifest-stdin`) — **DROPPED (v2)**. Superseded by Decision-15.

---

### 5. Use Cases

#### 5.1 UC-08: Extract concepts from a single source page (REVISED for v2)

**Actors:**
- Operator (user or sub-agent)
- System (`wiki-extract-concepts` skill)
- LLM (Claude Sonnet 4.6 via Anthropic API)
- SQLite (`IndexRepository`)
- Filesystem (vault `_concepts/` directory)
- Indexer (`scripts.wiki_skills.wiki_enrich` functions, **in-process** — Decision-15)

**Preconditions:**
- Vault is registered (`wiki-init --register-existing` run).
- Source page is already indexed in `pages` table (either via `/wiki-enrich` or `/wiki-index-upsert`).
- `ANTHROPIC_API_KEY` is set in environment.
- TASK 004 vendored module importable: `from scripts.wiki_ingest.commands.ingest import ingest` succeeds (transitively guarantees `wiki_enrich.py` module-level import does not fail; required by Decision-15 in-process dispatch).

**Main Scenario (without `--ingest`):**
1. Operator: `/wiki-extract-concepts --vault trade-agents --vault-root /path/to/vault --source-page self-improving-trading-agent-on-hermes`
2. System: Resolves `--source-page` to absolute path; validates inside vault root (R-26 path guard).
3. System: Reads source page body from filesystem; computes `sha256(body)`.
4. System: Queries `source_state` for `(vault_id='trade-agents', source_kind='extract-concepts', scope='self-improving-trading-agent-on-hermes', key='source_hash')`. No prior record → proceed.
5. System: Queries `entities` + `entity_aliases` for `vault_id='trade-agents'`; serialises known-concepts list.
6. System: Calls Anthropic API (`claude-sonnet-4-6`, `temperature=0`): sends source body + known-concepts. Prompt instructs: "identify 3-10 key concepts; use exact slug/name for known concepts; for novel concepts provide slug, name, 1-3 sentence definition, source_quote (10-50 words), source_span (Lstart-Lend), entity_type."
7. System: Validates LLM response JSON; classifies into `create` / `mention` lists.
8. System: For each `create` item: writes `_concepts/<slug>.md` atomically; calls `repo.upsert_entity(is_candidate=1)`.
9. System: Calls `repo.replace_refs(...)` for all extracted entities (create + mention) against the source page; parses `"Lstart-Lend"` → `(line_start, line_end)` integers.
10. System: Updates `source_state` with new `source_hash`.
11. System: Builds manifest; emits JSON to stdout.
12. Operator: may pipe stdout to `jq` for inspection; further indexing is operator-controlled.

**Main Scenario (with `--ingest` — Decision-15):**
1.–10. As above.
11′. System: Builds manifest dict (held in memory, not emitted to stdout yet).
12′. System: `from scripts.wiki_skills.wiki_enrich import _validate_manifest, index_from_manifest`.
13′. System: Calls `_validate_manifest(manifest, 'trade-agents', vault_root)`. On `WikiIngestError` → emit `{"error": "MANIFEST_INVALID", ...}`, exit 6. No further DB mutations (entity rows + page_entity_refs from steps 8–9 remain — already committed; the index-step failure is on the metadata mirror, not on the concept rows; operator can re-run after fix).
14′. System: Calls `index_from_manifest(manifest, 'trade-agents', vault_root, db_path)`. Captures summary dict (with `upserted[]`, `failed[]`, `log_event_id`).
15′. System: Emits combined `{"extraction": <manifest>, "index": <summary>}` to stdout. Exit 0 on full success; exit 5 if `summary["failed"]` is non-empty (mirrors wiki-enrich's `PARTIAL_INDEX_FAILURE` shape).

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

- **A5: `--ingest` flag passed (REVISED for v2 — Decision-15)**
  1. After manifest built (in-memory, not stdout-emitted yet), system imports `_validate_manifest` + `index_from_manifest` from `scripts.wiki_skills.wiki_enrich`.
  2. `_validate_manifest` runs first; on contract violation → exit 6 with `MANIFEST_INVALID` envelope (concept-page writes are not rolled back; operator inspects + re-runs).
  3. `index_from_manifest` runs; indexes each `kind=concept` written path; mirrors `log_event` to `log_events`.
  4. Combined result `{"extraction": <manifest>, "index": <summary>}` emitted; exit 0 on full success, exit 5 on `summary["failed"]` non-empty.

**Postconditions:**
- 0 or more `_concepts/<slug>.md` files written in vault.
- `entities` table rows created with `is_candidate=1` for new concepts.
- `page_entity_refs` rows created for all extracted entities (create + mention) referencing source page.
- `source_state` row upserted with current `source_hash`.
- Without `--ingest`: manifest emitted to stdout.
- With `--ingest`: indexed rows reflect manifest; combined JSON emitted.

**Acceptance Criteria:**
- After running on `trade-agents` vault with a real source page: `SELECT count(*) FROM entities WHERE vault_id='trade-agents' AND is_candidate=1` >= N (where N = count of novel concepts in manifest).
- `SELECT trust_level FROM page_entity_refs WHERE vault_id='trade-agents' AND page_slug='<source-slug>'` returns `'medium'` for all rows inserted by this skill.
- `SELECT source_quote FROM page_entity_refs WHERE entity_slug='<slug>'` is non-NULL and 10-50 words.
- `SELECT line_start, line_end FROM page_entity_refs WHERE entity_slug='<slug>'` returns integer pair parsed from LLM `"Lstart-Lend"` output.
- Each written `_concepts/<slug>.md` has parseable YAML frontmatter with `is_candidate: true`.
- With `--ingest`: combined JSON contains both `extraction.status="ok"` and `index.upserted[*]` for each `kind=concept` entry.
- RTM rows covered: R-30, R-31, R-32, R-33, R-34, R-35, R-36, R-37, R-38, R-39, R-40, R-41, R-42.

---

#### 5.2 UC-09: Re-extract on source page change (idempotency) — UNCHANGED

**Actors:**
- Operator
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
| `entities` | Active; `is_candidate` field present (default 0) | New rows written with `is_candidate=1` via `repo.upsert_entity` (I-7.7a new method) |
| `entity_aliases` | Active; schema exists | Not written by R-3; read for known-concept de-dup |
| `page_entity_refs` | Active; `trust_level`, `source_quote`, `line_start`, `line_end` fields present | New rows with `trust_level='medium'`, provenance populated |
| `source_state` | Active; used by transcript adapter for idempotency | New rows with `source_kind='extract-concepts'` (verified: `source_state.source_kind` is `TEXT NOT NULL`, no CHECK constraint — `SCHEMA-v2.sql:378`; new value is allowed without DDL change) |
| `pages` | Active | Read-only (source page lookup); no new write |

**Note on `source_span` (Decision-10):** the LLM is prompted to return `"Lstart-Lend"` strings; the parser converts these to two integer columns (`line_start`, `line_end`) in `page_entity_refs`. No DB column named `source_span` is introduced by this task.

**`IndexRepository` extension (I-7.7a):** Phase 3a's `resolve_entity` stub is read-path; the write-path `upsert_entity` method is added by this task to `IndexRepository` ABC and `SQLiteRepository` concrete impl.

**Cross-module import (v2 / Decision-15 + Decision-16):** `scripts.wiki_skills.wiki_extract_concepts` imports three symbols from the **neutral** module `scripts.wiki_skills._manifest_consumer` (created by I-7.0, *not* from a sibling skill):
- `validate_manifest(manifest: dict, expected_vault_id: str, vault_root: Path) -> None` (raises `WikiIngestError`)
- `index_from_manifest(manifest: dict, vault_id: str, vault_root: Path, db_path: str | None = None) -> dict`
- `WikiIngestError` (exception class)

`wiki_enrich.py` re-exports the same three symbols (after I-7.0 lands) so that all existing test imports continue to work without rename. The leading-underscore variant `_validate_manifest` is kept as a module-level alias in `wiki_enrich.py` for one release cycle (back-compat hatch), then deletable. The new `_manifest_consumer.py` module is the single source of truth.

**Why this matters architecturally**: v1 of TASK 003 introduced a cross-CLI subprocess hop (rejected by Decision-15). The first draft of v2 replaced it with a cross-*skill* Python import — better, but coupled `wiki_extract_concepts` to `wiki_enrich` via a private-prefix function (`_validate_manifest`), an anti-pattern (the underscore says "internal", the import said "public"). Decision-16 + I-7.0 resolve this by introducing a neutral module so no skill depends on another skill. The pattern is reusable: future skills that need manifest consumption (batch-ingest, background-reindex, webhook indexer) import from the same neutral module without any further refactor.

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

# 3a. Inspection mode (no --ingest): manifest only
python -m scripts.wiki_skills.wiki_extract_concepts \
  --vault $VAULT \
  --vault-root $VAULT_ROOT \
  --source-page $SOURCE_SLUG \
  > /tmp/extract-manifest.json
echo "Exit code: $?"
# Expected: 0

# 3b. Verify manifest structure + neutral-module contract (Decision-15 + Decision-16)
python -c "
import json
from pathlib import Path
from scripts.wiki_skills._manifest_consumer import validate_manifest
m = json.load(open('/tmp/extract-manifest.json'))
assert m['status'] == 'ok'
assert m['vault_id'] == '$VAULT'
assert isinstance(m['written'], list)
# Live contract check via the neutral _manifest_consumer module (no underscore — public API)
validate_manifest(m, '$VAULT', Path('$VAULT_ROOT'))
print(f'Concepts in manifest: {len(m[\"written\"])}; validate_manifest passed')
"
# Expected: Concepts in manifest: N >= 1; validate_manifest passed

# 4. Auto-dispatch mode (--ingest): in-process indexer call
python -m scripts.wiki_skills.wiki_extract_concepts \
  --vault $VAULT \
  --vault-root $VAULT_ROOT \
  --source-page $SOURCE_SLUG \
  --ingest \
  > /tmp/extract-with-ingest.json
python -c "
import json
r = json.load(open('/tmp/extract-with-ingest.json'))
assert r['extraction']['status'] == 'ok'
assert isinstance(r['index']['upserted'], list)
print(f'Indexed {len(r[\"index\"][\"upserted\"])} pages in-process')
"
# Expected: Indexed N pages in-process

# 5. Verify entity rows created with is_candidate=1
sqlite3 ~/.local/share/wiki-index/global.db \
  "SELECT count(*) FROM entities WHERE vault_id='$VAULT' AND is_candidate=1;"
# Expected: >= N

# 6. Verify provenance on page_entity_refs
sqlite3 ~/.local/share/wiki-index/global.db \
  "SELECT count(*) FROM page_entity_refs
   WHERE vault_id='$VAULT' AND page_slug='$SOURCE_SLUG'
   AND trust_level='medium' AND source_quote IS NOT NULL
   AND line_start IS NOT NULL AND line_end IS NOT NULL;"
# Expected: >= N

# 7. Idempotency: re-run → unchanged
python -m scripts.wiki_skills.wiki_extract_concepts \
  --vault $VAULT \
  --vault-root $VAULT_ROOT \
  --source-page $SOURCE_SLUG \
  | python -c "import json,sys; m=json.load(sys.stdin); assert m['action']=='unchanged' and m.get('manifest') is None, m"
# Expected: no exception

# 8. Concept pages on disk
ls $VAULT_ROOT/_concepts/*.md | head -5
# Expected: N new files present

# 9. wiki-enrich CLI surface untouched (Decision-15 invariant)
python -m scripts.wiki_skills.wiki_enrich --help | grep -E 'manifest-file|manifest-stdin' && \
  echo "FAIL: manifest flags appeared on wiki-enrich (Decision-15 violated)" || \
  echo "OK: wiki-enrich surface preserved"
# Expected: OK: wiki-enrich surface preserved

# 10. _manifest_consumer module exists and exports the promoted public API (Decision-16 invariant)
python -c "
from scripts.wiki_skills._manifest_consumer import validate_manifest, index_from_manifest, WikiIngestError
import scripts.wiki_skills.wiki_enrich as we
# Back-compat alias preserved one release cycle
assert we.validate_manifest is validate_manifest, 'wiki_enrich must re-export validate_manifest'
assert we.index_from_manifest is index_from_manifest, 'wiki_enrich must re-export index_from_manifest'
assert we._validate_manifest is validate_manifest, 'wiki_enrich must keep _validate_manifest alias for back-compat'
print('OK: _manifest_consumer is the canonical source; wiki_enrich re-exports correctly')
"
# Expected: OK: _manifest_consumer is the canonical source; wiki_enrich re-exports correctly

# 11. Full test suite still green
pytest tests/ -q
# Expected: 332+ passed (328 baseline + 4 from I-7.0 + N from I-7.12/I-7.13), 0 failed

# 12. mypy strict
mypy --strict scripts/wiki_skills/wiki_extract_concepts.py scripts/wiki_skills/_manifest_consumer.py
# Expected: Success: no issues found
```

---

### 8. Resolved Decisions (v2 / 2026-05-27 resume)

| Q | Resolution | Encoded in |
|---|---|---|
| **Q1 — `upsert_entity` DAL method** | Add to `IndexRepository` ABC. `resolve_entity` is read-path only; write-path doesn't exist today. | Decision-6 (carried), I-7.7a |
| ~~**Q2 — `--manifest-file` on `wiki-enrich`**~~ | **RETRACTED.** In-process import replaces flag. | Decision-15 supersedes Decision-9 |
| **Q3 — `source_span` LLM format** | `"L12-L18"` strings parsed to `(line_start, line_end)` integer columns. | Decision-10 (carried), R-33(d), R-38(d) |
| **Q4 — concept page file-write ownership** | Option A — this skill writes files; manifest emitted; consumer is `index_from_manifest` in-process. | Decision-8 (carried), R-36, I-7.6 |
| **Q5 — manifest dispatch mechanism (v2)** | In-process function call (Decision-15). No subprocess. No new CLI flags on `wiki-enrich`. | Decision-15, R-41, I-7.11 |
| **Q6 — synthesiser-subagent hook into vendored `ingest()`** | Out of scope. The decorative `known_concepts` parameter on vendored `ingest()` (Decision-13) is for a future task; this skill does not invoke `ingest()` at all. | §1.3 Non-goals |
| **Q7 — vendored primitives reuse** | Optional planner-level micro-decision. Default = use repo-local primitives. | I-7.6 note |

**Status**: Analysis Phase v2 complete. Architecture review needed only for the small §3.4 sequence-diagram update (in-process dispatch). Ready for `task-reviewer` gate.

---

### 9. Task-Review Self-Checklist

- [x] Every active RTM row (R-30..R-43) has at least one Issue (I-7.0..I-7.14) and at least one acceptance bullet. R-44 explicitly dropped (Decision-15).
- [x] No RTM orphans: R-30→I-7.1/I-7.2, R-31→I-7.1, R-32→I-7.3, R-33→I-7.4, R-34→I-7.4/I-7.5, R-35→I-7.10, R-36→I-7.6, R-37→I-7.7a/I-7.7b, R-38→I-7.8, R-39→I-7.9, R-40→I-7.6/I-7.8, R-41→I-7.0/I-7.11 (refactor enables clean dispatch + dispatch implementation), R-42→I-7.1, R-43→I-7.0/I-7.12/I-7.13/I-7.14 (I-7.0 adds 4 test_manifest_consumer cases).
- [x] UC-08 covers R-30..R-42 main path + alternates. UC-09 covers R-39 idempotency.
- [x] Decisions 6, 7, 8, 10 carried forward unchanged. Decision-15 documented and explicitly supersedes Decision-9. Decision-16 resolves the cross-skill coupling that Decision-15 alone would have introduced.
- [x] No contradiction with TASK 004 ship state: `wiki-enrich` `--source` flag remains `required=True` (no mutual-exclusion group); `validate_manifest` and `index_from_manifest` semantics preserved (this task **moves** them to a neutral module via I-7.0 and re-exports them from `wiki_enrich.py` for back-compat — signatures and behaviour unchanged).
- [x] Scope (out) section explicitly calls out the dropped R-44 / I-7.15 work and the synthesiser-subagent hook.
- [x] I-7.0 lands **first**; all subsequent beads depend on it (clean import target available from day 1 — no "import-then-refactor" two-step).
- [x] Smoke recipe covers: inspection mode (Smoke 3a), neutral-module contract (Smoke 3b), in-process dispatch (Smoke 4), idempotency (Smoke 7), invariant check that wiki-enrich CLI surface is untouched (Smoke 9), `_manifest_consumer` is canonical and re-exports work (Smoke 10), test suite + mypy (Smoke 11-12).
- [x] Cross-skill import anti-pattern flagged in the v2 architecture critique is **eliminated, not deferred** (Decision-16 / I-7.0). No skill depends on another skill for manifest consumption.
