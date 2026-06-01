# TASK 015 — Performance hardening: extract-concepts hot path

### 0. Meta Information
- **Task ID:** 015
- **Slug:** `perf-hardening-extract-concepts`
- **Mode:** VDD (full pipeline)
- **Closes:**
  - `docs/issues/h-perf-3-index-from-manifest-argparse-in-loop.md` (**H-PERF-3**, SEV-2)
  - `docs/issues/p-8-wal-pragma-setup-cost-compounded-across-the-two-process-workflow.md` (**P-8**, SEV-2)
  - `docs/issues/p-6-known-concepts-payload-o-n-per-prepare-invocation.md` (**P-6**, SEV-2)
  - `docs/issues/p-7-no-batch-surface-for-n-source-page-workflows.md` (**P-7**, SEV-2)

---

### 1. General Description

The `wiki-extract-concepts` pipeline (`prepare` → orchestrator synthesis → `apply`) has
four confirmed performance bottlenecks in the `_manifest_consumer` / `wiki_index_upsert`
hot path, all filed as SEV-2 known issues. The concrete trigger: a multi-source enrichment
workflow over ~100 source pages stalls measurably due to:

1. **H-PERF-3** — `index_from_manifest` calls `wiki_index_upsert.main(argv)` once per
   written concept page, which re-parses argparse, opens a fresh SQLite connection, runs
   the full PRAGMA sweep, then closes — all per row. 25 candidates × 100 pages = 2,500
   connection cycles.
2. **P-8** — The two-process `prepare`+`apply` boundary and the in-process `--ingest` path
   together open up to 4 SQLite connections per source page. Each pays the WAL/journal/
   synchronous PRAGMA setup cost (~5 ms). At 1,000 pages with `--ingest`: ~20 s pure
   overhead.
3. **P-6** — `prepare` embeds the full known-concepts list (slug + name + type + aliases)
   in its JSON envelope. At 10k entities: ~500 KB per invocation. The orchestrator typically
   only needs slugs for de-dup, not the full record set.
4. **P-7** — No batch mode: each source page requires a separate CLI invocation (process
   spawn + SQLite cold-open). Vault-wide re-extraction of 100 pages = 100 process spawns.

Fixes are designed to be **zero DDL** (`user_version` stays 5), **backward-compatible**
(existing single-page CLI surface and stdout JSON contracts unchanged), and **additive**
(new flags / entry-points alongside the existing ones).

---

### 2. Requirements Traceability Matrix (RTM)

