# Development Plan: TASK 003 v3.1 — wiki-extract-concepts deterministic refactor

> **Status**: DRAFT (v3.1) — 2026-05-28; awaiting plan-reviewer sign-off.
> **Task ID**: 003 v3.1 / Slug: `wiki-extract-concepts`
> **Source spec**: [docs/TASK.md](./TASK.md) — TASK 003 v3.1; Decision-17; Q1–Q17; active RTM R-30/R-31/R-32/R-33′/R-34/R-35/R-36/R-37/R-38/R-39/R-40/R-41/R-42/R-43 (retired: R-33, R-44); Issues I-V3.1..I-V3.13; UC-08 v3.1 (main + A6–A13); UC-09 v3.1; smoke recipe §7 (18 steps).
> **Architecture spec**: [docs/ARCHITECTURE.md](./ARCHITECTURE.md) §2.1 Concept Extractor (v3.1 target architecture — **already updated** in analysis phase); §3.4 UC-08 sequence diagram (v3.1 target — **already updated**); status header. **No further architecture work in this plan** — I-V3.8 becomes a drift-verification bead.
> **Methodology**: **Stub-First (TDD)**. Code-bearing beads land in two passes — Phase 1 stubs + tests (Red→Green on stubs), Phase 2 logic. Documentation-only beads (I-V3.2, I-V3.3, I-V3.4, I-V3.5, I-V3.9) skip Phase 1. Verification-only beads (I-V3.8, I-V3.10, I-V3.11) run direct checks.
>
> **Option A green-throughout invariant** (decided 2026-05-28 adversarial review): test-suite stays ≥ 390 between any two bead boundaries, NOT ≥ 396 as originally claimed. The original 396 floor was unachievable because 003-v3-00's `add_subparsers(required=True)` change breaks 6 legacy-shape `main([... legacy args ...])` tests. The fix splits the test-refactor scope into **003-v3-11a** (Phase -1; deletes the 6 legacy-shape tests pre-subparser) and **003-v3-11** (Phase 3; deletes the 9 remaining anthropic-mock function tests). Regression intent for the 6 deleted tests (H-1, H-3, C-1, ingest e2e, no-ingest manifest, help-text-flags) is migrated to Phase-1 beads 003-v3-00/01/03.
> **Predecessor**: TASK 003 v2 — **SHIPPED** 2026-05-28 (15 beads, 396 pytest passed, mypy --strict clean on 55 files). v2 deterministic infrastructure (page writer, entity upsert with SQL downgrade-guard, refs upsert, idempotency gate, manifest builder, in-process indexer dispatch) preserved verbatim except for two narrow changes (C-1 content-hash skip in `write_concept_page`; H-8 `--orchestrator-id` plumbing through `upsert_extracted_entity`).
> **Out of scope (carried forward from TASK.md §1.2 / §1.3)**: `--llm-standalone` Pattern-C escape hatch; subagent-spawn pattern; `status` subcommand (M-6 YAGNI gate); batch N-source-page surface (P-1, P-7); hash-pinning of `concept-extraction/SKILL.md`; `summary` page type CHECK constraint; backward-compat alias for `extract_concepts_llm()` (internal helper, clean delete); backward-compat for v2's monolithic CLI invocation (BREAKING CHANGE — H-4); `--known-concepts-format=slugs-only` (P-2).

---

## 0. Architectural Foundation (Reference)

| Layer | Owns | Class (ADR-002 §D8) | v3.1 changes |
|---|---|---|---|
| `scripts/wiki_skills/_manifest_consumer.py` (neutral module from v2 I-7.0) | `validate_manifest`, `index_from_manifest`, `WikiIngestError` | Glue (sub-layer below skills) | **Unchanged.** |
| `scripts/wiki_skills/wiki_enrich.py` (back-compat re-export) | Re-exports the three symbols + `_validate_manifest` alias | Class A producer (raw-source synthesis path) | **Unchanged.** |
| `scripts/wiki_skills/wiki_extract_concepts.py` (skill entry-point) | Argparse with `subparsers(required=True)`, `prepare` + `apply` subcommands, strict validator, concept-page writes (content-hash skip), manifest emission, optional in-process dispatch | Class A producer (derivative-page synthesis path) | **REFACTORED.** Delete `extract_concepts_llm` + `_build_extraction_prompt` + `LLMUnavailableError` + `import anthropic`. Add `prepare()` + `apply()` entry-point functions. Add `_validate_candidates_schema` (strict mode + count bound + per-field caps). Add `_MAX_SOURCE_BODY_BYTES` (10 MiB) + `_MAX_CANDIDATES_BYTES` (1 MiB) caps. `write_concept_page` content-hash skip + markdown sanitization + symlink refuse. `upsert_extracted_entity` accepts `orchestrator_id`. |
| `skills/wiki-extract-concepts/SKILL.md` (existing) | Operator-facing CLI invocation guide | Class A docs | **REWRITTEN.** Documents `prepare`/`apply` subcommand surface + BREAKING CHANGE notice + exit codes 0/1/2/4/5/6 with new sub-envelopes. |
| `.agent/skills/concept-extraction/SKILL.md` (**NEW**) | Operator-facing extraction prompt + JSON candidates contract | Class A docs (security-sensitive — banner per M-4) | **NEW.** Symlinks into `skills/concept-extraction/` and `.claude/skills/concept-extraction/`. |
| `workflows/wiki-extract-concepts.md` (**NEW**) | Step-by-step orchestrator workflow (prepare → check is_unchanged → load skill → Read source → synthesize → apply with --source-hash) | Class A docs | **NEW.** Symlinks into `.agent/workflows/`. |
| `requirements.txt` | Python deps | Tooling | **CHANGED.** Remove `anthropic>=0.34.0`. |
| `IndexRepository` + `SQLiteRepository` | DAL | Class B (cache) | **Unchanged.** v2's `upsert_entity` ABC + concrete is preserved as-is. |
| `entities`, `entity_aliases`, `page_entity_refs`, `source_state` | Schema rows | Class B (cache) | **Unchanged.** No DDL changes. |

**TASK 003 v3.1 invariants** (carried forward + new — Option A revised 2026-05-28):

- **Suite floor**: `pytest tests/ -q ≥ 390` between any two bead boundaries (NOT ≥ 396 as originally claimed — that floor required impossible intra-bead atomicity; see §6 R-2 and §3 Option A note).
- **Bead atomicity**: 1 bead = 1 commit = 1 pytest gate. No intra-bead commit interleaving permitted.
- No new DB tables; no schema changes (R-43 / §6 / §1.3 non-goal).
- `wiki_enrich.py` argparse surface **unchanged** — no new `--manifest-*` flags (Decision-15).
- `_manifest_consumer.py` interface unchanged.
- No cross-skill imports — `wiki_extract_concepts` imports from `_manifest_consumer`, not from `wiki_enrich` (Decision-16).
- **Patch-target lock (v2 R-2 carried forward)**: all `unittest.mock.patch(...)` sites that touch `wiki_extract_concepts` module's bound names must patch `scripts.wiki_skills.wiki_extract_concepts.<symbol>` (the bound name), NOT `scripts.wiki_skills._manifest_consumer.<symbol>` (the source).
- `vault_id` predicate on every entity / ref / source_state query (ADR-002 §D1.1).
- All R-3 entity rows written with `is_candidate=1`; promotion (R-4) is deferred.
- **NEW (v3.1)**: error envelopes never echo offending field content (CWE-117 / CWE-209 regression guards in I-V3.12).
- **NEW (v3.1)**: `_concepts/<slug>.md` symlinks refused before any hash-compute or write (Q15 symlink check).

---

## 1. Task Execution Sequence

