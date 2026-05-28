# TASK: wiki-extract-concepts v3 — Deterministic skill + orchestrator-driven synthesis

### 0. Meta Information

- **Task ID:** 003
- **Slug:** `wiki-extract-concepts` (v3 refactor; **v3.1 spec** post `/vdd-multi` iteration-1 hardening)
- **Mode:** Standard (refactor task — same epic, simpler implementation)
- **Status:** `SHIPPED` (2026-05-28, commit `43812f2`) — 15 beads merged via `/vdd-develop-all`; post-ship `/vdd-multi` surfaced 22 residual findings (1 CRITICAL + 8 HIGH + 9 MEDIUM + 4 LOW) — ALL fixed in the same ship commit. Final gate: 450 pytest pass + 4 skipped, mypy --strict clean (55 files), anthropic-free invariant clean, patch-target lock clean. New envelopes added: `INVALID_SOURCE_HASH` (exit 2), `IDEMPOTENCY_UPDATE_FAILED` (exit 5). Out-of-scope follow-ups (architectural) tracked as `H-PERF-3` / `H-5` / `H-6` in [docs/KNOWN_ISSUES.md](./KNOWN_ISSUES.md). Pre-ship history: opened immediately after v2 ship (396 pytest passed) to correct an architectural inconsistency surfaced during dogfood attempt on `trade-agents` vault — v2's embedded LLM call inside the Python skill broke the established repo pattern ("all skills are deterministic plumbing; calling agent does LLM work"). v3.1 brings this skill into line with `wiki-ingest` / `summarizing-meetings` precedent. v2 spec preserved at [docs/tasks/task-003-v2-wiki-extract-concepts.md](./tasks/task-003-v2-wiki-extract-concepts.md).
- **Epic:** Epic 7 — Entity Resolver (R-3 architectural refactor; R-4/R-5 still deferred)
- **Predecessor:** TASK 003 v2 — **COMPLETE** 2026-05-28 (15 beads shipped, **396 pytest passed / 4 skipped**, mypy --strict clean on 55 files). All shipped work is preserved as the deterministic apply-path infrastructure; v3 removes only the embedded LLM call + adjacent scaffolding.
- **Related artifacts:**
  - [docs/ROADMAP.md](./ROADMAP.md) — R-3 ✅ DONE 2026-05-28 (v2); v3 entry to be added on ship
  - [docs/ARCHITECTURE.md](./ARCHITECTURE.md) — §2.1 Concept Extractor; §3.4 UC-08 sequence; §1.5.2 transport diagram
  - [docs/SCHEMA-v2.sql](./SCHEMA-v2.sql) — unchanged (no DDL impact)
  - [docs/WIKI-INGEST-V1.1-CONTRACT.md](./WIKI-INGEST-V1.1-CONTRACT.md) — same manifest contract
  - [scripts/wiki_skills/wiki_enrich.py](../scripts/wiki_skills/wiki_enrich.py) — sibling skill; no change in v3
  - [scripts/wiki_skills/_manifest_consumer.py](../scripts/wiki_skills/_manifest_consumer.py) — neutral consumer; unchanged
  - [scripts/wiki_ingest/commands/ingest.py](../scripts/wiki_ingest/commands/ingest.py) — **the architectural precedent** that v3 follows. Vendored wiki-ingest is a deterministic orchestrator (no LLM call inside); summary-passthrough requires source to already have a `type: summary` frontmatter, written by the calling agent / `summarizing-meetings` skill. v3 wiki-extract-concepts becomes its analog for the entity layer.

- **Decisions carried forward (1–14, 15, 16 unchanged):**
  - Decisions 1–14: unchanged (Option I, vault_id partitioning, Class A/B/C layering, vendoring details, etc.)
  - Decision-15 + 16 (in-process manifest dispatch via neutral `_manifest_consumer.py`): unchanged — still applies to `apply` subcommand's `--ingest` path

- **New decision for v3:**
  - **Decision-17 (2026-05-28)**: **Embedded LLM call in `wiki-extract-concepts` retracted; skill becomes deterministic; calling agent owns synthesis.** Rationale + considered-and-rejected alternatives unchanged from v3.0 (see expanded discussion at §3). v3.1 hardening pass closes the 9 must-fix findings without re-litigating the core architectural choice.

---

### 0.1 v2 → v3.1 change list (catalogue, post-vdd-multi)