| ID | Requirement | MVP? | Sub-features |
|----|------------|------|--------------|
| **R-015-1** | Programmatic entry-point for `wiki_index_upsert` (closes H-PERF-3 root) | **YES** | (a) add `upsert_one(vault_id, src, vault_root, repo) → dict[str,Any]` to `wiki_index_upsert.py`; (b) identical logic to `main()` but accepts an already-open `repo`, no argparse, returns the envelope dict instead of calling `emit()`; (c) existing `main()` wraps `upsert_one` (no logic duplication); (d) mypy `--strict` typed |
| **R-015-2** | `index_from_manifest` connection reuse (closes H-PERF-3 + P-8) | **YES** | (a) open ONE `make_repo` before the loop; (b) loop calls `upsert_one(…, repo)` — no argparse per entry, no per-entry connection open/close; (c) `append_log_event` reuses the same repo; (d) repo closed once in a `finally` when opened internally; (e) existing envelope schema `{upserted, failed, log_event_id}` unchanged; (f) zero functional regression on success + partial-failure paths; (g) add optional `repo` parameter `index_from_manifest(…, repo=None)` — when provided the caller owns lifecycle (function uses it directly, does NOT close it); backward-compat (existing callers omit `repo` → function opens/closes its own) |
| **R-015-3** | `prepare --known-concepts-format` flag (closes P-6) | **YES** | (a) new optional flag `--known-concepts-format {full,slugs-only}` (default `full`) on the `prepare` subparser; (b) `full` → current `[{slug,name,type,aliases},…]` (backward-compat); (c) `slugs-only` → `[slug,slug,…]` plain string array; (d) `known_concepts` key present in both modes (orchestrator key name unchanged); (e) mypy typed; (f) documented in `--help` |
| **R-015-4** | `prepare --batch` surface (closes P-7, Phase A: prepare side) | **YES** | (a) new optional `--batch <slugs.json>` flag (mutex with `--source-page`); (b) input: path to a JSON file containing `[source_slug, …]` list; (c) output: `{batch: [{source_slug, source_hash, is_unchanged, known_concepts, missing_concept_files, source_path}, …]}` envelope, one entry per slug; (d) entry-level errors stored as `{source_slug, error, message}` (per-page isolation — one failure does NOT abort the batch); (e) `slugs.json` validation: must be a non-empty list of strings, each passing `_resolve_source_inside_sources`; (f) `--known-concepts-format` applies batch-wide (known_concepts queried once, shared across entries) |
| **R-015-5** | `apply --batch-candidates` surface (closes P-7, Phase B: apply side) | **YES** | (a) new optional `--batch-candidates <combined.json>` flag (mutex with `--candidates-file` / `--candidates-stdin`); (b) input schema: `[{source_slug, source_hash, candidates: […]}, …]` — one entry per source page; (c) standard per-entry `_validate_candidates_schema` + hash-check per entry; (d) per-entry `_apply_single(…, repo)` so one SQLite connection is reused across all entries; (e) aggregate output: `{batch: [{source_slug, action, manifest|error}, …]}`; (f) `--ingest` flag still dispatches `index_from_manifest` (once per batch, on the aggregated manifests) |
| **R-015-NF1** | Zero DDL | **YES** | `user_version` stays 5; no new tables/columns/indexes |
| **R-015-NF2** | Backward compatibility | **YES** | All existing single-page CLI flags (`prepare --source-page`, `apply --candidates-file/--candidates-stdin`) and stdout JSON envelope schemas unchanged |
| **R-015-NF3** | mypy `--strict` + pytest green | **YES** | All 63+ files pass mypy `--strict`; pytest count ≥ 852 (+4 skip) with no regressions; new code covered |
| **R-015-NF4** | No CWE-117/CWE-209 regressions | **YES** | `upsert_one` error envelopes never echo raw file content; batch error entries never echo candidate values |

---

### 3. Problem Description

#### 3.1 H-PERF-3: argparse-in-loop (highest-impact)

`_manifest_consumer.index_from_manifest` (lines 81–194) loops over `manifest["written"]`
and for each entry calls `wiki_index_upsert.main(argv)`. `main()` calls `_build_parser().parse_args(argv)`,
constructs `make_repo(config)`, runs the full PRAGMA setup, upserts, then closes the repo.
At 25 candidates × 1,000 source pages = 25,000 argparse + repo-open cycles.

The fix (R-015-1 + R-015-2): extract the per-entry upsert logic into
`upsert_one(vault_id, src, vault_root, repo)` that takes an already-open repo. The
`index_from_manifest` caller opens one repo, loops calling `upsert_one`, then appends the
log event on the same connection, then closes.

#### 3.2 P-8: PRAGMA setup multiplied by process boundary + in-process loop

Even after H-PERF-3 is fixed, `prepare` and `apply` are separate CLI invocations that each
open their own connections. For the `--ingest` path: `apply` opens a repo (for entity
writes), then `index_from_manifest` opens repos for the upsert loop and for log_event.
After R-015-2 the loop connections are eliminated; the `apply`-vs-`index_from_manifest`
connection boundary is an acceptable remaining cost (scoped — the two-process boundary is
a Decision-17 design invariant, not a defect).

#### 3.3 P-6: oversized `known_concepts` payload

`prepare` queries `entities LEFT JOIN entity_aliases` and serializes full records. The full
record is needed only when the orchestrator suspects a duplicate. Adding `--known-concepts-format=slugs-only`
lets operators cap the envelope at ~N × 30 bytes instead of ~N × 200 bytes, with the
trade-off that the orchestrator must re-query full records when a slug match is suspected.

#### 3.4 P-7: no batch surface