### Phase -1 — Pre-subparser test hygiene (Option A green-throughout enablement)

The single bead of this phase clears the 6 legacy-shape `main()` tests that would otherwise fail under 003-v3-00's argparse change. It is a pure test-file deletion; no production code touched. **Regression intent for every deleted test is migrated to a TODO marker** pointing at the Phase-1 bead that re-asserts the behaviour via the new `prepare`/`apply` surface.

- [R-43] [I-V3.6a] **Delete the 6 legacy-shape `main()` tests** in `tests/test_wiki_extract_concepts.py`: `test_argparse_help_text_contains_ingest_flag` (line 36), `test_main_rejects_absolute_source_page_path` (H-1, line 458), `test_main_rejects_invalid_source_slug` (H-3, line 486), `test_main_ingest_partial_failure_does_not_update_source_state` (C-1, line 522), `test_main_with_ingest_calls_dispatch_and_emits_combined` (line 1071), `test_main_without_ingest_emits_manifest_only` (line 1140). The surviving `test_argparse_missing_vault_returns_exit` (line 28) is preserved (it asserts only SystemExit(2), which still holds under subparsers-required). Insert TODO markers referencing migration targets in 003-v3-00 / 003-v3-01 / 003-v3-03. Net delta: −6 tests. Suite drops from 396 to 390 (green).
  - Description File: [docs/tasks/task-003-v3-11a-delete-legacy-main-tests.md](./tasks/task-003-v3-11a-delete-legacy-main-tests.md)
  - Priority: Critical (blocks 003-v3-00)
  - Dependencies: none (first bead overall)
  - Estimated time: 0.25 day

### Phase 0 — Argparse subparser scaffold (PRECONDITION — blocks Phase 1 logic)

**The only bead in this phase. It blocks every code-bearing v3.1 bead** so all subsequent logic targets a clean two-subcommand structure from the outset.

- [R-30] [I-V3.1a] Add argparse subparsers (`prepare` + `apply`) with `add_subparsers(dest="cmd", required=True)`. Wire `main(argv)` to dispatch on `args.cmd`. Add stub `prepare(args) -> int` and `apply(args) -> int` that each `raise NotImplementedError("task-003-v3-NN")`. Operator who runs `wiki-extract-concepts --vault X --source-page Y` (no subcommand) now gets argparse error pointing at `prepare`/`apply` — this IS the BREAKING CHANGE (H-4). Update unit tests minimally: add E2E test `test_argparse_no_subcommand_returns_helpful_error` (Red→Green); add E2E test `test_argparse_prepare_subparser_exists` + `test_argparse_apply_subparser_exists` + `test_main_dispatches_to_prepare_stub` + `test_main_dispatches_to_apply_stub` + `test_argparse_top_level_help_shows_subcommands` (replacement for the help-text test deleted in 11a). Rename surviving `test_argparse_missing_vault_returns_exit` → `test_argparse_no_args_returns_exit_2` (mechanical, since the cause of SystemExit(2) is now "missing required subcommand" not "missing --vault"). Do NOT delete the LLM-call functions yet (preserved for backward compatibility with the 9 remaining anthropic-mock function tests until Phase 2 bead 003-v3-06).
  - Description File: [docs/tasks/task-003-v3-00-argparse-subparser-scaffold.md](./tasks/task-003-v3-00-argparse-subparser-scaffold.md)
  - Priority: Critical (blocks every Phase-1 logic bead)
  - Dependencies: **task-003-v3-11a** (legacy-shape tests must be cleared first)
  - Estimated time: 0.5 day

### Phase 1 — Subcommand logic (sequential — each replaces a stub or extends the surface)

After 003-v3-00 lands, the subcommand logic fills in. Order is strict because `apply` consumes shape decided in `prepare`. The legacy `main()` body and `extract_concepts_llm()` remain in the module file until bead 003-v3-06 deletes them — this preserves a green test suite through Phase 1.

- [R-31, R-32, R-39, R-42] [I-V3.1b] Implement `prepare(args) -> int`: resolve `--source-page` (slug → relative path), validate inside vault, `stat().st_size` check against `_MAX_SOURCE_BODY_BYTES = 10_485_760` (M-3 / `SOURCE_TOO_LARGE` exit 2), read body, compute sha256, query `source_state` for `is_unchanged`, call `load_known_entities`, build `missing_concept_files` list (M-1 — disk vs DB drift sweep, eager O(N) in v3.1; P-9 deferred), emit JSON `{vault_id, source_slug, source_path, source_hash, is_unchanged, known_concepts, missing_concept_files}`. Add new tests: prepare happy-path, source-not-found, invalid-slug (**H-3 regression migration from 11a**), `INVALID_SOURCE_PATH` absolute (**H-1 regression migration from 11a**), idempotency match, `SOURCE_TOO_LARGE` stat-cap, `missing_concept_files` drift sweep. Net new tests: **+7** (gross), **−1** (drop the obsolete `test_main_dispatches_to_prepare_stub` from 003-v3-00) = **+6 net**.
  - Description File: [docs/tasks/task-003-v3-01-prepare-subcommand.md](./tasks/task-003-v3-01-prepare-subcommand.md)
  - Priority: Critical
  - Dependencies: task-003-v3-00
  - Estimated time: 0.75 day

- [R-33′, R-42] [I-V3.1c] Implement strict-mode `_validate_candidates_schema(items)`: rename from `_validate_extraction_schema`; enforce equality (`item.keys() == _REQUIRED_CANDIDATE_KEYS`) not subset → `UNKNOWN_FIELD` (H-9); enforce count bound `1 ≤ len(items) ≤ 25` → `CANDIDATE_COUNT_OUT_OF_BOUNDS` (H-2); enforce per-field caps `name ≤ 200`, `definition ≤ 2000`, `source_quote ≤ 500` → `FIELD_TOO_LONG` (H-6); preserve kebab slug regex, `Lstart-Lend` span, `entity_type` whitelist; envelope schema `{error, field, reason}` — NEVER echo offending content (CWE-117). Add new tests: per-field cap rejection, unknown-field rejection, count-bound (empty + 26 items). Net new tests: **+4**.
  - Description File: [docs/tasks/task-003-v3-02-strict-validator.md](./tasks/task-003-v3-02-strict-validator.md)
  - Priority: Critical (apply depends on the strict validator)
  - Dependencies: task-003-v3-00
  - Estimated time: 0.5 day

- [R-31, R-37, R-39, R-41, R-42] [I-V3.1d] Implement `apply(args) -> int`: argparse for `apply` adds `--candidates-file PATH | --candidates-stdin` (mutex), `--source-hash HEX` (REQUIRED), `[--ingest]`, `[--orchestrator-id STRING]`. Load candidates (with `_MAX_CANDIDATES_BYTES = 1_048_576` cap on file or stdin → `CANDIDATES_TOO_LARGE` exit 4); validate `--candidates-file PATH` via `validate_inside_vault` → `INVALID_CANDIDATES_PATH` exit 2 (H-5); re-read source from disk + recompute sha256 + compare against `--source-hash` → `SOURCE_CHANGED_DURING_EXTRACTION` exit 2 on mismatch (H-1, Q5); call `_validate_candidates_schema`; preserve v2 logic for classify → write concept pages → upsert entities + refs → manifest → optional dispatch. Update `source_state` AFTER manifest build, gated on `summary["failed"]` being empty when `--ingest` set. Add new tests: canned-JSON apply happy, stdin-vs-file mutex, **`--ingest` end-to-end mocked dispatch (regression migration from 11a)**, **without-`--ingest` manifest-only (regression migration from 11a)**, **`--ingest` partial failure → exit 5 / source_state NOT updated (C-1 regression migration from 11a)**, `--source-hash` mismatch → exit 2 SOURCE_CHANGED, candidates-file outside vault → INVALID_CANDIDATES_PATH (H-5), candidates payload > 1 MiB → CANDIDATES_TOO_LARGE, UNKNOWN_FIELD structured-envelope. Net new tests: **+9** (gross), **−1** (drop the obsolete `test_main_dispatches_to_apply_stub` from 003-v3-00) = **+8 net**.
  - Description File: [docs/tasks/task-003-v3-03-apply-subcommand.md](./tasks/task-003-v3-03-apply-subcommand.md)
  - Priority: Critical
  - Dependencies: task-003-v3-01 (prepare emits the `source_hash` apply consumes), task-003-v3-02 (apply calls the strict validator)
  - Estimated time: 1 day