| Area | v2 (shipped) | v3.1 (this task — post-hardening) | Driver |
|---|---|---|---|
| LLM call site | `anthropic.Anthropic().messages.create(...)` inside `extract_concepts_llm()` | **Removed.** Calling agent synthesizes in own context. | Decision-17 |
| `requirements.txt` | `anthropic>=0.34.0` | Dependency removed | Decision-17 |
| CLI shape | One monolithic `wiki-extract-concepts --vault ... --source-page ... [--ingest]` (8 flags) | Two subcommands: `prepare` (recon) + `apply` (write). `argparse(subparsers(required=True))` — operators get helpful error on legacy invocation. `status` deferred to YAGNI gate (M-6). | Decision-17, H-4 |
| **BREAKING CHANGE** for operators | n/a | Explicit BREAKING-CHANGE notice in CHANGELOG-equivalent locations (TASK §6, ROADMAP "Done"). Legacy `wiki-extract-concepts --vault X --source-page Y` (no subcommand) → argparse error pointing to new subcommand surface. | H-4 |
| Source-page synthesis | Embedded LLM | Calling agent: reads source via Read tool → consults `prepare` known-concepts output → emits candidates JSON in own context → pipes to `apply --candidates-stdin` | Decision-17 |
| `extract_concepts_llm()` function | ~50 LoC + 5 unit tests | **Deleted** | Decision-17 |
| `_build_extraction_prompt()` function | ~25 LoC in code | **Moved** to `.agent/skills/concept-extraction/SKILL.md` as operator-facing instruction text | Decision-17 |
| `_validate_extraction_schema()` | Required-keys subset check + kebab slug regex + Lstart-Lend span + entity_type whitelist | **Renamed → `_validate_candidates_schema()`** + **strict mode** (rejects items with keys outside the required set; `≠` check, not subset) + **per-field length caps** (`name ≤ 200`, `definition ≤ 2000`, `source_quote ≤ 500`) + **candidate count bound** (`1 ≤ len ≤ 25`) + **error envelope MUST NOT echo offending field content** (CWE-117) | H-2, H-6, H-9 |
| `_MAX_SOURCE_BODY_CHARS` (100K cap) | Pre-LLM-call guard | **Re-introduced in `prepare` as `_MAX_SOURCE_BODY_BYTES = 10_485_760` (10 MiB)** via `stat().st_size` check before `read_text()`. Reject with `SOURCE_TOO_LARGE` envelope (exit 2). Cap is no longer "decorative" — it's DoS protection on `prepare`'s sha256 + read pipeline. | M-3 (security), H-1 corollary |
| `_MAX_CANDIDATES_BYTES` (NEW) | n/a | **`= 1_048_576` (1 MiB)** cap on `--candidates-file` path AND on stdin payload. Reject with `CANDIDATES_TOO_LARGE` envelope (exit 4). Bounds fs-DoS attack surface from H-6. | H-6, H-5 |
| `--candidates-file PATH` | n/a | **REQUIRES `validate_inside_vault(candidates_path, vault_root)`**. File MUST live inside `--vault-root`. External transport = `--candidates-stdin` (documented as preferred). On parse failure, envelope emits `at line N column M` — **NOT file content** (CWE-117 / CWE-209 carried from v2). | H-5 |
| `LLMUnavailableError` | Exception class + main()'s exit-3 mapping | **Deleted** (no LLM call to fail) | Decision-17 |
| `ExtractionParseError` | Raised by LLM-output validator | **Kept.** Raised by `_validate_candidates_schema` on operator-supplied JSON. Same code, different caller. | preserved |
| Exit-code envelope (R-42) | 0/1/2/3/4/5/6 (7 codes) | 0/1/2/4/5/6 (6 codes — exit 3 LLM_API_UNAVAILABLE deleted). Exit 2 sub-envelopes: `SOURCE_NOT_FOUND`, `INVALID_SOURCE_PATH`, `INVALID_SOURCE_SLUG`, **`SOURCE_TOO_LARGE`**, **`SOURCE_CHANGED_DURING_EXTRACTION`**, **`INVALID_CANDIDATES_PATH`** (new envelopes from H-1/H-5/M-3). Exit 4 sub-envelopes: `EXTRACTION_PARSE_ERROR`, **`CANDIDATES_TOO_LARGE`**, **`CANDIDATE_COUNT_OUT_OF_BOUNDS`**, **`FIELD_TOO_LONG`**, **`UNKNOWN_FIELD`**. | Decision-17 + H-1/H-2/H-5/H-6/H-9 |
| `--model` and `--max-tokens` CLI flags | Pass-through to SDK call | **Deleted.** Orchestrator picks own model. | Decision-17 |
| `--orchestrator-id` flag (NEW) | n/a | **Optional** flag on `apply`. Operator-supplied free-form string; regex `^[a-z0-9._:@-]{1,64}$`. Populates `canonicalized_by` as `f"llm:{orchestrator_id}@{date}"`. Default = `"orchestrator"` if absent. Recovers v2's audit-trail attribution lost by Q9-v3.0; honest unknown beats hallucinated specific. | H-8 |
| `--ingest` flag | Triggers in-process `dispatch_to_indexer` | **Kept** on `apply` subcommand. Same semantics. | unchanged |
| `prepare` subcommand | n/a | **NEW.** Returns `{vault_id, source_slug, source_path, source_hash, is_unchanged, known_concepts, missing_concept_files: []}` JSON. Pre-flight for orchestrator. Idempotency check + size-cap check folded in. `missing_concept_files` warns operator about disk/DB drift (M-1). | Decision-17 + M-1 |
| `apply` subcommand | n/a (was main() body) | **NEW.** Reads candidates JSON via `--candidates-file PATH` or `--candidates-stdin`. **Requires `--source-hash <HEX>`** matching prepare's reported hash; mismatch → exit 2 `SOURCE_CHANGED_DURING_EXTRACTION` (H-1). Validates strict schema → classifies → writes pages (content-hash skip — see below) → upserts entities + refs → manifest → optional indexer dispatch. | Decision-17 + H-1 |
| `write_concept_page` skip semantics | `if target.exists(): return target` (v2: skip-on-exists, unconditional) | **`skip-only-if-content-identical`**: if file exists, compute sha256 of existing content vs sha256 of would-be-written content; identical → return path with `action="unchanged"`; different → **rewrite** with `action="updated"` + log warning. Eliminates C-1 drift between disk files and DB rows on partial-failure replay. | C-1 |
| Markdown body construction | f-string with raw `{name}`/`{definition}`/`{source_quote}` interpolation | **Sanitized**: `name` regex-allowlisted `^[\w\s\-.,:;()\'"!?]{1,200}$` + strip leading `#`/`---`; `definition` markdown-escaped (escape `\n## ` pattern, HTML tags); `source_quote` wrapped in `>` blockquote (eliminates inline `"..."` ambiguity AND `]]` wikilink-target attack). YAML frontmatter via `frontmatter.dumps` (PyYAML safe_dump confirmed) + adversarial regression tests for `name="---"` / `name="key: value"` / `name="\n- list-item"`. | H-7 |
| `_validate_extraction_schema()` semantic-quality check (NEW) | n/a | Optional substring check (operator-bypassable via env var): `if quote.lower() not in body.lower(): raise ExtractionParseError(FIELD_QUOTE_NOT_IN_BODY)` — provides cheap defense against hallucinated provenance (closes part of H-1 / M-5). | M-5 |
| `check_idempotency` + `update_idempotency_state` | Called from main() | **Kept.** `check_idempotency` called by `prepare`; `update_idempotency_state` called by `apply` **AFTER manifest build, gated on `summary["failed"]` being empty when `--ingest` is set** (C-1 invariant + ingest-failure rollback). | unchanged structurally |
| `write_concept_page`, `upsert_extracted_entity`, `upsert_entity_refs`, `build_manifest`, `dispatch_to_indexer`, `_parse_source_span`, `load_known_entities`, `classify_candidates` | Helper functions in module | **Mostly kept verbatim.** Two changes: (1) `write_concept_page` skip semantics (C-1 fix above); (2) `upsert_extracted_entity` reads `orchestrator_id` from caller, defaults `"orchestrator"` (Q9-v3.1 replaces Q9-v3.0). All other helpers unchanged. | C-1, H-8 |
| Manifest contract emitted | Same wiki-ingest v1.1 shape | **Unchanged.** Calling agent doesn't see it; `apply` builds it, optionally dispatches via `_manifest_consumer`. | unchanged |
| Skill wrapper `skills/wiki-extract-concepts/SKILL.md` | Operator-facing CLI invocation guide | **Rewritten.** Becomes a workflow description: two CLI subcommands + the orchestrator's role in between. Documents BREAKING CHANGE from v2. | Decision-17, H-4 |
| New `.agent/skills/concept-extraction/SKILL.md` | n/a | **NEW.** Operator-facing extraction prompt + JSON candidates contract. Loaded by the calling agent via Skill tool before synthesis. **Documented as security-sensitive in CONTRIBUTING-equivalent** (CODEOWNERS or top-of-file banner) — modifications require security-review (M-4). | Decision-17 + M-4 |
| New `workflows/wiki-extract-concepts.md` | n/a | **NEW.** Step-by-step workflow the calling agent follows: invoke `prepare` → load `concept-extraction` skill → synthesize candidates → invoke `apply` (passing `--source-hash` from prepare). | Decision-17 + H-1 |
| `bin/wiki-extract-concepts` wrapper | Pass-through to `python -m scripts.wiki_skills.wiki_extract_concepts $@` | **Unchanged at wrapper level**; operator-visible CLI is breaking change (`subparsers(required=True)`). Smoke-test in §7 asserts `bin/wiki-extract-concepts prepare --help` and `bin/wiki-extract-concepts apply --help` route correctly. | H-4 |
| `tests/test_wiki_extract_concepts.py` | **57 tests** (verified via `pytest --collect-only`; 12 LLM-mock + 45 deterministic) | **Refactored.** Drop 12 LLM-mock tests. Add ~6 prepare tests + ~4 apply tests + ~4 adversarial regression tests (markdown injection, YAML injection, per-field cap, unknown-field strict mode, candidate-count bound, source-hash mismatch). Net change: **+2 tests** (57 → ~59). | Decision-17 + H-1/H-6/H-7/H-9 |
| `tests/test_wiki_extract_concepts_integration.py` | 3 integration tests with anthropic mock | **Refactored.** Drop anthropic mock; replace with canned candidates JSON fixture. Same 3 scenarios (first / unchanged / --ingest). | Decision-17 |
| `tests/fixtures/source_extract/llm-response.json` | LLM-output fixture | **Renamed** → `candidates.json`; restructured (drop top-level wrapper; keep just the array since orchestrator emits raw array, not a metadata-wrapped object) | Decision-17 |
| Anthropic SDK exception catch list (5 types) | Wrapped to `LLMUnavailableError` with CWE-209 suppression | **Deleted.** No SDK call. | Decision-17 |
| L-V3.3 KNOWN_ISSUES entry (CWE-209) | STATUS: fixed | **Marked obsolete** by v3 (LLM call removed entirely; exception-chain question moot) | Decision-17 |
| Pytest target count | claimed "390+ passed" in v3.0 spec | **Corrected: target ~398 passed** (396 v2 baseline − 12 LLM-mock tests deleted + ~14 new tests = ~398). Verified via `pytest --collect-only` (57 in test file, 12 deletable, +~14 add). | H-3 |