Each source page requires a separate process spawn. `prepare --batch <slugs.json>` amortizes
the process-spawn + DB cold-open cost across all pages in the batch; `known_concepts` is
loaded once and shared. `apply --batch-candidates` writes all concept pages in one invocation
with a shared SQLite connection (R-015-5d), making batch-apply a superset of the R-015-2
connection-reuse fix.

---

### 4. Use Cases

#### UC-015-1: CLI operator — single-page workflow (regression)
**Actors:** Operator, `wiki-extract-concepts` CLI
**Preconditions:** vault registered, source page exists
**Main scenario:**
1. Operator runs `wiki-extract-concepts prepare --vault <id> --vault-root <root> --source-page <slug> --db-path <db>`
2. CLI opens one repo, loads known_concepts (full, default), emits JSON envelope
3. Operator synthesises candidates and runs `wiki-extract-concepts apply … --candidates-file candidates.json --ingest`
4. Apply opens one repo for all work; calls `index_from_manifest(manifest, …, repo=repo)` passing the shared repo (R-015-2)
5. All 25 concept pages upserted via `upsert_one`; log_event appended on the same repo; repo closed once
6. CLI exits 0; stdout envelope `{batch: null, upserted: […], log_event_id: N}`
**Postconditions:** DB state identical to pre-015 behaviour
**Acceptance:** existing passing pytest suite stays green; no behaviour change

#### UC-015-2: CLI operator — `slugs-only` mode
**Actors:** Operator
**Preconditions:** vault has ≥1 entity
**Main scenario:**
1. Operator runs `prepare … --known-concepts-format slugs-only`
2. Envelope `known_concepts` field is `["slug-a", "slug-b", …]` (plain strings, not objects)
3. Envelope size for 10k entities ≤ ~350 KB (vs ~5 MB full)
**Alternative scenario:**
- Operator omits flag or passes `--known-concepts-format full` → behaves as before
**Acceptance:** envelope `known_concepts` is a list of strings; existing `full` output unchanged

#### UC-015-3: CLI operator — batch prepare
**Actors:** Operator
**Preconditions:** vault registered; `slugs.json` = `["page-a","page-b","page-c"]`
**Main scenario:**
1. Operator runs `prepare --vault <id> --vault-root <root> --batch slugs.json --db-path <db>`
2. CLI resolves each slug; known_concepts loaded once; source bodies read and hashed individually
3. Emits `{batch: [{source_slug,source_hash,is_unchanged,known_concepts,…}, …]}`
**Alternative scenario A — one slug fails to resolve:**
- Entry in batch result has `{source_slug, error: "SOURCE_NOT_FOUND", message: …}` (non-fatal; other entries succeed)
**Alternative scenario B — batch file is malformed JSON:**
- CLI emits `{error: "INVALID_BATCH_FILE", message: …}` and exits 2
**Acceptance:** batch envelope has one entry per slug; per-entry error does not abort batch; known_concepts loaded once

#### UC-015-4: CLI operator — batch apply
**Actors:** Operator
**Preconditions:** combined.json from batch prepare synthesis is ready
**Main scenario:**
1. Operator runs `apply --vault <id> --vault-root <root> --batch-candidates combined.json --ingest --db-path <db>`
2. CLI opens one repo; for each entry: validates candidates schema + source hash, writes concept pages, upserts entities
3. Aggregated manifest passed to `index_from_manifest` (R-015-2 path) once
4. Emits `{batch: [{source_slug, action, manifest}, …]}`
**Alternative scenario — one entry has invalid candidates:**
- That entry has `{source_slug, error: "EXTRACTION_PARSE_ERROR", …}`; remaining entries proceed
**Acceptance:** one DB connection open for all entries; `index_from_manifest` called once; partial failures reported per entry

#### UC-015-5: `upsert_one` programmatic caller (library use)
**Actors:** Python code (e.g., future `wiki-enrich` in-process path)
**Main scenario:**
1. Caller opens `make_repo(config)`, calls `wiki_index_upsert.upsert_one(vault_id, src, vault_root, repo)` in a loop
2. Returns `{"action": outcome, "vault_id": …, "slug": …, …}` dict
3. Caller closes repo after the loop
**Postconditions:** same DB state as calling `main()` per entry; no stdout side-effect
**Acceptance:** mypy typed; existing `main()` calls `upsert_one` internally (no duplication)