- [R-36, R-40] [I-V3.1e + I-V3.13] Reshape `write_concept_page`: (1) **content-hash skip semantics (C-1)** — if file exists, compute sha256 of existing content vs. would-be-written content; identical → return `(target, "unchanged")`; different → atomic rewrite → return `(target, "updated")` + log warning; (2) **symlink refuse (Q15)** — `if target.is_symlink(): raise PathTraversalError(...)` BEFORE any read or hash-compute; (3) **markdown body sanitization (H-7 + Q13)** — `name` regex-allowlist `^[\w\s\-.,:;()\'"!?]{1,200}$` (with `re.UNICODE` flag per iteration-2 N-5) + strip leading `#`/`---`; `definition` markdown-escape (escape `\n## ` pattern + HTML tags); `source_quote` wrapped in `>` blockquote; `source_span` strict regex `^L\d+-L\d+$` (already enforced upstream, but body construction asserts) — eliminates inline-quote ambiguity, wikilink-target attack, YAML injection. Add adversarial regression tests: `name="\n## Backdoor"`, `name="---"`, `name="key: value"`, `name="\n- list-item"`, `name="Свидетель"` (Cyrillic), `definition="<script>alert(1)</script>"`, `source_span="L1-L2)]] [[evil"`, content-hash skip same-content (action=unchanged), content-hash skip diff-content (action=updated + rewrite), pre-existing-file-as-symlink → PathTraversalError. Net new tests: **+8**.
  - Description File: [docs/tasks/task-003-v3-04-markdown-sanitize.md](./tasks/task-003-v3-04-markdown-sanitize.md)
  - Priority: Critical
  - Dependencies: task-003-v3-00 (the helper has to remain importable through the refactor)
  - Estimated time: 0.75 day

- [R-37] [I-V3.1g] Implement `--orchestrator-id STRING` flag on `apply`: regex validation `^[a-z0-9._:@-]{1,64}$` (H-8); plumbing through `upsert_extracted_entity` so `canonicalized_by = f"llm:{orchestrator_id}@{date}"` where `orchestrator_id` defaults to literal `"orchestrator"` if absent. Add new tests: orchestrator_id valid → canonicalized_by populated, orchestrator_id invalid regex → argparse error, default omitted → `"orchestrator"`. Net new tests: **+3**.
  - Description File: [docs/tasks/task-003-v3-05-orchestrator-id-flag.md](./tasks/task-003-v3-05-orchestrator-id-flag.md)
  - Priority: High
  - Dependencies: task-003-v3-03 (apply argparse exists)
  - Estimated time: 0.25 day

- [R-30] [I-V3.1f] **Delete dead code** (now-safe after the new surface lands): remove `extract_concepts_llm()`, `_build_extraction_prompt()`, `LLMUnavailableError`, `_MAX_SOURCE_BODY_CHARS` (replaced by `_MAX_SOURCE_BODY_BYTES`), and `import anthropic`. Remove exit-3 (`LLM_API_UNAVAILABLE`) mapping from `main()`. Remove v2 legacy `main()` body (now superseded by subcommand dispatch from 003-v3-00). Update module docstring to reflect v3.1 surface. Net new tests: **-12** (the 12 LLM-mock tests deleted in lockstep — see 003-v3-11).
  - Description File: [docs/tasks/task-003-v3-06-delete-llm-call.md](./tasks/task-003-v3-06-delete-llm-call.md)
  - Priority: Critical (the actual deliverable of Decision-17 — must be LAST among Phase-1 code-bearing beads so the suite stays green throughout)
  - Dependencies: task-003-v3-00, task-003-v3-01, task-003-v3-02, task-003-v3-03, task-003-v3-04, task-003-v3-05 (all new logic landed), task-003-v3-11 (tests refactored to not use anthropic mocks)
  - Estimated time: 0.25 day

### Phase 2 — Documentation (parallel-safe with Phase 1)