---

### 1. General Description

#### 1.1 Goal

Bring `wiki-extract-concepts` into structural alignment with the established repo pattern: **skills are deterministic plumbing; calling agent (Claude Code / Gemini CLI / Cursor) does LLM-driven synthesis in its own context**.

The v2-shipped deterministic infrastructure (page writer, entity upsert with SQL downgrade-guard, refs upsert with line-span parse, idempotency gate, manifest builder, in-process indexer dispatch) is **preserved as-is** except for two narrow changes documented in §0.1 (`write_concept_page` content-hash skip per C-1; `upsert_extracted_entity` reads `orchestrator_id` per H-8). The new `prepare` subcommand replaces the front half of v2's `main()`. The middle step — LLM synthesis — moves to the calling agent.

#### 1.2 Scope (v3.1 — post-vdd-multi hardening)

**In scope:**

*Core refactor (v3.0):*
- Delete `extract_concepts_llm()` + `_build_extraction_prompt()` + `LLMUnavailableError` from `scripts/wiki_skills/wiki_extract_concepts.py`.
- Remove `anthropic>=0.34.0` from `requirements.txt`.
- Refactor `main()` into argparse subparsers: `prepare` and `apply`, with `subparsers(required=True)` so legacy invocation surfaces helpful error (H-4).
- Move extraction prompt + JSON candidates contract to `.agent/skills/concept-extraction/SKILL.md` (NEW; security-sensitive, M-4).
- Add `workflows/wiki-extract-concepts.md` (NEW).
- Rewrite `skills/wiki-extract-concepts/SKILL.md` with BREAKING CHANGE notice.

*v3.1 hardening:*
- **Strict schema validator** (`_validate_candidates_schema`, renamed from `_validate_extraction_schema`): reject items with keys outside required set (H-9); enforce candidate count `1 ≤ N ≤ 25` (H-2); enforce per-field caps `name ≤ 200`, `definition ≤ 2000`, `source_quote ≤ 500` (H-6); error envelope emits field-name + reason, NEVER offending content (H-5/CWE-117).
- **`apply --source-hash <HEX>` required**: mismatch with disk-recomputed hash → exit 2 `SOURCE_CHANGED_DURING_EXTRACTION` (H-1).
- **`apply --candidates-file PATH` validated via `validate_inside_vault`** (H-5); `--candidates-stdin` documented as preferred external-transport path.
- **`_MAX_CANDIDATES_BYTES = 1_048_576` (1 MiB)** cap on candidates input (file or stdin); reject with `CANDIDATES_TOO_LARGE` (H-5/H-6).
- **`_MAX_SOURCE_BODY_BYTES = 10_485_760` (10 MiB)** cap on source-page read in `prepare`; `stat().st_size` check before `read_text()`; reject with `SOURCE_TOO_LARGE` (M-3).
- **`write_concept_page` content-hash skip**: file exists + content identical → skip; file exists + content differs → rewrite with `action="updated"` + warning (C-1).
- **Markdown body sanitization**: `name` allowlist regex + strip leading `#`/`---`; `definition` escape `\n## ` and HTML tags; `source_quote` wrapped in `>` blockquote (H-7).
- **YAML safety adversarial regression tests**: `name="---"`, `name="key: value"`, `name="\n- list-item"`, `definition="<script>alert(1)</script>"` (H-7).
- **`--orchestrator-id <STRING>` flag on `apply`**: regex `^[a-z0-9._:@-]{1,64}$`; populates `canonicalized_by`; default `"orchestrator"` (H-8).
- **Semantic-quality optional check**: `source_quote` substring presence in source body — `ExtractionParseError(FIELD_QUOTE_NOT_IN_BODY)` if absent (M-5; operator-bypassable via env var `WIKI_EXTRACT_NO_QUOTE_CHECK=1`).
- **`prepare` warns about disk/DB drift**: `missing_concept_files: [...]` field listing entity rows whose `file_path` doesn't exist on disk (M-1).
- **BREAKING CHANGE notice**: §6 documents the CLI surface break; SKILL.md flags it; ROADMAP "Done" entry mentions it (H-4).
- **CONTRIBUTING-style security note** on `.agent/skills/concept-extraction/SKILL.md`: marked security-sensitive; modifications require code-review (M-4).

*Documentation:*
- Update `docs/ARCHITECTURE.md` §2.1 + §3.4 per architecture-reviewer's pre-flagged edit sites.
- Update `docs/ROADMAP.md` "Done" entry to mention v3.1.
- Update `docs/KNOWN_ISSUES.md` to mark L-V3.3 as obsoleted by v3.
- Add Decision-17 + Q10–Q15 to TASK.md (this file).

**Out of scope (deferred / non-goals):**

- `--llm-standalone` Pattern-C escape hatch for cron / headless use. Add ONLY when a real cron-batch use case surfaces.
- Subagent-spawn pattern (`.claude/agents/concept-extractor.md`). Rejected by /vdd-multi iteration 0 adversarial.
- `status` subcommand. YAGNI; add when actually needed (M-6 acknowledges UX cost).
- Batch surface for N-source-page workflows. Performance SEV-2 P-1 documented in KNOWN_ISSUES.
- Hash-pinning of `concept-extraction/SKILL.md` in manifest provenance. Documented as future hardening; not blocking v3.1.
- Restoration of `summary` page type as a CHECK constraint (vault_ingest concern, not this skill).
- Backward-compat alias for `extract_concepts_llm()`. The function was an internal helper, never exposed to operators. Clean delete.
- Backward-compat for v2's monolithic CLI invocation. Subcommand split IS a breaking change; operator must learn the new surface. Documented in §6.
- `--known-concepts-format=slugs-only` (compact known_concepts payload). Performance SEV-2 P-2 documented in KNOWN_ISSUES.