---

### 5. Acceptance Criteria

| ID | Criterion | Pass/Fail |
|----|-----------|-----------|
| AC-015-1 | `test_index_from_manifest_single_connection` — assert `make_repo` is called exactly once per `index_from_manifest` call (monkeypatched repo counter) | PASS when make_repo call count = 1 |
| AC-015-2 | `test_upsert_one_no_argparse` — call `upsert_one(…, repo)` directly; assert argparse is NOT invoked (mock); assert returned dict has `action` key | PASS |
| AC-015-3 | `test_prepare_slugs_only` — run prepare with `--known-concepts-format slugs-only` against vault with ≥3 entities; assert `known_concepts` is a list of strings (not dicts) | PASS |
| AC-015-4 | `test_prepare_full_default` — run prepare without the flag; assert `known_concepts` entries are dicts with `{slug,name,type,aliases}` keys (regression) | PASS |
| AC-015-5 | `test_prepare_batch_multi_page` — batch prepare over 3 slugs; assert envelope has `batch` key with 3 entries, each with `source_slug`+`source_hash` | PASS |
| AC-015-6 | `test_prepare_batch_partial_failure` — batch with 2 valid + 1 invalid slug; assert batch result has 3 entries, 2 success + 1 error; exit code 0 | PASS |
| AC-015-7 | `test_apply_batch_candidates` — batch apply over 2 source pages; assert `repo.upsert_page` is called once per concept page (via shared repo); manifests aggregated | PASS |
| AC-015-8 | `test_apply_batch_with_ingest` — batch apply `--ingest` over 2 source pages; assert `make_repo` called exactly once for the entire invocation (shared across entity writes + both `index_from_manifest` calls); `index_from_manifest` called once per source page (N=2), each receiving the shared repo | PASS |
| AC-015-9 | Existing golden-snapshot / karpathy byte-identity tests pass unchanged (zero DDL, zero layout change) | PASS |
| AC-015-10 | `mypy --strict scripts/` — zero new errors across all 63+ files | PASS |
| AC-015-11 | Full `pytest tests/` — count ≥ 852, 0 unexpected failures | PASS |

---

### 6. Non-Goals

- No changes to the `wiki-enrich` or `wiki-query` hot paths (separate issues).
- No connection pooling (`sqlite3.connect` object is not thread-safe; pooling deferred).
- No changes to the WAL/PRAGMA configuration itself (P-8 root-cause PRAGMA caching is
  out-of-scope; the fix here reduces *call count*, not per-call cost).
- No Postgres backend (P3 roadmap item).
- No change to the `concept-extraction` SKILL.md prompt or eval harness.

---

### 7. Implementation phasing (Stub-First beads)

| Phase | Beads | Scope |
|-------|-------|-------|
| 0 | 015-00 | Regression anchor — confirm baseline pytest count, run mypy, confirm zero new failures |
| 1 | 015-01 | Stub `upsert_one` in `wiki_index_upsert.py` (returns stub dict); stub test RED |
| 1 | 015-02 | Implement `upsert_one`; `main()` delegates; test GREEN |
| 1 | 015-03 | Refactor `index_from_manifest` — single repo, call `upsert_one` in loop; AC-015-1 + AC-015-2 GREEN |
| 2 | 015-04 | Stub `--known-concepts-format` flag + test RED |
| 2 | 015-05 | Implement `slugs-only` path; AC-015-3 + AC-015-4 GREEN |
| 3 | 015-06 | Stub `prepare --batch` + test RED |
| 3 | 015-07 | Implement batch prepare (known_concepts once, per-slug resolve + hash); AC-015-5 + AC-015-6 GREEN |
| 4 | 015-08 | Stub `apply --batch-candidates` + test RED |
| 4 | 015-09 | Implement batch apply (shared repo, per-entry apply, aggregate manifest); AC-015-7 + AC-015-8 GREEN |
| 5 | 015-10 | Close issues, update `.AGENTS.md`, docs gate |

---

### 8. Open Questions

_(none blocking — all four fixes have concrete file-level fix plans confirmed in the issue
files; architecture is additive/backward-compatible)_