- [R-33′, R-34] [I-V3.2] Create `.agent/skills/concept-extraction/SKILL.md` with extraction prompt (lifted verbatim from v2's `_build_extraction_prompt`), JSON candidates contract (strict schema, count bound `1 ≤ N ≤ 25`, per-field caps documented), example invocations. **Top-of-file banner**: "SECURITY-SENSITIVE: modifications require code review and security audit. This file's content is loaded into LLM context at runtime; tampering enables stored prompt injection." (M-4). Add symlinks: `skills/concept-extraction/SKILL.md` → `.agent/skills/concept-extraction/SKILL.md`; `.claude/skills/concept-extraction/SKILL.md` → same.
  - Description File: [docs/tasks/task-003-v3-07-concept-extraction-skill.md](./tasks/task-003-v3-07-concept-extraction-skill.md)
  - Priority: Medium (parallel)
  - Dependencies: none
  - Estimated time: 0.25 day

- [R-30, H-1] [I-V3.3] Create `workflows/wiki-extract-concepts.md` documenting the 6-step orchestrator workflow: (1) invoke `prepare`; (2) check `is_unchanged` short-circuit; (3) `Skill({skill: "concept-extraction"})`; (4) `Read(source_path)`; (5) synthesize candidates in own context per the contract; (6) invoke `apply` with `--source-hash` from prepare's output. Symlink into `.agent/workflows/`. Update `.claude/commands/wiki-extract-concepts.md` to delegate to the workflow.
  - Description File: [docs/tasks/task-003-v3-08-workflow-doc.md](./tasks/task-003-v3-08-workflow-doc.md)
  - Priority: Medium (parallel)
  - Dependencies: task-003-v3-00 (subcommand names finalised)
  - Estimated time: 0.25 day

- [R-30, H-4] [I-V3.4] Rewrite `skills/wiki-extract-concepts/SKILL.md`: subcommand surface (`prepare` + `apply` arguments table), exit-code table 0/1/2/4/5/6 with new sub-envelopes (`SOURCE_TOO_LARGE`, `SOURCE_CHANGED_DURING_EXTRACTION`, `INVALID_CANDIDATES_PATH`, `CANDIDATES_TOO_LARGE`, `CANDIDATE_COUNT_OUT_OF_BOUNDS`, `FIELD_TOO_LONG`, `UNKNOWN_FIELD`, `FIELD_QUOTE_NOT_IN_BODY`), **prominent BREAKING CHANGE banner at top** (legacy CLI invocation no longer supported — points to new surface). Sync copies in `.agent/skills/wiki-extract-concepts/SKILL.md` and `.claude/skills/wiki-extract-concepts/SKILL.md` via existing symlinks.
  - Description File: [docs/tasks/task-003-v3-09-skill-wrapper-rewrite.md](./tasks/task-003-v3-09-skill-wrapper-rewrite.md)
  - Priority: Medium
  - Dependencies: task-003-v3-03 (apply final argument set decided), task-003-v3-05 (--orchestrator-id arg)
  - Estimated time: 0.25 day

- [R-30] [I-V3.5] Remove `anthropic>=0.34.0` from `requirements.txt`.
  - Description File: [docs/tasks/task-003-v3-10-drop-anthropic-dep.md](./tasks/task-003-v3-10-drop-anthropic-dep.md)
  - Priority: Low
  - Dependencies: task-003-v3-06 (no anthropic import remains in scripts/), task-003-v3-11 (no anthropic import remains in tests/)
  - Estimated time: 0.1 day

### Phase 3 — Tests refactor

- [R-43] [I-V3.6b] **Delete the 9 remaining anthropic-mock function tests** in `tests/test_wiki_extract_concepts.py` (those that invoke `wec.extract_concepts_llm("body", [])` directly — see bead file for catalogued list). The 6 legacy-shape `main()` tests were already deleted in 003-v3-11a (Phase -1); their regression intent has been preserved as migrated tests in 003-v3-00/01/03. Confirm no `mock.patch("anthropic.Anthropic")` or `LLMUnavailableError` or `extract_concepts_llm` references remain. **Net delta: −9 tests**.
  - Description File: [docs/tasks/task-003-v3-11-test-refactor.md](./tasks/task-003-v3-11-test-refactor.md)
  - Priority: Critical (blocks 003-v3-06 deletion)
  - Dependencies: task-003-v3-01, task-003-v3-02, task-003-v3-03, task-003-v3-04, task-003-v3-05 (logic + regression-migration tests landed)
  - Estimated time: 0.25 day (reduced from 0.5d — 11a took the harder half)

- [R-43] [I-V3.7] Refactor `tests/test_wiki_extract_concepts_integration.py`: drop anthropic mocks; replace with canned candidates JSON fixture at `tests/fixtures/source_extract/candidates.json` (renamed from `llm-response.json`; restructured to drop the metadata wrapper — orchestrator emits raw `[{...}]` array). Same 3 scenarios (first / unchanged / --ingest) split into prepare + apply subprocess invocations.
  - Description File: [docs/tasks/task-003-v3-12-integration-test-refactor.md](./tasks/task-003-v3-12-integration-test-refactor.md)
  - Priority: Critical
  - Dependencies: task-003-v3-03 (apply subcommand exists)
  - Estimated time: 0.5 day

### Phase 4 — Verification / housekeeping / smoke / regression

- [R-30, R-33′, R-42] [I-V3.8] **Drift-verification only** (ARCH update was completed in analysis phase). Grep ARCHITECTURE.md §2.1 + §3.4 + status header for v3.1 invariants: `prepare`/`apply` subcommand names; exit-code table 0/1/2/4/5/6; new sub-envelopes; "Decision-17"; "v3.1 target architecture". Confirm no `extract_concepts_llm` / `LLMUnavailableError` / `--model` / `--max-tokens` references remain in the v3.1 sections. **Output**: drift report; if any drift found → re-edit ARCH inline; if clean → mark bead complete.
  - Description File: [docs/tasks/task-003-v3-13-arch-update.md](./tasks/task-003-v3-13-arch-update.md)
  - Priority: Low (verification gate)
  - Dependencies: task-003-v3-06 (code matches the described shape)
  - Estimated time: 0.1 day

- [R-30, R-42, housekeeping] [I-V3.9] Update `docs/ROADMAP.md`: append R-3 v3.1 entry under "Done" with BREAKING CHANGE call-out (H-4). Update `docs/KNOWN_ISSUES.md`: mark L-V3.3 obsolete (LLM call deleted); add **P-6** (known_concepts payload O(N) per call, SEV-2); add **P-7** (no batch surface for N-source-page workflows, SEV-2); add **P-8** (WAL PRAGMA setup cost doubled by two-process `prepare`+`apply`, SEV-3); add **P-9** (`missing_concept_files` O(N) stat sweep at Karpathy scale, SEV-3); add nit row for Q17 `SOURCE_NOT_FOUND` vs `INVALID_SOURCE_PATH` info-disclosure oracle.
  - Description File: [docs/tasks/task-003-v3-14-roadmap-known-issues-update.md](./tasks/task-003-v3-14-roadmap-known-issues-update.md)
  - Priority: Low
  - Dependencies: task-003-v3-06 (code shipped)
  - Estimated time: 0.25 day

- [R-43, H-4] [I-V3.10] **Dogfood smoke on `trade-agents` vault** per TASK.md §7. Execute all 18 smoke steps. **BREAKING CHANGE smoke (mandatory)**: `bin/wiki-extract-concepts --vault X --source-page Y` (no subcommand) → argparse exit + helpful error pointing at `prepare`/`apply`.
  - Description File: [docs/tasks/task-003-v3-15-dogfood-smoke.md](./tasks/task-003-v3-15-dogfood-smoke.md)
  - Priority: Critical (acceptance gate)
  - Dependencies: task-003-v3-06, task-003-v3-09, task-003-v3-10, task-003-v3-12 (all code + tests + docs landed)
  - Estimated time: 0.5 day

- [R-43] [I-V3.11] **Regression sweep**: `pytest tests/ -q` → **at least 436 passed** (target ~436; baseline 396 − 15 deleted across 11a + 11 + 55 added across 00..05/12/17 = ~436). `mypy --strict scripts/` → no issues. Confirm `bin/wiki-extract-concepts prepare --help` + `bin/wiki-extract-concepts apply --help` route correctly. Retire SDK-metadata deep-sweep deferred item from KNOWN_ISSUES (moot post-v3). **MID-REFACTOR INVARIANT (Option A)**: each prior bead's verification step must show `pytest tests/ -q ≥ 390` (no regression between any two bead boundaries; per-bead atomicity respected; see §6 R-2 for the rationale behind the 390 floor vs. originally-claimed 396).
  - Description File: [docs/tasks/task-003-v3-16-regression-sweep.md](./tasks/task-003-v3-16-regression-sweep.md)
  - Priority: Critical (acceptance gate)
  - Dependencies: **all prior** task-003-v3-00..task-003-v3-15
  - Estimated time: 0.25 day

- [R-42] [I-V3.12] **Adversarial envelope-shape parametrized test**: add `tests/test_wiki_extract_concepts.py::test_apply_error_envelopes_never_echo_content` — parametrize over every sub-envelope from R-42(c) + R-42(d) (`SOURCE_TOO_LARGE`, `SOURCE_CHANGED_DURING_EXTRACTION`, `INVALID_CANDIDATES_PATH`, `CANDIDATES_TOO_LARGE`, `CANDIDATE_COUNT_OUT_OF_BOUNDS`, `FIELD_TOO_LONG`, `UNKNOWN_FIELD`, `FIELD_QUOTE_NOT_IN_BODY`). For each: trigger the envelope; assert JSON has keys `{error, field?, reason}`; assert JSON does NOT contain keys `content`, `value`, `raw`, `received`; assert the offending input string is NOT a substring of any envelope field value (CWE-117 / CWE-209 regression guard).
  - Description File: [docs/tasks/task-003-v3-17-envelope-shape-tests.md](./tasks/task-003-v3-17-envelope-shape-tests.md)
  - Priority: High (security regression guard)
  - Dependencies: task-003-v3-02 (validator emits envelopes), task-003-v3-03 (apply emits envelopes)
  - Estimated time: 0.25 day

### Note on I-V3.13 (rolled into 003-v3-04)

The original I-V3.13 (content-hash skip in `write_concept_page`) is **folded into 003-v3-04** alongside the markdown sanitization + symlink refuse, because all three reshape the same helper function and share the same regression-test fixture. Splitting would have created two beads touching the same ~50 LoC body with overlapping test surfaces — net waste. The C-1 acceptance from I-V3.13 remains explicit inside the 003-v3-04 task file's acceptance checklist.

---

## 2. Dependency DAG (critical-path view)

```text
                  ┌──────────────────────────────────┐
                  │ task-003-v3-11a delete-legacy-   │  (I-V3.6a, R-43) — PHASE -1
                  │   main-tests (BLOCKING)          │  Suite: 396 → 390 (green)
                  └──────────┬───────────────────────┘
                             ▼
                  ┌──────────────────────────────────┐
                  │ task-003-v3-00 argparse-subparser│  (I-V3.1a, R-30) — PHASE 0
                  │   scaffold (BLOCKING)            │  Suite: 390 → 396 (+6 new)
                  └──────────┬───────────────────────┘
                             │
        ┌────────────────────┼────────────────────┬─────────────────────┐
        ▼                    ▼                    ▼                     ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│ task-003-v3-01  │  │ task-003-v3-02  │  │ task-003-v3-04  │  │ task-003-v3-07  │
│ prepare         │  │ strict-validator│  │ write-cp reshape│  │ concept-extract │
│ (I-V3.1b)       │  │ (I-V3.1c)       │  │ (I-V3.1e+13)    │  │ skill (I-V3.2)  │
│ +6 net          │  │ +8 net          │  │ +12 net         │  │ docs only       │
└────────┬────────┘  └────────┬────────┘  └─────────────────┘  └─────────────────┘
         │                    │
         └──────────┬─────────┘
                    ▼
         ┌─────────────────┐                    ┌─────────────────┐
         │ task-003-v3-03  │                    │ task-003-v3-08  │
         │ apply           │◄───┐               │ workflow doc    │
         │ (I-V3.1d)       │    │               │ (I-V3.3)        │
         │ +8 net          │    │               └─────────────────┘
         └────────┬────────┘    │
                  │             │
                  ├─────────────┼──┬──────────────┐
                  ▼             │  ▼              ▼
         ┌─────────────────┐    │  ┌──────────┐ ┌─────────────────┐
         │ task-003-v3-05  │    │  │ task-12  │ │ task-003-v3-17  │
         │ --orch-id flag  │    │  │ integ    │ │ envelope-shape  │
         │ (I-V3.1g) +3    │    │  │ (I-V3.7) │ │ (I-V3.12) +12   │
         └────────┬────────┘    │  └──────────┘ └─────────────────┘
                  │             │
                  ▼             │
         ┌─────────────────┐    │
         │ task-003-v3-09  │    │
         │ skill rewrite   │    │
         │ (I-V3.4) docs   │    │
         └─────────────────┘    │
                                │
         ┌──────────────────────┘
         ▼
┌─────────────────┐    (consumes logic from 01/02/03/04/05)
│ task-003-v3-11  │    PHASE 3
│ delete 9 LLM-   │    Suite: post-05 peak − 9 (green)
│ mock function   │
│ tests (I-V3.6b) │
└────────┬────────┘
         ▼
┌─────────────────┐
│ task-003-v3-06  │ (I-V3.1f) — delete LLM AFTER tests refactored
│ delete-llm-call │
└────────┬────────┘
         ▼
┌─────────────────┐
│ task-003-v3-10  │ (I-V3.5) — drop anthropic dep
│ drop-anthropic  │
└────────┬────────┘
         │
     ┌───┴────────────┬────────────────┬──────────────────┐
     ▼                ▼                ▼                  ▼
┌─────────┐ ┌─────────────────┐ ┌─────────────┐ ┌─────────────────┐
│ task-13 │ │ task-003-v3-14  │ │task-v3-15   │ │ task-003-v3-16  │
│ ARCH    │ │ roadmap+issues  │ │ dogfood     │ │ regression sweep│
│ verify  │ │ (I-V3.9)        │ │ (I-V3.10)   │ │ (I-V3.11) GATE  │
│(I-V3.8) │ │                 │ │             │ │                 │
└─────────┘ └─────────────────┘ └─────────────┘ └─────────────────┘
```

**Critical path** (longest blocking chain): **11a → 00** → 01 → 03 → 05 → 09 → 11 → 06 → 10 → 15 → 16.
**Parallel-safe pairs**:
- 11a: serial precondition (no parallel work)
- After 00: {01, 02, 04, 07}
- After 03: {05, 12, 17}
- After 05: {09}
- After 10: {13, 14, 15, 16}

**Suite size at every bead boundary** (Option A invariant — floor 390, target ≥ 390 between any two beads):
| After bead | Suite | Δ | Notes |
|---|---|---|---|
| baseline | 396 | — | v2 ship state |
| 11a | 390 | −6 | 6 legacy-shape tests deleted |
| 00 | 396 | +6 | 5 new dispatch tests + 1 replacement help-text + 1 rename |
| 01 | 402 | +6 | 7 prepare tests − 1 stub-dispatch test |
| 02 | 410 | +8 | strict-validator tests |
| 03 | 418 | +8 | 9 apply tests − 1 stub-dispatch test |
| 04 | 430 | +12 | markdown/sanitize/hash/symlink |
| 05 | 433 | +3 | orchestrator-id |
| 17 | 445 | +12 | envelope-shape parametrized |
| 11 | 436 | −9 | 9 anthropic-mock function tests deleted |
| 06 | 436 | 0 | LLM code deleted; tests already gone |
| 10 | 436 | 0 | anthropic dep dropped |

**Final**: ~436 passed (well above the original 398 target).

---

## 3. Stub-First Application (per `skill-tdd-stub-first`)

| Bead | Code surface? | Phase-1 stub | Phase-1 test (Red→Green on stub) | Phase-2 logic |
|---|---|---|---|---|
| 003-v3-11a | **no — test deletion** | n/a | n/a | direct delete of 6 legacy-shape tests + insert TODO migration markers |
| 003-v3-00 | yes (argparse scaffold + dispatch stubs) | `prepare(args) -> int` and `apply(args) -> int` `raise NotImplementedError`; subparsers wired; `main` dispatches | `test_argparse_no_subcommand_returns_helpful_error` (Red); `test_argparse_prepare_subparser_exists` + `test_argparse_apply_subparser_exists` + `test_argparse_top_level_help_shows_subcommands` (Green) | helpers replaced by 003-v3-01..05 |
| 003-v3-01 | yes (prepare logic) | `prepare` body in place; emit minimal JSON | unit tests for the 6 prepare cases Red on stub → Green on logic | full prepare impl |
| 003-v3-02 | yes (validator rewrite) | `_validate_candidates_schema` defined with rename only; existing checks preserved; new checks `pass` | unit tests for unknown-field / count-bound / per-field-cap Red on stub → Green | full strict-mode logic |
| 003-v3-03 | yes (apply logic) | `apply` body in place; minimal happy path | unit tests for 6 apply cases Red → Green | full apply impl |
| 003-v3-04 | yes (write_concept_page reshape) | symlink-refuse stub returns early; hash-skip stub returns `(target, "unchanged")` placeholder; sanitization helpers stubbed | adversarial regression tests Red → Green | hash-compute + atomic rewrite + sanitization |
| 003-v3-05 | yes (--orchestrator-id flag) | `--orchestrator-id` argparse added; default `"orchestrator"`; validation `pass` | unit tests for 3 cases Red → Green | regex validation + plumbing through upsert |
| 003-v3-06 | yes (deletion) | n/a — pure delete | n/a — assertion: `grep -n "extract_concepts_llm\|LLMUnavailableError\|import anthropic" scripts/wiki_skills/wiki_extract_concepts.py` returns 0 lines; `pytest tests/ -q` still green (because 003-v3-11 deleted the dependent tests already) | n/a |
| 003-v3-07 | **no — docs** | n/a | n/a | direct write of SKILL.md + symlinks |
| 003-v3-08 | **no — docs** | n/a | n/a | direct write of workflow + symlink |
| 003-v3-09 | **no — docs** | n/a | n/a | direct rewrite of SKILL.md |
| 003-v3-10 | yes (1-line dep change) | n/a — small surface | n/a | `requirements.txt` edit; pip-install confirms no anthropic pulled |
| 003-v3-11 | yes (tests rewrite) | n/a — test code IS the surface | each new test Red on missing impl → Green after the matching Phase-1 bead | the test refactor is itself the deliverable; runs lockstep with code beads |
| 003-v3-12 | yes (integration test rewrite) | canned fixture + skip placeholder | Red → Green when apply subcommand works | unskip; subprocess invocation pattern |
| 003-v3-13 | **no — verify** | n/a | n/a | grep ARCH for drift; emit report |
| 003-v3-14 | **no — docs** | n/a | n/a | direct edits to ROADMAP + KNOWN_ISSUES |
| 003-v3-15 | **no — smoke** | n/a | n/a | run 18-step recipe |
| 003-v3-16 | **no — verify** | n/a | n/a | `pytest tests/ -q`, `mypy --strict scripts/` |
| 003-v3-17 | yes (parametrized test) | parametrize list of sub-envelopes; assertion shape | each parameter Red on missing envelope → Green after 003-v3-02 + 003-v3-03 | full assertion logic |

**Note on the Option A two-step deletion** (replaces the original lifecycle-interleaving design):

The original PLAN tried to atomically delete 12 tests AND add 14 tests inside a single `003-v3-11` bead via intra-bead commit interleaving — but that violated the framework contract that bead = atomic unit (one commit, one pytest gate). The 2026-05-28 adversarial review caught this as HIGH-1.

**Option A fix**: split the 12-test deletion into two beads ordered around the breakage:
- **003-v3-11a** (Phase -1, runs FIRST): deletes the 6 tests that call `wec.main([... legacy args ...])`. These would have broken at 003-v3-00's `add_subparsers(required=True)` change regardless of LLM-mock status — they are removed PRE-emptively. Regression intent migrated to Phase-1 beads (H-1 → 003-v3-01; H-3 → 003-v3-01; C-1 → 003-v3-03; ingest-e2e → 003-v3-03; no-ingest-manifest → 003-v3-03; top-level-help → 003-v3-00).
- **003-v3-11** (Phase 3, runs after 003-v3-05): deletes the remaining 9 anthropic-mock function tests (those invoke `wec.extract_concepts_llm()` directly, never went through `main()`). These stay green through 003-v3-00..05 because the function is still defined.

Net: same 15-test reduction (6 + 9 = 15, originally framed as 12 — the 3 main-with-anthropic tests were in the 12 but ALSO needed pre-00 deletion, so they migrated from 11 scope to 11a scope; the 6 legacy-shape includes 3 non-anthropic that were not in the original 12 count). Each bead is atomic, no intra-bead interleaving.

---

## 4. Use Case Coverage

| Use Case | Description | Beads |
|---|---|---|
| **UC-08 v3.1 main** (without `--ingest`) | Operator invokes `/wiki-extract-concepts`; orchestrator does prepare → synthesize → apply | 003-v3-00, 003-v3-01, 003-v3-02, 003-v3-03, 003-v3-04, 003-v3-05, 003-v3-07, 003-v3-08, 003-v3-09 |
| **UC-08 v3.1 main** (with `--ingest`) | Same plus in-process indexer dispatch (Decision-15 preserved) | All of UC-08 main + (preserved v2 `dispatch_to_indexer`, untouched in v3.1) |
| **UC-08 A6** (operator edits source between prepare and apply) | apply detects hash mismatch → exit 2 SOURCE_CHANGED | 003-v3-03 (apply hash recompute), 003-v3-17 (envelope-shape) |
| **UC-08 A7** (agent emits 0 or 26+ candidates) | Exit 4 CANDIDATE_COUNT_OUT_OF_BOUNDS | 003-v3-02 (validator count bound), 003-v3-17 |
| **UC-08 A8** (10MB `definition` field) | Exit 4 FIELD_TOO_LONG with no content echo | 003-v3-02 (per-field cap), 003-v3-17 |
| **UC-08 A9** (extra key in candidate) | Exit 4 UNKNOWN_FIELD (strict mode) | 003-v3-02 (strict equality), 003-v3-17 |
| **UC-08 A10** (`--candidates-file /etc/passwd`) | Exit 2 INVALID_CANDIDATES_PATH | 003-v3-03 (validate_inside_vault), 003-v3-17 |
| **UC-08 A11** (`--candidates-file ./candidates.json` 5GB) | Exit 4 CANDIDATES_TOO_LARGE before any parse | 003-v3-03 (_MAX_CANDIDATES_BYTES), 003-v3-17 |
| **UC-08 A12** (`name="\n## Backdoor"`) | Sanitization strips; concept page body safe | 003-v3-04 (markdown sanitization), regression test |
| **UC-08 A13** (existing `_concepts/X.md` from prior incomplete run) | Content-hash skip: same → unchanged; different → updated | 003-v3-04 (content-hash skip), regression test |
| **UC-09 v3.1** (re-extract on unchanged body) | Orchestrator-level short-circuit after `prepare` returns is_unchanged=true | 003-v3-01 (prepare emits is_unchanged), 003-v3-08 (workflow documents short-circuit) |

---

## 5. RTM Coverage Matrix

| RTM ID | Requirement (v3.1) | Bead(s) | Phase |
|---|---|---|---|
| **R-30** | New `prepare`+`apply` subcommand surface; skill + slash command symlinked; Python `main(argv)` dispatching to subparsers with `required=True` | 003-v3-00, 003-v3-06 (delete legacy), 003-v3-07, 003-v3-08, 003-v3-09 | 0, 1, 2 |
| **R-31** | argparse: `prepare` accepts `--vault --vault-root --source-page [--db-path]`; `apply` adds `--candidates-file/--candidates-stdin` (mutex) + `--source-hash` (REQUIRED) + `[--ingest] [--orchestrator-id]`; removed `--model` + `--max-tokens` | 003-v3-00, 003-v3-01, 003-v3-03, 003-v3-05 | 0, 1 |
| **R-32** | Pre-extraction known-concepts emitted by `prepare`; `missing_concept_files` warns disk/DB drift | 003-v3-01 | 1 |
| **R-33′** | Calling agent synthesizes candidates; `apply` validates via strict `_validate_candidates_schema` (rename + count bound + per-field caps + no extra keys + optional quote-in-body check); envelope NEVER echoes content | 003-v3-02, 003-v3-03 (calls validator), 003-v3-07 (contract docs), 003-v3-17 (envelope-shape) | 1, 2, 4 |
| **R-34** | Known-concepts in prompt (skill); apply.classify_candidates partitions by known-slugs (preserved); optional source_quote ∈ source_body | 003-v3-07 (skill), 003-v3-03 (classify preserved), 003-v3-02 (optional quote check) | 1, 2 |
| **R-35** | Manifest output: wiki-ingest v1.1-compatible (unchanged) | 003-v3-03 (preserves v2 build_manifest call site) | 1 |
| **R-36** | Concept-page generation: content-hash skip semantics; markdown sanitization; symlink refuse | 003-v3-04 | 1 |
| **R-37** | Entity-row upsert with `is_candidate=1` + SQL downgrade-guard (preserved); `canonicalized_by = f"llm:{orchestrator_id}@{date}"` | 003-v3-05 | 1 |
| **R-38** | `page_entity_refs` rows with trust_level='medium' + parsed Lstart-Lend (unchanged) | (preserved v2 upsert_entity_refs — touched only via 003-v3-03 call site) | 1 |
| **R-39** | Idempotency: `prepare` returns `is_unchanged`; `apply` requires `--source-hash` matching disk-recomputed hash → SOURCE_CHANGED on mismatch | 003-v3-01 (prepare), 003-v3-03 (apply enforcement) | 1 |
| **R-40** | Multi-vault `vault_id` enforcement (preserved) | (preserved across all helpers) | 1 |
| **R-41** | In-process dispatch via neutral `_manifest_consumer` (preserved) | (preserved in 003-v3-03 apply call site) | 1 |
| **R-42** | Exit codes 0/1/2/4/5/6 (exit-3 retired); new sub-envelopes; envelopes never echo content | 003-v3-01 (prepare exit 2), 003-v3-02 (validator exit 4), 003-v3-03 (apply exit 2/5/6), 003-v3-06 (delete exit-3 mapping), 003-v3-17 (envelope-shape parametrized) | 1, 4 |
| **R-43** | Test count target ~436 (Option A); floor ≥ 390 between bead boundaries; mypy --strict clean; pytest tests/ -q clean | **003-v3-11a** (Phase -1 hygiene), 003-v3-11, 003-v3-12, 003-v3-17, 003-v3-16 (regression sweep), 003-v3-15 (dogfood smoke) | -1, 3, 4 |
| ~~R-33~~ | ~~Claude Sonnet 4.6 LLM call~~ | **RETIRED** (Decision-17) | — |
| ~~R-44~~ | ~~wiki-enrich --manifest-* flags~~ | **RETIRED** (already in v2 Decision-15) | — |

**1-1 issue mapping** (no orphans): R-30 → I-V3.1a/I-V3.1f/I-V3.2/I-V3.3/I-V3.4/I-V3.5; R-31 → I-V3.1a/I-V3.1b/I-V3.1d/I-V3.1g; R-32 → I-V3.1b; R-33′ → I-V3.1c/I-V3.1d/I-V3.2/I-V3.12; R-34 → I-V3.2/I-V3.1c/I-V3.1d; R-35 → I-V3.1d (preserved); R-36 → I-V3.1e+I-V3.13; R-37 → I-V3.1g; R-38 → I-V3.1d (preserved); R-39 → I-V3.1b/I-V3.1d; R-40 → I-V3.1d/I-V3.1e (preserved); R-41 → I-V3.1d (preserved); R-42 → I-V3.1b/I-V3.1c/I-V3.1d/I-V3.1f/I-V3.12; R-43 → **I-V3.6a (11a)** / I-V3.6 (11) / I-V3.7 / I-V3.11 / I-V3.12 / I-V3.10.

---

## 6. Risk Register

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| **R-1** | **Patch-target lock drift** (carried forward from v2 PLAN R-2) — operator forgets that `unittest.mock.patch` targeting `wiki_extract_concepts` module's bound names MUST patch `scripts.wiki_skills.wiki_extract_concepts.<symbol>` and NOT `scripts.wiki_skills._manifest_consumer.<symbol>` (where the source lives). Drift causes tests to pass locally but fail under refactor. | Medium | Medium | Lock documented in this PLAN §0 invariants; reinforced in 003-v3-03 and 003-v3-11 task files. Lint check during 003-v3-16 regression sweep: `grep -rn "patch.*_manifest_consumer.\(index_from_manifest\|validate_manifest\|WikiIngestError\)" tests/` MUST be empty. |
| **R-2** | **Test-suite regression mid-refactor** — Phase-1 beads in the wrong order produce a window where `extract_concepts_llm` is deleted but its tests still exist (or vice versa), red-failing `pytest tests/ -q` between commits. | Low (after Option A fix) | High | **Option A** (2026-05-28 adversarial review): two-step test-deletion via 003-v3-11a (Phase -1, removes legacy-shape `main()` tests that 003-v3-00 would otherwise break) + 003-v3-11 (Phase 3, removes the remaining anthropic-mock function tests after 003-v3-05). Bead order enforced by DAG: **11a → 00 → 01..05 → 11 → 06 → 10**. Each bead is atomic (one commit, one pytest gate). Suite floor is **390** between any two bead boundaries (NOT 396 as originally claimed — the original claim was unachievable). |
| **R-3** | **`source_state` row drift during the refactor** — operator runs v2 form (legacy invocation) against a vault that's already had v3.1 `prepare` recorded, or vice versa, causing schema-level confusion. | Low | Low | v2 form errors out at argparse (no subcommand) — no SQL state mutation. v3.1 `prepare` runs the same `check_idempotency` against the same `source_state.source_kind='extract-concepts'` key. No collision possible. |
| **R-4** | **`write_concept_page` content-hash compute regression** — sha256 of existing file content includes frontmatter trailing newline differences; equality check rejects byte-identical content as different and triggers spurious rewrite. | Medium | Medium | 003-v3-04 acceptance bullet: regression test seeds file with `frontmatter.dumps(post)` output and re-runs; assert `action="unchanged"` on identical regeneration. Normalize both sides via `bytes(payload, "utf-8")` before sha256. |
| **R-5** | **Symlink-refuse check race** — between `target.is_symlink()` check and `os.replace(tmp, target)`, an attacker swaps the target for a symlink. | Low | Medium | The atomic write is `tempfile + os.replace`; `os.replace` follows symlinks and writes through, but the pre-check refuses BEFORE any write. The race window is narrow but exists. Documented as an iteration-2-LOW residual; mitigation deferred to `O_NOFOLLOW` open + write rename (future hardening). 003-v3-04 acceptance: regression test asserts `PathTraversalError` raised; documents the race in inline comment. |
| **R-6** | **`_MAX_CANDIDATES_BYTES` cap bypass via stdin chunking** — operator pipes 5 GB through stdin one-byte-at-a-time; the read loop accumulates beyond the cap before the check fires. | Low | Medium | 003-v3-03 acceptance: `sys.stdin.buffer.read(_MAX_CANDIDATES_BYTES + 1)` then assert `len(data) <= _MAX_CANDIDATES_BYTES` BEFORE parsing. Reject with `CANDIDATES_TOO_LARGE` exit 4 if length exceeded. Regression test: feed `'x' * (1_048_577)` via stdin → exit 4. |
| **R-7** | **Markdown sanitization regression** — operator-facing concept page formatting changes break existing rendering / lint expectations elsewhere (e.g., `wiki-lint` complains about new blockquote pattern). | Low | Low | 003-v3-04 acceptance: regression test seeds a v2-style page, asserts the new sanitization preserves the visual rendering for legitimate inputs (only adversarial inputs change). `wiki-lint` re-run on dogfood smoke (003-v3-15) catches any cross-skill regression. |
| **R-8** | **Anthropic SDK still installed in dev env after 003-v3-10** — pip didn't uninstall because the package was installed before `requirements.txt` was updated. | Low | Low | 003-v3-10 acceptance: `pip uninstall anthropic -y` after the requirements edit; then `pip install -r requirements.txt`; then `python -c "import anthropic"` → `ModuleNotFoundError`. Dogfood smoke step #13 confirms. |

---

## 7. Definition of Done (acceptance gate — task-003-v3-16)

The task is "Done" iff **all** of the following hold:

- [ ] All **19 beads** (task-003-v3-11a + task-003-v3-00..task-003-v3-17) marked complete with green acceptance bullets.
- [ ] `pytest tests/ -q` → **at least 436 passed, 0 failed** (baseline 396 from v2; − 15 LLM-mock/legacy tests deleted across 11a + 11; + 55 new tests across 00..05/17/12; net ≈ +40 = ~436). **Mid-refactor invariant (Option A)**: each bead transition shows pytest green; no red phase. **Floor**: between any two bead boundaries, `pytest tests/ -q ≥ 390`. (Original 396 floor was unachievable — see §6 R-2 and §3 Option A note.)
- [ ] `mypy --strict scripts/` (full tree) → **Success: no issues found**.
- [ ] Smoke step #1–#11 (TASK §7): core happy path + H-1/H-2/H-4/H-5/H-6/H-7/H-9 adversarial smokes all pass.
- [ ] Smoke step #12: `env | grep -i anthropic` empty.
- [ ] Smoke step #13: `grep anthropic requirements.txt` empty + `python -c "import anthropic"` raises `ModuleNotFoundError`.
- [ ] Smoke step #14: `bin/wiki-extract-concepts prepare --help` shows `--source-page`; `bin/wiki-extract-concepts apply --help` shows `--source-hash`.
- [ ] Smoke step #15: Idempotency re-run after first apply → prepare returns `is_unchanged=true`.
- [ ] Smoke step #16: Error envelope content-leak audit — synthetic test triggers each exit-4 sub-envelope; assert JSON has no `content`, `value`, `raw`, `received` keys (covered by 003-v3-17).
- [ ] Smoke step #17: `pytest tests/ -q` → ≥ 436 passed (Option A target).
- [ ] Smoke step #18: `mypy --strict scripts/`.
- [ ] **BREAKING CHANGE smoke (H-4)**: `bin/wiki-extract-concepts --vault X --source-page Y` (no subcommand) → argparse error containing the strings `prepare` and `apply`.
- [ ] **Patch-target lock invariant (R-1)**: `grep -rn "patch.*_manifest_consumer.\(index_from_manifest\|validate_manifest\|WikiIngestError\)" tests/` → 0 matches.
- [ ] **Adversarial regression smoke**: pytest re-runs the H-1/H-2/H-5/H-6/H-7/H-9 cases from §7 of TASK as unit tests (via 003-v3-11 + 003-v3-17 surface).

**Reference**: smoke recipe full 18 steps in [docs/TASK.md §7](./TASK.md).

---

## 8. Effort Summary

| Metric | Value |
|---|---|
| Beads count | **19** (003-v3-11a + 003-v3-00..003-v3-17) |
| Total working-time estimate (single-developer, sequential) | ~6.0 days (Option A net: +0.25d for 11a − 0.25d saved from reduced 003-v3-11 scope = net 0 change) |
| Critical-path estimate (with parallelization where DAG permits) | ~3.75 days (unchanged — 11a is a 0.25d serial precondition that fits within the previous 003-v3-00 slot allocation) |
| Acceptance-gate effort (task-003-v3-16 alone) | 0.25 day |

**Bead time estimates**:

| Bead | Estimate | Critical path? |
|---|---|---|
| 003-v3-11a delete legacy-main tests | 0.25 d | yes (Phase -1, blocks 003-v3-00) |
| 003-v3-00 argparse subparser scaffold | 0.5 d | yes |
| 003-v3-01 prepare subcommand | 0.75 d | yes |
| 003-v3-02 strict validator | 0.5 d | parallel with 01 |
| 003-v3-03 apply subcommand | 1.0 d | yes |
| 003-v3-04 markdown sanitize + hash skip + symlink | 0.75 d | parallel with 01/02/03 |
| 003-v3-05 --orchestrator-id flag | 0.25 d | yes |
| 003-v3-06 delete LLM call | 0.25 d | yes (last) |
| 003-v3-07 concept-extraction skill | 0.25 d | parallel |
| 003-v3-08 workflow doc | 0.25 d | parallel |
| 003-v3-09 skill wrapper rewrite | 0.25 d | parallel |
| 003-v3-10 drop anthropic dep | 0.1 d | yes (after 06) |
| 003-v3-11 test refactor (anthropic-mock function deletes only) | 0.25 d | yes (precedes 06) |
| 003-v3-12 integration test refactor | 0.5 d | parallel |
| 003-v3-13 arch drift verify | 0.1 d | parallel |
| 003-v3-14 roadmap + known issues | 0.25 d | parallel |
| 003-v3-15 dogfood smoke | 0.5 d | yes (after 06+10+12) |
| 003-v3-16 regression sweep | 0.25 d | yes (acceptance gate) |
| 003-v3-17 envelope-shape parametrized | 0.25 d | parallel with 12 |

---

## 9. Open Issues / Planner Judgement Calls

1. **I-V3.1 split granularity** — TASK.md catalogues I-V3.1 as one big bead but it spans ~600 LoC reshape. PLAN.md splits it into 7 sub-beads (003-v3-00 through 003-v3-06) plus the rolled-in 003-v3-04 (which absorbed I-V3.13). The split is along functional seams (subparser → prepare → validator → apply → write_concept_page reshape → --orchestrator-id → delete legacy). Each sub-bead ≤1 day. Operator may further split during implementation if any sub-bead exceeds budget; the DAG only enforces ordering across sub-beads, not internal split.
2. **I-V3.13 folded into 003-v3-04** — both touch the same helper (`write_concept_page`); splitting created overlapping test surfaces. The acceptance for C-1 (content-hash skip) is preserved explicitly inside 003-v3-04's checklist.
3. **003-v3-11 split into 11a + 11 (Option A, 2026-05-28)** — the original PLAN tried atomic interleaving of test-add + test-delete within a single bead, which violated the framework contract (1 bead = 1 commit). Adversarial review caught this. Fixed by splitting deletion across two beads ordered around the breakage boundary (11a Phase -1 for legacy-shape tests; 11 Phase 3 for anthropic-mock function tests). See §3 Option A note.
4. **I-V3.8 demoted to drift-verification** — ARCH §2.1 + §3.4 were updated in the analysis phase. 003-v3-13 (the bead for I-V3.8) becomes a grep-and-diff check, not an editorial pass. If drift is found, the bead allows inline ARCH edits, but the working assumption is "already done".
5. **003-v3-10 (drop anthropic) timing** — placed AFTER 003-v3-06 (delete LLM call) AND AFTER 003-v3-11 (test refactor) so neither production code nor test code holds a stale `import anthropic` when the dep is removed. Reverse ordering would break `pytest` collection.
6. **`_MAX_SOURCE_BODY_BYTES` value 10 MiB** is from TASK.md spec (Q5 / M-3). Tradeoff: too low rejects legitimate large summaries; too high re-enables DoS. 10 MiB matches the existing `validate_manifest` body cap pattern. Operator may override via future flag if surfaced.
7. **`_MAX_CANDIDATES_BYTES` value 1 MiB** is from TASK.md spec (Q12 / H-6). 1 MiB ≈ 100 candidates × 10 KB each (well above the 25-candidate cap × per-field caps `200 + 2000 + 500 + ~100` = ~2.8 KB per candidate × 25 = 70 KB realistic upper bound). 1 MiB is generous and bounds DoS surface.

---

## 10. Start Signal

Plan-reviewer gate next. After sign-off, start with **task-003-v3-11a** (delete-legacy-main-tests, Phase -1) — a 0.25-day test-file edit that unblocks 003-v3-00. After 11a lands, proceed to **task-003-v3-00** (argparse-subparser-scaffold). No parallel work permitted until 003-v3-00 lands. After 003-v3-00 ships, Phase 1 beads {003-v3-01, 003-v3-02, 003-v3-04, 003-v3-07} may begin in parallel. Phase 1 chain (003-v3-01 → 003-v3-03 → 003-v3-05 → 003-v3-09) is strict-sequential. 003-v3-06 (delete legacy LLM call) MUST be preceded by 003-v3-11 (test refactor, anthropic-mock function deletes) so the suite stays green.

**Option A green-throughout invariant**: between any two bead boundaries, `pytest tests/ -q ≥ 390`. The 003-v3-11a step lowers the suite floor from 396 to 390, after which it monotonically increases through Phase 1.