#### 1.3 Non-goals

- This task does not introduce new DB tables or schema changes.
- This task does not modify `wiki_enrich.py`, `_manifest_consumer.py`, or any other skill.
- This task does not change the manifest contract (v1.1 schema is the wire format).
- This task does not change the bead architecture of v2's deterministic helpers beyond the two narrow changes documented (C-1 + H-8).

---

### 2. Requirements Traceability Matrix (RTM)

**v3.1 RTM amendments (post-hardening):**

| ID | v2 Acceptance | v3.1 Acceptance | Change |
|---|---|---|---|
| **R-30** | Skill + slash command + Python entry point | (a) skill exists; (b) slash command symlinked; (c) Python entry has `main(argv)` dispatching to `prepare`/`apply` subparsers with `required=True` | refined + H-4 |
| **R-31** | `--vault`, `--vault-root`, `--source-page`, `--db-path`, `--model`, `--ingest` | (a) `prepare` accepts `--vault --vault-root --source-page [--db-path]`; (b) `apply` accepts same plus `--candidates-file PATH | --candidates-stdin` (mutex) and `--source-hash HEX` (REQUIRED) and `[--ingest] [--orchestrator-id STRING]`. `--model`, `--max-tokens` removed. | refined + H-1/H-8 |
| **R-32** | Pre-extraction known-concepts query | (a) Query executed by `prepare`; (b) Result emitted as JSON in `prepare` stdout payload; (c) Empty vault → `known_concepts: []`; (d) `missing_concept_files: [...]` warns disk/DB drift (M-1) | refined + M-1 |
| **R-33** | Claude Sonnet 4.6, temperature=0, max_tokens≤4096, JSON output | **RETIRED.** | retired |
| **R-33′** | Calling agent synthesizes candidates per the contract | (a) SKILL.md documents the prompt + JSON contract; (b) `apply` validates orchestrator-supplied JSON via **strict-mode `_validate_candidates_schema`** (kebab slug regex, Lstart-Lend, entity_type whitelist, no extra keys, per-field caps, count bound `1≤N≤25`, optional quote-in-body substring check); (c) malformed JSON → `apply` exits 4 with `EXTRACTION_PARSE_ERROR` (or `CANDIDATE_COUNT_OUT_OF_BOUNDS` / `FIELD_TOO_LONG` / `UNKNOWN_FIELD` / `CANDIDATES_TOO_LARGE`) envelope; envelope MUST NOT echo offending field content | new + H-2/H-5/H-6/H-7/H-9 |
| **R-34** | LLM receives known-concept list; uses exact slug on match | (a) `prepare` emits known-concepts; (b) SKILL.md prompt instructs orchestrator; (c) `apply.classify_candidates` partitions by known-slugs (v2 logic preserved); (d) optional `source_quote ∈ source_body` semantic check (M-5) | refined + M-5 |
| **R-35** | Manifest output: wiki-ingest v1.1-compatible | **Unchanged.** `apply` emits manifest with same schema. | unchanged |
| **R-36** | Concept page `_concepts/<slug>.md` atomic write | (a) `write_concept_page` content-hash skip semantics (C-1) — file-exists + same-content → skip; file-exists + diff-content → rewrite with `action="updated"`; (b) Markdown body sanitization — `name` regex-allowlist + strip; `definition` markdown-escape; `source_quote` `>` blockquote; (c) Atomic temp+rename preserved; (d) `mkdir -p` preserved | refined + C-1/H-7 |
| **R-37** | `repo.upsert_entity(is_candidate=1)` with SQL downgrade-guard | (a) Preserved; (b) `canonicalized_by = f"llm:{orchestrator_id}@{date}"` where `orchestrator_id` defaults `"orchestrator"` and is validated `^[a-z0-9._:@-]{1,64}$` (H-8) | refined + H-8 |
| **R-38** | `page_entity_refs` rows: `trust_level='medium'`, parsed Lstart-Lend | **Unchanged.** | unchanged |
| **R-39** | Idempotency: same source → unchanged | (a) `prepare` returns `is_unchanged: bool`; (b) `apply` requires `--source-hash` matching disk-recomputed hash → mismatch = exit 2 `SOURCE_CHANGED_DURING_EXTRACTION` (H-1); (c) `apply` updates `source_state` AFTER manifest build, gated on `summary["failed"]` empty when `--ingest` set | refined + H-1 |
| **R-40** | Multi-vault: `vault_id` enforced | **Unchanged.** | unchanged |
| **R-41** | In-process dispatch via `_manifest_consumer` | **Unchanged.** | unchanged |
| **R-42** | Error handling and exit codes | (a) Codes 0/1/2/4/5/6 preserved; (b) Exit 3 retired; (c) Exit 2 sub-envelopes: `SOURCE_NOT_FOUND`, `INVALID_SOURCE_PATH`, `INVALID_SOURCE_SLUG`, **`SOURCE_TOO_LARGE`**, **`SOURCE_CHANGED_DURING_EXTRACTION`**, **`INVALID_CANDIDATES_PATH`**; (d) Exit 4 sub-envelopes: `EXTRACTION_PARSE_ERROR`, **`CANDIDATES_TOO_LARGE`**, **`CANDIDATE_COUNT_OUT_OF_BOUNDS`**, **`FIELD_TOO_LONG`**, **`UNKNOWN_FIELD`**, **`FIELD_QUOTE_NOT_IN_BODY`**; (e) ALL envelopes emit error-code + field-name + reason — NEVER offending content | refined + H-5/H-6/H-9/M-3 |
| **R-43** | Tests: unit + integration + mypy --strict | (a) Drop 12 LLM-mock tests; (b) Add ~6 prepare + ~4 apply + ~4 adversarial-regression tests (markdown injection, YAML injection, per-field cap, unknown-field, count-bound, source-hash mismatch, candidates-file-outside-vault, candidates-file-too-large, source-too-large); (c) Refactor 3 integration tests to use canned candidates JSON fixture; (d) **Pytest count target: ~398 passed** (corrected from v3.0's 390+ claim per H-3); (e) `mypy --strict` clean | refined + H-3/H-1/H-5/H-6/H-7/H-9 |

**Active RTM (v3.1)**: R-30, R-31, R-32, R-33′, R-34, R-35, R-36, R-37, R-38, R-39, R-40, R-41, R-42, R-43.
**Retired**: R-33 (superseded by R-33′), R-44 (already retired in v2).

---

### 3. Integration Choice: Deterministic skill + orchestrator-driven synthesis (Decision-17)

*Unchanged from v3.0 — see archived v3.0 spec rationale + considered-and-rejected alternatives.*

**Architectural precedent**: `wiki-ingest` (vendored at `scripts/wiki_ingest/`) is a deterministic orchestrator with no LLM calls; summarization happens upstream via `summarizing-meetings` skill loaded by the calling agent. v3 wiki-extract-concepts mirrors this for the entity layer.

**Invocation flow (v3.1):**

```
Operator: /wiki-extract-concepts --vault X --source-page Y

# Calling agent loads workflows/wiki-extract-concepts.md and follows:

Step 1: wiki-extract-concepts prepare --vault X --vault-root P --source-page Y
  → JSON: {source_path, source_hash, is_unchanged, known_concepts, missing_concept_files}

Step 2: if is_unchanged=true → emit "unchanged" envelope; STOP.

Step 3: Skill({skill: "concept-extraction"}) — load prompt + JSON contract

Step 4: Read(source_path) — agent reads source body

Step 5: Synthesize candidates in own context per the contract. STRICT requirements:
  - 1 ≤ N ≤ 25 candidates
  - per-field caps: name ≤ 200, definition ≤ 2000, source_quote ≤ 500
  - kebab slug, Lstart-Lend span, entity_type in whitelist
  - NO extra keys
  - source_quote substring of source_body (best-effort)

Step 6: echo '<candidates-array>' | wiki-extract-concepts apply \
          --vault X --vault-root P --source-page Y \
          --source-hash <hash-from-prepare> \
          --candidates-stdin \
          [--orchestrator-id "claude-opus-4-7"] \
          [--ingest]

  → apply validates schema; recomputes source_hash from disk; rejects on
    mismatch (SOURCE_CHANGED_DURING_EXTRACTION) or schema violation.
  → On success: writes _concepts/<slug>.md (content-hash skip), upserts
    entities + refs, updates source_state, emits manifest.
```

---

### 4. Epics & Issues

#### Epic E7-v3: wiki-extract-concepts deterministic refactor (v3.1)

- **I-V3.1** Refactor `scripts/wiki_skills/wiki_extract_concepts.py` into argparse subparsers with `required=True`. Delete `extract_concepts_llm()`, `_build_extraction_prompt()`, `LLMUnavailableError`. Add `prepare(args) -> int` and `apply(args) -> int`. Remove `import anthropic`. **Hardening**: implement `_validate_candidates_schema` strict mode + count bound + per-field caps; `_MAX_SOURCE_BODY_BYTES` + `_MAX_CANDIDATES_BYTES`; `--source-hash` required on apply + mismatch detection; `--candidates-file` validate-inside-vault; markdown body sanitization in `write_concept_page` (sanitize `name`, escape `definition`, blockquote `source_quote`); content-hash skip in `write_concept_page`; `--orchestrator-id` flag + regex validation. Preserve all other v2 helpers verbatim. Error envelopes never echo offending content. → R-30(c), R-31, R-33′, R-36, R-37, R-39, R-42, R-43

- **I-V3.2** Create `.agent/skills/concept-extraction/SKILL.md` with: extraction prompt, JSON candidates contract (strict schema, count bound, per-field caps documented). Top-of-file banner: **"SECURITY-SENSITIVE: modifications require code review and security audit. This file's content is loaded into LLM context at runtime; tampering enables stored prompt injection."** Symlinks into `skills/concept-extraction/` and `.claude/skills/concept-extraction/`. → R-33′, R-34, M-4

- **I-V3.3** Create `workflows/wiki-extract-concepts.md` with 6-step orchestrator workflow (prepare → check is_unchanged → load skill → Read source → synthesize → apply with `--source-hash`). Symlink into `.agent/workflows/`. Update `.claude/commands/wiki-extract-concepts.md` to delegate. → R-30(b), H-1

- **I-V3.4** Rewrite `skills/wiki-extract-concepts/SKILL.md`: workflow + subcommand surface, exit-code table 0/1/2/4/5/6 with new sub-envelopes, **prominent BREAKING CHANGE notice at top** (legacy CLI invocation no longer supported). Sync copies in `.agent/skills/` and `.claude/skills/`. → R-30(a), H-4

- **I-V3.5** Remove `anthropic>=0.34.0` from `requirements.txt`. → R-30

- **I-V3.6** Refactor `tests/test_wiki_extract_concepts.py`: delete 12 LLM-mock tests (enumerated in v3.0 spec). Add ~14 new tests:
  - **Prepare** (6): happy path, source-not-found, invalid-slug, idempotency match, idempotency mismatch, **source-too-large stat-cap (M-3)**
  - **Apply** (4): canned JSON happy, --candidates-stdin vs --candidates-file mutex, end-to-end with --ingest mocked dispatch, **--source-hash mismatch → exit 2 SOURCE_CHANGED (H-1)**
  - **Adversarial** (4): **per-field cap rejection (definition=5MB → FIELD_TOO_LONG, H-6)**, **unknown-field rejection (extra key → UNKNOWN_FIELD, H-9)**, **candidate-count bound (empty array → CANDIDATE_COUNT_OUT_OF_BOUNDS; 26 items → same, H-2)**, **candidates-file outside vault → INVALID_CANDIDATES_PATH (H-5)**, **markdown injection (name="\n## Backdoor" → sanitized to safe form, H-7)**, **YAML injection (name="---" → frontmatter still parseable, H-7)**, **error envelope content-leak audit (each adversarial test asserts envelope does NOT contain offending content)**.

  Net: 57 − 12 + ~14 = **~59 tests in this file**. → R-43

- **I-V3.7** Refactor `tests/test_wiki_extract_concepts_integration.py`: drop anthropic mocks; canned candidates JSON fixture (`tests/fixtures/source_extract/candidates.json`); 3 scenarios (first / unchanged / --ingest) via prepare+apply subcommand split. → R-43

- **I-V3.8** Update `docs/ARCHITECTURE.md` per architecture-reviewer's pre-flagged edit sites (§2.1 strip LLM refs + add subcommand description + exit-code table 0/1/2/4/5/6 + sub-envelope list; §3.4 sequence diagram step [3]; status header v3.1 ship state; new "Why deterministic" subsection referencing Decision-17). → R-30, R-33′, R-42

- **I-V3.9** Update `docs/ROADMAP.md` (R-3 v3 entry with BREAKING CHANGE call-out per H-4). Update `docs/KNOWN_ISSUES.md`: mark L-V3.3 obsolete; add **P-6** (known_concepts payload O(N) per call, SEV-2); add **P-7** (no batch surface for N-source-page workflows, SEV-2); add **P-8** (WAL PRAGMA setup cost doubled by two-process `prepare`+`apply` workflow vs v2's single process, SEV-3 — iteration-2 perf finding); add **P-9** (`missing_concept_files` O(N) stat sweep at Karpathy scale, SEV-3 — iteration-2 perf finding; future bead: lazy-via-flag or SQL-JOIN). Also add nit row: `SOURCE_NOT_FOUND` vs `INVALID_SOURCE_PATH` info-disclosure oracle (iteration-2 security NEW-3 — operator-trust scope, future hardening if multi-tenant). → housekeeping + performance + security findings

- **I-V3.10** Dogfood smoke on `trade-agents` vault per §7. Includes legacy-invocation breaking-change smoke (H-4): `bin/wiki-extract-concepts --vault X --source-page Y` (no subcommand) → argparse error with help text pointing to `prepare`/`apply`. → R-43

- **I-V3.11** Regression sweep: `pytest tests/ -q` reports **~398 passed** (corrected per H-3). `mypy --strict scripts/` clean. Confirm `bin/wiki-extract-concepts prepare --help` + `bin/wiki-extract-concepts apply --help` route correctly. Retire SDK-metadata deep-sweep deferred item from KNOWN_ISSUES (moot post-v3). → R-43

- **I-V3.12** (NEW) Adversarial smoke-test bench in `tests/test_wiki_extract_concepts.py`: dedicated section asserting all error envelopes from `apply` validation failures emit `{error: <CODE>, field: <field_name>, reason: <human-readable>}` shape with NO `content`, `value`, `raw`, `received` keys (CWE-117 / CWE-209 regression guard). One parametrized test covering all sub-envelopes from R-42(c) + R-42(d). → R-42, H-5/H-6/H-9

- **I-V3.13** (NEW) Content-hash skip semantics in `write_concept_page` + regression tests: existing file + same-content → return path + log `skipped (unchanged)`; existing file + diff-content → rewrite atomically + log `updated (content changed)`; existing file + same-content but different sha256 algorithm metadata (edge case: schema migration) → rewrite. Test fixture seeds a stale `_concepts/<slug>.md`, runs apply with different `definition`, asserts file is rewritten and `action="updated"` propagates into manifest. → C-1, R-36

---

### 5. Use Cases

#### 5.1 UC-08 (v3.1) — Extract concepts (orchestrator-driven, hardened)

**Preconditions:**
- Vault registered. Source page indexed. Calling agent has Read + Bash. `concept-extraction` skill loadable.

**Main Scenario (without `--ingest`):**

1. Operator invokes `/wiki-extract-concepts --vault trade-agents --source-page X`.
2. Calling agent reads `workflows/wiki-extract-concepts.md`.
3. **Calling agent calls `wiki-extract-concepts prepare`** → JSON: `{source_path, source_hash, is_unchanged: false, known_concepts: [...], missing_concept_files: []}`.
4. If `is_unchanged=true`, emit unchanged envelope and stop.
5. Otherwise: `Skill({skill: "concept-extraction"})` loads contract.
6. Agent `Read(source_path)` — reads source body.
7. Agent synthesizes 1–25 candidates per strict schema in own context. Emits JSON array.
8. Agent pipes to apply:
   ```bash
   echo '[{...}, {...}]' | wiki-extract-concepts apply \
     --vault trade-agents --vault-root /path --source-page X \
     --source-hash <hash-from-prepare> --candidates-stdin \
     --orchestrator-id "claude-opus-4-7"
   ```
9. `apply` validates strict schema; recomputes source_hash; rejects on mismatch → exit 2. Otherwise: classifies → writes pages (content-hash skip) → upserts → manifest → updates source_state → emits manifest JSON.

**Alternative scenarios (v3.1 new):**

- **A6: Operator edits source between prepare and apply** → apply detects hash mismatch → exit 2 `SOURCE_CHANGED_DURING_EXTRACTION`; operator re-runs prepare.
- **A7: Agent emits 0 or 26+ candidates** → exit 4 `CANDIDATE_COUNT_OUT_OF_BOUNDS`.
- **A8: Agent emits 10MB `definition` field** → exit 4 `FIELD_TOO_LONG` (field=`definition`, no content echo).
- **A9: Agent emits extra key `model="evil-llm"` in candidate** → exit 4 `UNKNOWN_FIELD` (strict mode).
- **A10: Operator passes `--candidates-file /etc/passwd`** → exit 2 `INVALID_CANDIDATES_PATH` (validate_inside_vault fail); envelope emits path string only, no file content.
- **A11: Operator passes `--candidates-file ./candidates.json` where file is 5GB** → exit 4 `CANDIDATES_TOO_LARGE` before any parse.
- **A12: Agent emits `name="\n## Backdoor\n\nMalicious instructions"`** → sanitization strips `\n## ` pattern; concept page body has `# X` header only (no injection); regression test asserts.
- **A13: Existing `_concepts/X.md` file present from prior incomplete run** → `write_concept_page` content-hash check: identical → skip + manifest `action="unchanged"`; different → rewrite + manifest `action="updated"`. C-1 drift eliminated.

#### 5.2 UC-09 (v3.1) — Re-extract on unchanged body (idempotency)

Same as v3.0 — short-circuit at orchestrator level after `prepare` returns `is_unchanged=true`. No LLM call. No apply needed.

---

### 6. Schema and API Impact + BREAKING CHANGE notice

**No schema changes.** All v2 schema work preserved.

**API changes — BREAKING CHANGE for operators (H-4):**

> ⚠️ **BREAKING CHANGE — operator-facing CLI surface**
>
> v2: `wiki-extract-concepts --vault X --vault-root P --source-page Y [--ingest]`
> v3: `wiki-extract-concepts prepare ...` AND `wiki-extract-concepts apply ...`
>
> Legacy invocation (no subcommand) → argparse error with help text directing operator to new subcommand surface. **Every existing script, shell alias, agent prompt, or muscle-memory invocation using the v2 form will break.** Migration is straightforward (run prepare, then apply with `--source-hash`), but it is not transparent. Operators MUST update their workflows.

**Removed CLI flags**: `--model`, `--max-tokens`.
**Added CLI flags** (on `apply`): `--candidates-file PATH | --candidates-stdin` (mutex), `--source-hash HEX` (REQUIRED), `--orchestrator-id STRING` (optional).
**Removed exit code**: 3 (LLM_API_UNAVAILABLE).
**Added exit-2 sub-envelopes**: `SOURCE_TOO_LARGE`, `SOURCE_CHANGED_DURING_EXTRACTION`, `INVALID_CANDIDATES_PATH`.
**Added exit-4 sub-envelopes**: `CANDIDATES_TOO_LARGE`, `CANDIDATE_COUNT_OUT_OF_BOUNDS`, `FIELD_TOO_LONG`, `UNKNOWN_FIELD`, `FIELD_QUOTE_NOT_IN_BODY`.

**Cross-module changes**: none. `_manifest_consumer.py` interface unchanged. `wiki_enrich.py` unchanged.

**Python deps**: `anthropic>=0.34.0` removed.

---

### 7. Acceptance Criteria (E2E Smoke, v3.1 — hardened)

```bash
source .venv/bin/activate
export VAULT=trade-agents
export VAULT_ROOT=/path/to/trade-agents
export DB=/tmp/dogfood-v3.db

# === Core happy path ===

# 1. Vault registered + source page indexed (one-time setup; see I-V3.10 docs)

# 2. prepare
wiki-extract-concepts prepare --vault $VAULT --vault-root $VAULT_ROOT \
  --source-page some-summary --db-path $DB > /tmp/prepare.json

python -c "
import json
p = json.load(open('/tmp/prepare.json'))
assert p['is_unchanged'] is False
assert 'source_hash' in p
assert isinstance(p.get('missing_concept_files', []), list)
print('Prepare OK; source_hash=', p['source_hash'][:16])
"

# 3. Operator synthesizes candidates (smoke uses canned)
SOURCE_HASH=$(python -c "import json; print(json.load(open('/tmp/prepare.json'))['source_hash'])")
cat > /tmp/candidates.json <<'EOF'
[{"slug":"sample-concept","name":"Sample Concept","definition":"Demo.",
  "source_quote":"this is a sample concept extracted from the source body",
  "source_span":"L5-L7","entity_type":"concept"}]
EOF

# 4. apply with required --source-hash
wiki-extract-concepts apply --vault $VAULT --vault-root $VAULT_ROOT \
  --source-page some-summary --candidates-file /tmp/candidates.json \
  --source-hash $SOURCE_HASH --orchestrator-id "smoke-test" --db-path $DB

# === Adversarial smokes (H-1, H-2, H-5, H-6, H-7, H-9) ===

# 5. H-1: source hash mismatch
wiki-extract-concepts apply --vault $VAULT --vault-root $VAULT_ROOT \
  --source-page some-summary --candidates-file /tmp/candidates.json \
  --source-hash deadbeef --db-path $DB 2>&1 | \
  grep -q SOURCE_CHANGED_DURING_EXTRACTION && echo "H-1 OK"

# 6. H-2: empty candidates → exit 4 CANDIDATE_COUNT_OUT_OF_BOUNDS
echo '[]' | wiki-extract-concepts apply --vault $VAULT --vault-root $VAULT_ROOT \
  --source-page some-summary --candidates-stdin --source-hash $SOURCE_HASH 2>&1 | \
  grep -q CANDIDATE_COUNT_OUT_OF_BOUNDS && echo "H-2 OK"

# 7. H-5: --candidates-file outside vault → exit 2 INVALID_CANDIDATES_PATH
wiki-extract-concepts apply --vault $VAULT --vault-root $VAULT_ROOT \
  --source-page some-summary --candidates-file /etc/passwd \
  --source-hash $SOURCE_HASH 2>&1 | grep -q INVALID_CANDIDATES_PATH && echo "H-5 OK"

# 8. H-6: per-field cap → exit 4 FIELD_TOO_LONG
python -c "
import json
huge = 'x' * 5000  # > 2000 cap
print(json.dumps([{'slug':'x','name':'X','definition':huge,
                   'source_quote':'q','source_span':'L1-L2','entity_type':'concept'}]))
" | wiki-extract-concepts apply --vault $VAULT --vault-root $VAULT_ROOT \
    --source-page some-summary --candidates-stdin --source-hash $SOURCE_HASH 2>&1 | \
  grep -q FIELD_TOO_LONG && echo "H-6 OK"

# 9. H-7: markdown sanitization — name containing newline+header escapes safely
python -c "
import json
print(json.dumps([{'slug':'x','name':'X\n## Backdoor','definition':'d',
                   'source_quote':'q','source_span':'L1-L2','entity_type':'concept'}]))
" | wiki-extract-concepts apply --vault $VAULT --vault-root $VAULT_ROOT \
    --source-page some-summary --candidates-stdin --source-hash $SOURCE_HASH \
    --db-path $DB > /dev/null
grep -c "^## Backdoor" $VAULT_ROOT/_concepts/x.md  # Expect: 0 (sanitized)
echo "H-7 OK"

# 10. H-9: unknown field strict-mode rejection
python -c "
import json
print(json.dumps([{'slug':'x','name':'X','definition':'d','source_quote':'q',
                   'source_span':'L1-L2','entity_type':'concept',
                   'model':'evil-llm'}]))
" | wiki-extract-concepts apply --vault $VAULT --vault-root $VAULT_ROOT \
    --source-page some-summary --candidates-stdin --source-hash $SOURCE_HASH 2>&1 | \
  grep -q UNKNOWN_FIELD && echo "H-9 OK"

# 11. H-4: legacy invocation surfaces helpful error
wiki-extract-concepts --vault $VAULT --source-page Y 2>&1 | grep -qE "prepare|apply" \
  && echo "H-4 OK: legacy invocation shows subcommand help"

# === Invariants ===

# 12. NO anthropic env vars
env | grep -i anthropic && echo "FAIL" || echo "OK: no anthropic env"

# 13. NO anthropic dep
grep anthropic requirements.txt && echo "FAIL" || echo "OK: anthropic dep removed"

# 14. Subcommand help routes correctly (H-4 cont.)
bin/wiki-extract-concepts prepare --help | grep -q "source-page" && echo "OK: prepare help routes"
bin/wiki-extract-concepts apply --help | grep -q "source-hash" && echo "OK: apply help routes"

# 15. Idempotency: re-run prepare with same body → is_unchanged=true
wiki-extract-concepts prepare --vault $VAULT --vault-root $VAULT_ROOT \
  --source-page some-summary --db-path $DB | \
  python -c "import json,sys; p=json.load(sys.stdin); assert p['is_unchanged'] is True"
echo "OK: idempotency"

# 16. Error envelope content-leak audit
# (run a synthetic test that triggers each exit-4 sub-envelope, assert envelope JSON
#  does NOT contain keys: 'content', 'value', 'raw', 'received')

# 17. Full test suite
pytest tests/ -q  # Expect: ~398 passed (was 396; net +2)

# 18. mypy
mypy --strict scripts/
```

---

### 8. Resolved Decisions (v3.1)

| Q | Resolution | Encoded in |
|---|---|---|
| **Q1 — Why now?** | Dogfood revealed architectural inconsistency. | Decision-17 |
| **Q2 — Pattern A vs B vs C?** | Pattern B (deterministic skill + orchestrator synthesis). | Decision-17 |
| **Q3 — Subagent vs inline orchestrator synthesis?** | Inline orchestrator. | Decision-17 |
| **Q4 — `prepare` returns `source_body`?** | No, returns `source_path` only. | Decision-17 |
| **Q5 — `apply` recomputes hash from disk?** | **REWRITTEN (H-1)**: `apply` REQUIRES `--source-hash <HEX>` from orchestrator (sourced from prepare). Apply re-reads source from disk, recomputes hash, compares against `--source-hash`. **Mismatch → exit 2 `SOURCE_CHANGED_DURING_EXTRACTION`** (operator re-runs prepare). No silent corruption. | I-V3.1 + H-1 |
| **Q6 — Top-level metadata on candidates JSON (model, extracted_at)?** | No. Candidates JSON is just `[{...}]` array; `extracted_at` set by apply (`datetime.now(timezone.utc)`); `model` derived from `--orchestrator-id` flag (Q9). | I-V3.1 |
| **Q7 — Keep `summarizing-meetings` integration?** | Out of scope. | n/a |
| **Q8 — TOCTOU between prepare and apply?** | **REWRITTEN (H-1)**: see Q5. `--source-hash` makes the race explicit and fail-fast. Original v3.0 framing ("desired UX") was wrong — silently-corrupted provenance is never desired UX. | I-V3.1 + H-1 |
| **Q9 — `canonicalized_by` model field?** | **REWRITTEN (H-8)**: `apply` accepts optional `--orchestrator-id <STRING>` (regex `^[a-z0-9._:@-]{1,64}$`). Populates `canonicalized_by = f"llm:{orchestrator_id}@{date}"`. Defaults to literal `"orchestrator"` if absent. Operator who cares about audit trail passes their model name (e.g., `"claude-opus-4-7"`); honest unknown when absent. | I-V3.1 + H-8 |
| **Q10** (NEW from H-2) — **Candidate count bound?** | `1 ≤ N ≤ 25`. Empty array OR > 25 → `CANDIDATE_COUNT_OUT_OF_BOUNDS`. Enforced in `_validate_candidates_schema`. | I-V3.1, R-33′ |
| **Q11** (NEW from H-5) — **`--candidates-file` path validation?** | `validate_inside_vault(candidates_path, vault_root)` REQUIRED. Outside-vault path → `INVALID_CANDIDATES_PATH` (exit 2). `--candidates-stdin` documented as preferred external-transport path. | I-V3.1, R-31 |
| **Q12** (NEW from H-6) — **Per-field size caps?** | `name ≤ 200`, `definition ≤ 2000`, `source_quote ≤ 500` chars. Total candidates JSON ≤ 1 MiB (`_MAX_CANDIDATES_BYTES`). Violation → `FIELD_TOO_LONG` or `CANDIDATES_TOO_LARGE` (exit 4). Envelope does NOT echo offending field content. | I-V3.1, R-33′ |
| **Q13** (NEW from H-7) — **Markdown / YAML injection defense?** | `name` regex-allowlist `^[\w\s\-.,:;()\'"!?]{1,200}$` (with `re.UNICODE` flag for international vault contents per iteration-2 logic N-5) + strip leading `#`/`---`; `definition` markdown-escape (escape HTML tags + `\n## ` pattern); `source_quote` wrapped in `>` blockquote (not inline double-quotes); **`source_span` strict regex `^L\d+-L\d+$` (already enforced by `_parse_source_span`, but explicitly listed here per iteration-2 security NEW-1 since the `Mentions` body embeds it raw)**. YAML frontmatter via `frontmatter.dumps`'s safe_dump; adversarial regression tests for `name="---"`, `name="key: value"`, `name="\n- list-item"`, `name="Свидетель"` (Cyrillic — iteration-2 N-5), and `source_span="L1-L2)]] [[evil"` (wikilink-target attack — iteration-2 NEW-1). | I-V3.1 + I-V3.6 |
| **Q14** (NEW from H-9) — **Strict-mode schema (no extra keys)?** | `_validate_candidates_schema` enforces equality (`item.keys() == _REQUIRED_CANDIDATE_KEYS`), not subset. Extra keys → `UNKNOWN_FIELD` (exit 4). Prevents future regression where developer accidentally accepts agent-supplied `canonicalized_by`, `model`, etc. | I-V3.1, R-33′ |
| **Q15** (NEW from C-1) — **`write_concept_page` skip-on-exists?** | Content-hash skip: compute sha256 of existing file vs. sha256 of would-be-written content. Identical → skip with `action="unchanged"`. Different → REWRITE atomically with `action="updated"` and log warning. **`if target.is_symlink(): raise PathTraversalError("concept page is a symlink — refuse to rewrite")` BEFORE the read** (iteration-2 security NEW-2 — eliminates symlink-following info leak on the hash-compute step + write-to-attacker-controlled-target risk). Eliminates disk/DB drift after partial-failure replay (C-1). | I-V3.13, R-36 |

| **Q16** (NEW from iteration-2 perf) — **`missing_concept_files` O(N) stat sweep at Karpathy scale (10k entities)?** | Acknowledged as SEV-3 perf concern (P-NEW-1 from iteration-2). For trade-agents-scale (~100 entities) cost is ~10ms; at 10k entities approaches 1000ms per `prepare` invocation. Mitigation deferred to **KNOWN_ISSUES P-9** (lazy via `--check-drift` flag OR SQL-JOIN against materialized manifest). Spec keeps the eager check in v3.1; future bead converts to lazy. Cost named on the tin. | I-V3.9 + KNOWN_ISSUES P-9 |

| **Q17** (NEW from iteration-2 security NEW-3) — **Information-disclosure oracle via `SOURCE_NOT_FOUND` vs `INVALID_SOURCE_PATH` differentiation?** | Acknowledged. Practical impact tiny (slugs are operator-known, vault structure is operator-trusted). Defer collapse to single `SOURCE_NOT_FOUND` envelope as future hardening; current spec retains both codes for diagnostic clarity (`INVALID_SOURCE_PATH` = absolute path attempted; `SOURCE_NOT_FOUND` = relative path doesn't resolve). Operator-trust scope, not multi-tenant. Documented as KNOWN_ISSUES nit; not blocking. | KNOWN_ISSUES nit |

**Status**: Analysis Phase v3.1 complete. **`/vdd-multi` iteration-1**: 1 CRITICAL + 8 HIGH addressed inline. **`/vdd-multi` iteration-2**: logic=clean-pass · security=issues-found (1 MED + 2 LOW residual, all folded into Q13/Q15/Q17) · performance=clean-pass (2 SEV-3 deferred to KNOWN_ISSUES P-8/P-9). **Net residual**: 0 CRITICAL · 0 HIGH · 0 MED post-fold · 4 LOW deferred or scoped (NEW-2 symlink check folded into Q15; NEW-3 oracle Q17; logic N-5 unicode folded into Q13; logic N-3 cross-skill ownership → KNOWN_ISSUES). Ready for planner.

---

### 9. Task-Review Self-Checklist (v3.1)

- [x] Every active RTM row has at least one Issue; R-33 retirement explicit; R-33′ supersession clean.
- [x] No RTM orphans.
- [x] UC-08 v3.1 covers main path + new adversarial alternatives (A6–A13).
- [x] Decision-17 unchanged. Q5/Q8/Q9 rewritten to address H-1/H-8. Q10–Q15 added for H-2/H-5/H-6/H-7/H-9.
- [x] No contradiction with v2 ship state for unrelated areas.
- [x] Scope (out) explicitly calls out deferred items.
- [x] Loss-of-capability (cron) acknowledged. NEW: explicit BREAKING-CHANGE for operator CLI surface (H-4).
- [x] Pytest target corrected: ~398 (was: "390+" in v3.0). Math verified via `pytest --collect-only`.
- [x] Adversarial regression tests catalogued in I-V3.6 + I-V3.12 + I-V3.13.
- [x] All error envelopes specified as NEVER-echo-content (CWE-117/CWE-209 regression guards in I-V3.12).
- [x] `concept-extraction/SKILL.md` flagged security-sensitive (M-4); modifications require review.
- [x] Performance findings (P-1 batch surface, P-2 known_concepts payload growth) added to KNOWN_ISSUES via I-V3.9.
- [x] BREAKING CHANGE notice present in §6, I-V3.4, I-V3.9, I-V3.10 (legacy-invocation smoke).
