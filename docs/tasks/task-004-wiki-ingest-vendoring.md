# TASK: wiki-ingest-vendoring — Python-import-only vendor of wiki-ingest module

### 0. Meta Information

- **Task ID:** 004
- **Slug:** `wiki-ingest-vendoring`
- **Mode:** Standard
- **Status:** `COMPLETE` (2026-05-27) — all 11 beads shipped via `/vdd-develop` (004-01, 004-03) + `/vdd-develop-all` chain (004-02, 004-04..11). `/vdd-multi` adversarial sweep applied 6 CRITICAL/HIGH fixes inline (LICENSE-upstream rsync exclude, narrowed exception catch, truthy env parsing, full primary-path PARTIAL_INDEX_FAILURE envelope, absolute-path rejection, hex-case-insensitive divergence regex) + 12 regression-guard tests. Final state: 328 pytest passed / 4 skipped (was 295 baseline; +33 net new tests across TASK 004), `mypy --strict scripts/` clean on 53 files (vendored excluded via mypy.ini per Decision-14), all R-56/R-57 invariants verified. Awaiting operator commit decision per `/vdd-develop-all` no-auto-commit policy.
- **Predecessor:** [docs/tasks/task-003-wiki-extract-concepts.md](./tasks/task-003-wiki-extract-concepts.md) — PAUSED pending this task's ship
- **Related artifacts:**
  - [docs/ROADMAP.md](./ROADMAP.md) §P0 R-V1 — decision write-up and scoring summary
  - [docs/ARCHITECTURE.md](./ARCHITECTURE.md) — §1.5.2 (cross-process flow diagram to be updated), §1.5.3 (external wiki-ingest anatomy), §1.5.4 (DAL layer)
  - [docs/WIKI-INGEST-V1.1-CONTRACT.md](./WIKI-INGEST-V1.1-CONTRACT.md) — manifest JSON schema (unchanged by vendoring)
  - [docs/adr/ADR-001-wiki-ingest-integration.md](./adr/ADR-001-wiki-ingest-integration.md) — Option I (Wrap + Index); vendoring collapses the transport, not the semantics
  - [docs/adr/ADR-002-multi-vault-bottleneck-corrections.md](./adr/ADR-002-multi-vault-bottleneck-corrections.md) — vault_id partitioning + Class A/B/C layering
  - [scripts/wiki_skills/wiki_enrich.py](../scripts/wiki_skills/wiki_enrich.py) — only in-repo consumer of wiki-ingest; primary refactor target

- **Decisions carried forward from Tasks 001/002/003:**
  - **Decision-1 (2026-05-25)**: Option I (Wrap + Index) — `wiki-ingest` owns file synthesis; this repo owns SQLite index. ADR-001.
  - **Decision-2 (2026-05-26)**: Single global DB with `vault_id` partitioning. ADR-002.
  - **Decision-3 (2026-05-26)**: `vault_id` REQUIRED explicit. ADR-002 §D1.1.
  - **Decision-4 (2026-05-26)**: Data Layering Contract — Class A / B / C. ADR-002 §D8.
  - **Decision-5 (2026-05-27)**: UC-06/UC-07 superseded by `/wiki-enrich`. R-06.3 and R-24 SUPERSEDED.
  - **Decision-6 (2026-05-27)**: `wiki-extract-concepts` lives in this repo (not a separate package).
  - **Decision-7 (2026-05-27)**: Ship R-3 only for TASK 003; R-4/R-5 deferred.
  - **Decision-8 (2026-05-27)**: `wiki-extract-concepts` writes concept files itself; emits manifest for `/wiki-enrich` index-only upsert. ADR-001 clarified.
  - **Decision-9 (2026-05-27)**: `--manifest-file`/`--manifest-stdin` on `wiki-enrich` is in scope for TASK 003 (paused — I-7.15). NOT touched by TASK 004.
  - **Decision-10 (2026-05-27)**: LLM `source_span` format is `"L12-L18"` (TASK 003).

- **New decisions for TASK 004:**
  - **Decision-11 (2026-05-27)**: Option 5 Python-import-only vendor chosen. Seven options were scored on five criteria (install friction, maintenance overhead, runtime performance, backward compat, publication readiness). Option 5 scored highest: it eliminates the PATH dependency for end-users (enabling PyPI/plugin publication), preserves the standalone `wiki-ingest` CLI for simple-wiki users, avoids subprocess JSON round-trips in the primary path, and keeps the maintenance surface minimal (snapshot copy + sync script). Options 1-4 (submodule, monorepo, package dep, pip-only) all introduce either install friction or coupling issues; Options 6-7 (rewrite or removal) violate the standalone-CLI preservation requirement.
  - **Decision-12 (2026-05-27)**: Vendored copy is a **snapshot**, not auto-synced. Refresh policy: manual `scripts/sync_wiki_ingest.sh` invocation only (rsync + hash check). Fixes go upstream first (Universal-skills wiki-ingest), then sync down via the script. Divergent forks in the vendored copy are prohibited — the sync script must fail with a diff warning if local modifications are detected before overwriting.
  - **Decision-13 (2026-05-27)**: Vendored module exposes a programmatic Python function `ingest(source: Path, vault: Path, vault_id: str | None = None, source_hash: str | None = None, known_concepts: list[dict] | None = None, dry_run: bool = False, timeout_seconds: int = 600) -> dict`. Returns a manifest dict (NOT a JSON string). The function raises `IngestError` (a new exception class in the vendored module's public surface) on failures rather than calling `sys.exit()`. CLI in standalone wiki-ingest continues to serialise the dict to JSON via the existing `_emit()` path; in-process callers consume the dict directly. Exact type signature to be finalised in Architecture Phase, but the parameter surface is stable enough for RTM and issue scoping.
  - **Decision-14 (2026-05-27)**: `wiki-enrich --source` keeps subprocess fallback path. Primary path: `try: from scripts.wiki_ingest.commands.ingest import ingest as _vendored_ingest; call _vendored_ingest(...)`. Fallback path (if vendored import raises `ImportError` AND `shutil.which("wiki-ingest")` is not None): existing subprocess flow. Operator can force-disable in-process via `WIKI_ENRICH_NO_VENDORED=1` env var. Fallback is silent (no user-visible warning unless `--verbose` or DEBUG log level). `check_wiki_ingest_version()` is called only on the fallback subprocess path.

---

### 1. General Description

#### 1.1 Goal

Vendor the `wiki-ingest` Python module into this repository so that `obsidian-llm-wiki` becomes a **self-contained product** — no external `wiki-ingest` installation required. This unblocks the 1-3 month publication target (PyPI / GitHub plugin / Claude Code plugin marketplace), where two-repo installs are unacceptable for end-users.

The approach (Decision-11) copies only the Python package (`wiki_ingest/` including `commands/`) from the upstream repo into `scripts/wiki_ingest/`, then extracts a programmatic `ingest()` function from the subcommand's `execute()` logic so that `wiki_enrich.py` can call it in-process. The external `wiki-ingest` CLI remains intact in Universal-skills for standalone ("simple wiki") users.

#### 1.2 Scope

**In scope:**

- Copy `Universal-skills/skills/wiki-ingest/scripts/wiki_ingest/` (the Python package) into `obsidian-llm-wiki/scripts/wiki_ingest/`. Subdirectory `commands/` included. `__pycache__/` excluded.
- Expose a programmatic `ingest()` function from the vendored module (Decision-13). This requires refactoring `execute()` in `commands/ingest.py` to separate the `sys.exit()` / argparse side-effects from the core pipeline logic.
- Refactor `scripts/wiki_skills/wiki_enrich.py`: primary code path uses the vendored in-process import; subprocess fallback retained (Decision-14). `check_wiki_ingest_version()` demoted to fallback-only guard.
- `bin/wiki-enrich` launcher: remove the hard requirement for `wiki-ingest` on PATH (the in-process path succeeds without it).
- `scripts/sync_wiki_ingest.sh`: rsync-based snapshot refresh from configurable source path (default `../../Universal-skills/skills/wiki-ingest/scripts/wiki_ingest/`). Writes `scripts/wiki_ingest/VENDORED_FROM.md` recording the source commit SHA and sync timestamp. Detects local divergence before overwriting.
- Tests: replace subprocess mocks in `tests/test_wiki_enrich.py` with vendored-module function mocks; add test cases for `WIKI_ENRICH_NO_VENDORED=1` escape hatch and the subprocess fallback path.
- `mypy --strict` compliance for `scripts/wiki_ingest/` after copy. Budget time for type-annotation cleanup if upstream is loose.
- Documentation: README install steps simplified (no more `ln -s wiki-ingest`); ARCHITECTURE.md §1.5.2 cross-process diagram updated to in-process flow; `THIRD_PARTY_NOTICES.md` updated to credit upstream wiki-ingest.

**Out of scope (explicit non-goals):**

- Do NOT implement `wiki-enrich --manifest-stdin` / `--manifest-file` flag (R-44, I-7.15 — TASK 003 paused; that's TASK 003's work on resume).
- Do NOT touch `summarizing-meetings` or `transcript-fetcher` skills (Universal-skills, out of scope).
- Do NOT publish to PyPI (that is TASK 005 or later).
- Do NOT refactor anything outside `wiki_enrich.py`, `tests/test_wiki_enrich.py`, and the vendored module itself.
- Do NOT delete or modify `Universal-skills/skills/wiki-ingest/` in any way.
- Do NOT introduce `--manifest-stdin` or `--manifest-file` flag changes to `wiki-enrich`'s argparse surface. The `--source` flag surface is unchanged; mutual-exclusion with manifest flags is TASK 003's responsibility.

#### 1.3 Context: upstream ingest module anatomy

The upstream `wiki_ingest/commands/ingest.py` has a fully implemented pipeline (Phase 2 complete as of 2026-05-27). Key points that affect the programmatic API design:

- `execute(args: argparse.Namespace)` is the current entry point. It calls `_safety.die()` on errors, which calls `sys.exit()`. The programmatic API must refactor this so errors raise `IngestError` instead.
- The pipeline supports "summary-passthrough" only (source must have `type: summary|lesson-summary|meeting-summary` in frontmatter). Raw transcripts without a pre-existing summary type cause exit with `SOURCE_NEEDS_SUMMARIZATION`. The vendored `ingest()` function must document this constraint.
- `_run_pipeline()` composes `register-summary → upsert-page × N → update-index → append-log → log-event` via `_dispatch.dispatch()`. These are in-process calls to other command modules. This pipeline is usable as-is when imported.
- The module uses only stdlib plus the `wiki_ingest` package itself (no external pip deps in the command layer). This simplifies vendoring.

---

### 2. Requirements Traceability Matrix (RTM)

> Numbering continues after R-44 (last requirement in TASK 003).

| ID | Requirement | Status | Acceptance Bullets |
|---|---|---|---|
| **R-45** | Vendor copy: `wiki_ingest/` Python package present at `scripts/wiki_ingest/` | planned | (a) `scripts/wiki_ingest/__init__.py` exists and is importable from the repo's Python path; (b) `scripts/wiki_ingest/commands/` subdirectory present with all subcommand modules; (c) No `__pycache__/` present in the committed copy; (d) `scripts/wiki_ingest/VENDORED_FROM.md` exists with `source_commit`, `synced_at`, and `source_path` fields; (e) `from scripts.wiki_ingest.commands.ingest import ingest` succeeds in the repo's `.venv` |
| **R-46** | Programmatic `ingest()` function exposed from vendored module | planned | (a) `scripts/wiki_ingest/commands/ingest.py` exports a top-level `ingest(source, vault, ...)` function per Decision-13 signature; (b) Function returns a `dict` matching the v1.1 manifest schema on success; (c) Function raises `IngestError` (importable from `scripts.wiki_ingest.commands.ingest`) on all failure modes — no `sys.exit()` in the function call graph; (d) `IngestError` carries `code: str`, `phase: str | None`, `written_so_far: list[dict]` attributes for structured error handling; (e) `execute(args)` (the CLI entry point for the `register` / argparse path) continues to work by calling `ingest()` internally and converting `IngestError` to `_safety.die()` |
| **R-47** | `wiki_enrich.py` primary path: in-process vendored import | planned | (a) On `--source` invocation with vendored module importable and `WIKI_ENRICH_NO_VENDORED` unset: `subprocess.run(["wiki-ingest", ...])` is NOT called; (b) `check_wiki_ingest_version()` is NOT called on the in-process path; (c) Manifest dict returned by vendored `ingest()` is consumed by the existing `_validate_manifest()` and `index_from_manifest()` without modification to those functions; (d) Combined output JSON `{"action":"enriched", ...}` is identical in structure to the existing subprocess-based output |
| **R-48** | `wiki_enrich.py` subprocess fallback path retained | planned | (a) When `WIKI_ENRICH_NO_VENDORED=1` env var is set, the in-process path is skipped and the subprocess path is used; (b) When the vendored import raises `ImportError` AND `wiki-ingest` is on PATH, the subprocess fallback activates silently; (c) When the vendored import raises `ImportError` AND `wiki-ingest` is NOT on PATH, a clear error is emitted (`WIKI_INGEST_UNAVAILABLE`) with instructions; (d) `check_wiki_ingest_version()` is called on the subprocess path as before |
| **R-49** | `scripts/sync_wiki_ingest.sh` snapshot sync script | planned | (a) Script accepts optional `--source <path>` flag (default: `../../Universal-skills/skills/wiki-ingest/scripts/wiki_ingest/`); (b) **Divergence-check mechanism**: SHA256-content-hash of each vendored `*.py` file recorded in `VENDORED_FROM.md::file_hashes` block at sync time; pre-sync the script recomputes hashes and aborts with a per-file diff list if any vendored file's hash diverges from the recorded value (operator must have either explicitly added it to `local_patches` or run with `--accept-local-divergence`); chosen over git-diff because it works regardless of whether the operator commits between syncs and does not assume the source path is a git checkout; (c) After sync, updates `VENDORED_FROM.md` with current source `git rev-parse HEAD` SHA (if source is a git checkout, else "non-git"), ISO-8601 timestamp, and refreshed `file_hashes` block; (d) Excludes `__pycache__/` and `.pyc` files from rsync; (e) Script is executable and runnable with `bash scripts/sync_wiki_ingest.sh`; (f) Dry-run mode: `--dry-run` prints what would be synced without modifying any files |
| **R-50** | `mypy --strict` clean for `scripts/wiki_ingest/` | planned | (a) `mypy --strict scripts/wiki_ingest/` exits 0 after vendoring; (b) Any type-annotation gaps found in the upstream module are fixed in the vendored copy (documented in a comment referencing the upstream source line); (c) Any such local fixups are tracked as divergent-patches and noted in `VENDORED_FROM.md` under a `local_patches` list so the sync script can warn before overwriting |
| **R-51** | Tests: vendored path and fallback path coverage | planned | (a) `tests/test_wiki_enrich.py` uses `unittest.mock.patch('scripts.wiki_skills.wiki_enrich._vendored_ingest')` (or equivalent) instead of subprocess mocks for the primary-path tests; (b) New test: `WIKI_ENRICH_NO_VENDORED=1` forces subprocess path — assert `subprocess.run` is called and vendored function is NOT called; (c) New test: vendored import raises `ImportError` + `wiki-ingest` on PATH → subprocess fallback activates; (d) New test: vendored import raises `ImportError` + `wiki-ingest` NOT on PATH → `WIKI_INGEST_UNAVAILABLE` error emitted, exit 6; (e) All existing 295+ tests continue to pass |
| **R-52** | `bin/wiki-enrich` launcher no longer requires `wiki-ingest` on PATH | planned | (a) Invoking `wiki-enrich --vault V --vault-root P --source S` with `wiki-ingest` absent from PATH succeeds (exit 0) when vendored path works; (b) `bin/wiki-enrich` does NOT perform a `which wiki-ingest` guard at the launcher level |
| **R-53** | README and install documentation simplified | planned | (a) README `## Installation` section no longer lists `ln -s wiki-ingest` step as required; (b) README notes `wiki-ingest` on PATH is optional (enables subprocess fallback, useful for debugging); (c) Any quick-start recipe that used `wiki-ingest` as a required prerequisite is updated |
| **R-54** | ARCHITECTURE.md §1.5.2 updated to reflect in-process flow | planned | (a) The cross-process ASCII diagram in §1.5.2 is replaced or supplemented with an in-process flow diagram showing vendored import path; (b) The subprocess path is shown as "fallback (disabled by default when vendored module present)"; (c) §1.5.3 note updated: "external `wiki-ingest` binary: no longer required for standard operation; vendored copy at `scripts/wiki_ingest/` is primary" |
| **R-55** | `THIRD_PARTY_NOTICES.md` credits upstream wiki-ingest | planned | (a) File `THIRD_PARTY_NOTICES.md` created (or updated if exists) with: project name (`wiki-ingest`), upstream repo URL (`Universal-skills/skills/wiki-ingest`), **SPDX license identifier** copied verbatim from upstream `LICENSE` file (or `"NOASSERTION — operator-owned, internal"` if upstream has no LICENSE — Architect to confirm) so a future fork or open-source release has a clean license posture; operator-owner note (no licensing friction today); snapshot SHA and sync date; (b) If upstream `LICENSE` file exists, copy it verbatim to `scripts/wiki_ingest/LICENSE-upstream` for unambiguous provenance; (c) The notices file and any copied LICENSE are committed alongside the vendored copy |
| **R-56** | TASK 003 interface contracts preserved; no surface breakage for TASK 003 resume | planned | (a) `wiki_enrich.py` `--source` flag remains `required=True` (no mutual-exclusion group introduced — that is I-7.15 / TASK 003 scope); (b) `index_from_manifest()` and `_validate_manifest()` signatures unchanged; (c) `WikiIngestError` exception class preserved (used by subprocess fallback path); (d) All existing `--ingest-arg` passthrough behavior preserved on the subprocess fallback path |
| **R-57** | Standalone `wiki-ingest` CLI behavior unchanged (preserve "simple wiki" users per operator requirement) | planned | (a) `python -m scripts.wiki_ingest.commands.ingest --source <X> --vault <Y> [--output-format json]` (vendored copy, invoked as CLI module) exits 0 on the happy path and emits the v1.1 manifest to stdout, mirroring upstream `execute()` behavior — proves `execute()` wrapper around `ingest()` did not regress the CLI surface; (b) Upstream `Universal-skills/skills/wiki-ingest/scripts/wiki-ingest ingest --source X --vault Y` continues to work independently (no edits made to Universal-skills repo in this task — verifiable by `git status` in that repo); (c) Smoke 4 in §7 exercises (a) explicitly |

---

### 3. Issues (Atomic Implementation Units)

Prefix `I-V.x` denotes "vendoring" issues.

#### Epic EV: wiki-ingest vendoring

- **I-V.1** Create `scripts/wiki_ingest/` directory structure by copying the upstream package. Run `scripts/sync_wiki_ingest.sh --source <path-to-upstream>` (or manually rsync for bootstrap). Verify `from scripts.wiki_ingest.commands.ingest import execute` succeeds. Create `scripts/wiki_ingest/VENDORED_FROM.md` stub. → R-45

- **I-V.2** Write `scripts/sync_wiki_ingest.sh`. Implement: source-path resolution, divergence check (git diff against recorded commit SHA), rsync with exclude list, `VENDORED_FROM.md` update. Add `--dry-run` flag. Make executable. → R-49

- **I-V.3** Programmatic API extraction in vendored `scripts/wiki_ingest/commands/ingest.py`. Define `class IngestError(Exception)` with `code`, `phase`, `written_so_far` attributes. Refactor `execute(args)` to call a new top-level `ingest(source, vault, vault_id, source_hash, known_concepts, dry_run, timeout_seconds) -> dict` function. Inside `ingest()`: replace all `_safety.die(...)` calls with `raise IngestError(...)`. `execute()` wraps `ingest()` and catches `IngestError`, calling `_safety.die()` to preserve CLI behavior. Ensure `argparse.Namespace` is no longer passed into `ingest()` — all params are explicit keyword arguments. → R-46

- **I-V.4** `mypy --strict scripts/wiki_ingest/` pass. Identify and fix all type annotation gaps in the vendored copy. Document each local patch in a comment block `# VENDORED-PATCH:` and list in `VENDORED_FROM.md::local_patches`. Goal: zero mypy errors. **Time-box**: if cumulative type-fixup exceeds 2 hours, switch strategy — add minimal `# type: ignore[<error>]` comments with an `UPSTREAM-ISSUE:` referee link and file an issue on the Universal-skills/wiki-ingest tracker rather than continuing to deep-fix in the vendored copy. Goal of the time-box: prevent vendoring task from being held hostage by upstream typing debt. → R-50

- **I-V.5** Refactor `scripts/wiki_skills/wiki_enrich.py` primary path. At module level (lazy import, inside the function): `try: from scripts.wiki_ingest.commands.ingest import ingest as _vendored_ingest, IngestError as _VendoredIngestError; _VENDORED_AVAILABLE = True` / `except ImportError: _VENDORED_AVAILABLE = False`. In `main()`: check `os.environ.get("WIKI_ENRICH_NO_VENDORED") != "1"` AND `_VENDORED_AVAILABLE` → call `_vendored_ingest(source=source, vault=vault_root, vault_id=args.vault, ...)`. On `IngestError`: emit structured error and exit 6. Subprocess path: existing flow (now guarded by `not _VENDORED_AVAILABLE or WIKI_ENRICH_NO_VENDORED`). → R-47, R-48

- **I-V.6** Update `bin/wiki-enrich` launcher. Remove any `which wiki-ingest || exit` guard if present. Confirm the launcher works without `wiki-ingest` on PATH when the vendored path is active. → R-52

- **I-V.7** Update tests in `tests/test_wiki_enrich.py`. Replace subprocess mocks (`subprocess.run`) with `unittest.mock.patch` on the vendored `ingest` import for primary-path tests. Add three new test cases: `WIKI_ENRICH_NO_VENDORED=1` triggers subprocess; `ImportError` on vendored import with `wiki-ingest` on PATH triggers subprocess; `ImportError` on vendored import with `wiki-ingest` absent triggers `WIKI_INGEST_UNAVAILABLE`. → R-51

- **I-V.8** Update README installation section. Remove `wiki-ingest` symlink from required install steps; note optional PATH presence as a fallback/debug mechanism. → R-53

- **I-V.9** Update ARCHITECTURE.md §1.5.2 and §1.5.3. Replace the cross-process flow diagram with an in-process flow diagram. Add a note in §1.5.3 about the vendored copy at `scripts/wiki_ingest/`. → R-54

- **I-V.10** Create `THIRD_PARTY_NOTICES.md`. Include: project name (`wiki-ingest`), upstream repo path (`Universal-skills/skills/wiki-ingest`), operator ownership note, snapshot commit SHA (from `VENDORED_FROM.md`), sync date. → R-55

- **I-V.11** Regression sweep: run `pytest tests/ -q` (all 295+ tests green); run `mypy --strict scripts/` (full tree, not just vendored subdirectory); manually verify smoke recipe from §7 (Smokes 1-4). → R-51, R-50, R-57, all RTM rows

---

### 4. Use Cases

#### UC-V1: Operator updates vendored snapshot via sync script

**Actors:** Operator (developer of this repo), `scripts/sync_wiki_ingest.sh`, git.

**Preconditions:**
- The upstream `Universal-skills/skills/wiki-ingest/` repo has received a bug fix or feature update.
- The vendored `scripts/wiki_ingest/` exists with `VENDORED_FROM.md` recording the prior snapshot SHA.
- No local divergent patches have been made to the vendored copy (or operator is aware of them).

**Main Scenario:**
1. Operator: runs `bash scripts/sync_wiki_ingest.sh` (optionally with `--dry-run` first).
2. Script: reads `VENDORED_FROM.md` to get the prior `source_commit` SHA.
3. Script: checks for local modifications in `scripts/wiki_ingest/` (git diff or content hash comparison) against the recorded SHA. No divergence found → proceed.
4. Script: rsyncs `Universal-skills/skills/wiki-ingest/scripts/wiki_ingest/` → `scripts/wiki_ingest/` excluding `__pycache__/` and `*.pyc`.
5. Script: runs `git rev-parse HEAD` in the upstream source path and writes the new SHA + timestamp to `VENDORED_FROM.md`.
6. Operator: runs `mypy --strict scripts/wiki_ingest/` to verify no new type errors introduced by the upstream delta.
7. Operator: runs `pytest tests/ -q` to verify no regressions.
8. Operator: commits the updated vendored copy and `VENDORED_FROM.md`.

**Alternative Scenarios:**
- **A1: Local divergent patch detected** — Script prints diff of local changes vs upstream; exits non-zero with instructions to either discard local changes or move them upstream first. No rsync performed.
- **A2: `--dry-run` flag** — Script prints what would be rsynced without modifying any files. Operator reviews and re-runs without flag.
- **A3: Source path not found** — Script exits with "upstream source directory not found at `<path>`; pass `--source <path>` to override."

**Postconditions:**
- `scripts/wiki_ingest/` reflects the upstream state at the recorded commit SHA.
- `VENDORED_FROM.md` updated with new SHA and timestamp.
- All existing tests pass.

**Acceptance Criteria (RTM rows: R-49, R-45):**
- `VENDORED_FROM.md` contains `source_commit`, `synced_at`, `source_path` fields after sync.
- Re-running the sync script immediately produces "no changes" (idempotent).
- `--dry-run` produces no file mutations.
- Injecting a local modification to a vendored file causes the script to print a diff and exit non-zero.

---

#### UC-V2: End-user installs via single command, no external wiki-ingest required

**Actors:** End-user (new operator of obsidian-llm-wiki), Python package installer, shell.

**Preconditions:**
- `obsidian-llm-wiki` is cloned or installed (future: via `pip install obsidian-llm-wiki` in TASK 005).
- `wiki-ingest` is NOT installed and NOT on PATH.
- A target vault exists with a valid `WIKI_SCHEMA.md` including `vault_id`.

**Main Scenario:**
1. End-user: installs this repo per README (clone + `pip install -r requirements.txt` or future `pip install obsidian-llm-wiki`).
2. End-user: runs `wiki-enrich --vault my-vault --vault-root /path/to/vault --source /path/to/raw-summary.md`.
3. System: attempts vendored in-process import (`from scripts.wiki_ingest.commands.ingest import ingest`). Succeeds.
4. System: calls `ingest(source=..., vault=..., vault_id='my-vault', ...)` in-process. Returns manifest dict.
5. System: validates manifest; calls `index_from_manifest()`; appends log event.
6. System: emits `{"action": "enriched", "vault_id": "my-vault", "ingest": {...}, "index": {...}}`.
7. End-user: verifies `wiki-search --vault my-vault "keyword"` returns the ingested page.

**Alternative Scenarios:**
- **A1: Vendored ingest raises `IngestError` (e.g., source type mismatch)** — `wiki-enrich` emits `{"error": "WIKI_INGEST_FAILED", "code": "SOURCE_NEEDS_SUMMARIZATION", ...}`, exit 6. No subprocess fallback attempted (the error is from the content, not from the import path).
- **A2: `WIKI_ENRICH_NO_VENDORED=1` set for debugging** — subprocess path is attempted; fails with clear error since `wiki-ingest` is not on PATH; user is instructed to unset the env var.

**Postconditions:**
- At least one page upserted in SQLite.
- `log_events` table has a new row for this ingest.
- End-user can find the ingested content via `wiki-search`.

**Acceptance Criteria (RTM rows: R-45, R-46, R-47, R-52, R-53):**
- With `wiki-ingest` absent from PATH: `wiki-enrich --vault V --vault-root P --source S` exits 0.
- `shutil.which("wiki-ingest")` = None in the test environment.
- `pytest tests/test_wiki_enrich.py -k "test_in_process_no_subprocess"` passes (new test validating this scenario).

---

### 5. Schema and API Impact

#### 5.1 No DB schema changes

TASK 004 is entirely at the transport layer. No new tables, no column changes, no migration scripts required. The SQLite schema remains at the Phase 3a state (SCHEMA-v2.sql).

#### 5.2 New Python module: `scripts/wiki_ingest/`

After vendoring, the directory layout is:

```text
scripts/wiki_ingest/
├── __init__.py               — package init; re-exports __version__ = "1.1.0" (snapshot version)
├── VENDORED_FROM.md          — provenance metadata (not a Python module; gitignore-exempt)
├── _classify.py
├── _dispatch.py
├── _frontmatter.py
├── _markdown.py
├── _page_merge.py
├── _safety.py
├── _vault.py
└── commands/
    ├── __init__.py
    ├── append_log.py
    ├── classify_folder.py
    ├── demote.py
    ├── find.py
    ├── ingest.py             — PRIMARY REFACTOR TARGET (I-V.3): adds IngestError + ingest() fn
    ├── init.py
    ├── lint.py
    ├── log_event.py
    ├── promote.py
    ├── reindex.py
    ├── register_summary.py
    ├── scan.py
    ├── update_index.py
    └── upsert_page.py
```

#### 5.3 Programmatic API: proposed `ingest()` function signature

```python
# scripts/wiki_ingest/commands/ingest.py (vendored + refactored)

class IngestError(Exception):
    """Raised by ingest() on all failure modes (replaces _safety.die() calls).

    Attributes:
        message:        human-readable failure description (positional Exception arg)
        code:           error code string (e.g. "SOURCE_NEEDS_SUMMARIZATION")
        phase:          pipeline phase where failure occurred (e.g. "register-summary"),
                        or None if failure was pre-pipeline (validation)
        written_so_far: list of written-entry dicts (partial success state)
        child_exit_code: original exit code from a dispatched atomic op (0 if not applicable)
    """
    def __init__(
        self,
        message: str,
        code: str,
        phase: str | None = None,
        written_so_far: list[dict] | None = None,
        child_exit_code: int = 0,
    ) -> None: ...

def ingest(
    source: Path,
    vault: Path,
    vault_id: str | None = None,
    source_hash: str | None = None,
    known_concepts: list[dict] | None = None,
    dry_run: bool = False,
    timeout_seconds: int = 600,
    quiet: bool = True,
) -> dict:
    """Run the wiki-ingest pipeline in-process. Returns a v1.1 manifest dict.

    Args:
        source:           Absolute path to the raw input (must have type: summary|...).
        vault:            Absolute path to vault root or course root.
        vault_id:         Optional strict-mode vault ID; if given, must match WIKI_SCHEMA.md.
        source_hash:      Optional pre-computed sha256-hex of source bytes (idempotency).
        known_concepts:   Optional list of known-concept dicts [{slug, name, aliases}].
                          Currently decorative (wiki-ingest v1.1 summary-passthrough scope);
                          will be consumed when synthesiser-subagent integration lands.
        dry_run:          If True, no filesystem writes; manifest reflects what would happen.
        timeout_seconds:  Reserved; not enforced in-process (no subprocess to bound).
        quiet:            Suppress human-readable stdout lines. Default True for programmatic use.

    Returns:
        dict: v1.1 manifest with status="ok", written[], log_event, etc.
              If source was already ingested (idempotency short-circuit):
              returns manifest with status="ok", action="unchanged", written=[].

    Raises:
        IngestError: on any failure (invalid source, vault not found, pipeline step failure).
    """
    ...
```

**Notes on the signature:**

- `known_concepts` is marked decorative for v1.1 (upstream is summary-passthrough; LLM synthesis is not in the current `execute()` path). It is included in the signature now so callers (TASK 003 `wiki-extract-concepts`) do not need a breaking change when upstream adds synthesiser integration.
- `timeout_seconds` is also decorative in the in-process path (no subprocess to bound). Retained for interface symmetry with the subprocess path.
- The function is NOT async. The pipeline is synchronous filesystem I/O + in-process dispatches.

---

### 6. Architecture Impact

TASK 004 collapses the cross-process hop in §1.5.2 to an in-process call. The Architecture Phase will update ARCHITECTURE.md §1.5.2 with the revised flow diagram. No new DAL methods, no new DB tables, no new skill manifests. The vendored module is an internal implementation detail of `wiki_enrich.py`, not a new user-facing skill.

The symlink graph in §1.5.5 loses `~/.local/bin/wiki-ingest` as a required link. It becomes optional (enables subprocess fallback for operators who want it).

---

### 7. Acceptance Criteria (End-to-End Smoke Recipe)

The following recipe constitutes the TASK 004 gate. Run against any registered vault (e.g., `trade-agents`):

```bash
# Prerequisites: inside obsidian-llm-wiki repo, .venv activated.
source .venv/bin/activate
export VAULT=trade-agents
export VAULT_ROOT=/path/to/trade-agents
export SOURCE=/path/to/a-prebuilt-summary.md   # type: summary or lesson-summary in frontmatter

# --- Smoke 1: in-process path works WITHOUT wiki-ingest on PATH ---
# Remove wiki-ingest from PATH for this test (or unset symlink temporarily)
export PATH_SAVED="$PATH"
export PATH="$(echo $PATH | tr ':' '\n' | grep -v wiki-ingest | tr '\n' ':')"
which wiki-ingest 2>/dev/null && echo "FAIL: wiki-ingest still on PATH" || echo "OK: wiki-ingest absent"

wiki-enrich --vault "$VAULT" --vault-root "$VAULT_ROOT" --source "$SOURCE" \
  | python -c "
import json, sys
result = json.load(sys.stdin)
assert result['action'] == 'enriched', f'Expected enriched, got: {result}'
assert result['vault_id'] == '$VAULT', f'vault_id mismatch: {result}'
assert isinstance(result['index']['upserted'], list), 'upserted must be a list'
print(f'Smoke 1 PASS: in-process path enriched {len(result[\"index\"][\"upserted\"])} pages')
"
# Expected: Smoke 1 PASS: in-process path enriched N pages
echo "wiki-enrich exit code: $?"
# Expected: 0

# --- Smoke 2: subprocess fallback path works WITH wiki-ingest on PATH ---
export PATH="$PATH_SAVED"
which wiki-ingest  # confirm it's back
WIKI_ENRICH_NO_VENDORED=1 wiki-enrich --vault "$VAULT" --vault-root "$VAULT_ROOT" \
  --source "$SOURCE" \
  | python -c "
import json, sys
result = json.load(sys.stdin)
assert result['action'] in ('enriched', 'partial'), f'Unexpected: {result}'
print('Smoke 2 PASS: subprocess fallback works')
"
# Expected: Smoke 2 PASS: subprocess fallback works

# --- Smoke 3: ImportError path emits WIKI_INGEST_UNAVAILABLE ---
# Temporarily break the vendored import by renaming the package
trap 'mv scripts/wiki_ingest_bak scripts/wiki_ingest 2>/dev/null' EXIT
mv scripts/wiki_ingest scripts/wiki_ingest_bak
PATH_NO_INGEST="$(echo $PATH | tr ':' '\n' | grep -v wiki-ingest | tr '\n' ':')"
PATH="$PATH_NO_INGEST" wiki-enrich --vault "$VAULT" --vault-root "$VAULT_ROOT" \
  --source "$SOURCE" \
  | python -c "
import json, sys
result = json.load(sys.stdin)
assert 'error' in result, f'Expected error envelope, got: {result}'
print(f'Smoke 3 PASS: error code = {result[\"error\"]}')
"
mv scripts/wiki_ingest_bak scripts/wiki_ingest
trap - EXIT
# Expected: Smoke 3 PASS: error code = WIKI_INGEST_UNAVAILABLE

# --- Smoke 4: standalone CLI surface preserved (R-57) ---
# Vendored ingest, invoked as a CLI module, still works — proves execute() wrapper
# around ingest() did not regress the CLI surface.
python -m scripts.wiki_ingest.commands.ingest \
  --source "$SOURCE" --vault "$VAULT_ROOT" --output-format json \
  | python -c "
import json, sys
m = json.load(sys.stdin)
assert m['status'] == 'ok', f'Unexpected: {m}'
print('Smoke 4 PASS: standalone CLI surface intact')
"
# Expected: Smoke 4 PASS: standalone CLI surface intact

# --- Smoke 5: mypy --strict clean ---
mypy --strict scripts/wiki_ingest/
# Expected: Success: no issues found
mypy --strict scripts/wiki_skills/wiki_enrich.py
# Expected: Success: no issues found

# --- Smoke 6: full test suite green ---
pytest tests/ -q
# Expected: 298+ passed (295 baseline + >=3 new tests), 0 failed

# --- Smoke 7: sync script dry-run is non-destructive ---
bash scripts/sync_wiki_ingest.sh --dry-run \
  --source ../../Universal-skills/skills/wiki-ingest/scripts/wiki_ingest/
# Expected: prints list of would-be-synced files; no file mutations;
#           "Dry run complete. Re-run without --dry-run to apply."

# --- Smoke 7: VENDORED_FROM.md has required fields ---
python -c "
import re
text = open('scripts/wiki_ingest/VENDORED_FROM.md').read()
for field in ('source_commit', 'synced_at', 'source_path'):
    assert field in text, f'Missing field: {field}'
print('Smoke 7 PASS: VENDORED_FROM.md fields present')
"
# Expected: Smoke 7 PASS
```

---

### 8. Resolved Decisions (2026-05-27)

All blocking questions raised during operator brainstorming have been resolved. No blocking questions remain before Architecture Phase.

| Q | Resolution | Encoded in |
|---|---|---|
| **Q1 — Which of the 7 options?** | Option 5 Python-import-only vendor (Decision-11) | Decision-11, R-45..R-48 |
| **Q2 — Standalone wiki-ingest preserved?** | Yes — Universal-skills repo unchanged (Decision-12) | Decision-12, R-49 scope (out) |
| **Q3 — Programmatic API: exact signature** | `ingest(source, vault, vault_id, source_hash, known_concepts, dry_run, timeout_seconds, quiet) -> dict` + `IngestError` (Decision-13) | Decision-13, R-46, §5.3 |
| **Q4 — Subprocess fallback preserved?** | Yes — guarded by `WIKI_ENRICH_NO_VENDORED=1` and ImportError detection (Decision-14) | Decision-14, R-47, R-48, I-V.5 |
| **Q5 — TASK 003 surface preservation** | `--source` remains `required=True`; no mutual-exclusion group introduced (TASK 003's job) | Decision-9 (carried), R-56 |
| **Q6 — `execute()` CLI path preserved?** | Yes — `execute()` wraps `ingest()` and converts `IngestError` to `_safety.die()` | R-46(e), I-V.3 |

---

### 9. Task-Review Self-Checklist

- [x] Every RTM row (R-45..R-57) has at least one Issue (I-V.1..I-V.11) and at least one acceptance bullet.
- [x] No RTM orphans: R-45→I-V.1, R-46→I-V.3, R-47→I-V.5, R-48→I-V.5, R-49→I-V.2, R-50→I-V.4, R-51→I-V.7, R-52→I-V.6, R-53→I-V.8, R-54→I-V.9, R-55→I-V.10, R-56→I-V.11, R-57→I-V.11 (Smoke 4 verification).
- [x] UC-V1 cites R-49, R-45. UC-V2 cites R-45, R-46, R-47, R-52, R-53.
- [x] Decisions 11-14 each have a corresponding RTM row: D-11→R-45/R-46/R-47, D-12→R-49, D-13→R-46, D-14→R-47/R-48.
- [x] No contradiction with TASK 003 paused state: `--manifest-stdin`/`--manifest-file` (R-44, I-7.15) NOT touched; `--source` argparse surface NOT modified. R-56 explicitly enforces this boundary.
- [x] Scope (out) section explicitly calls out `--manifest-stdin`/`--manifest-file` as TASK 003's work.
- [x] `IngestError` attributes match the upstream `_PartialFailure` pattern so callers have structured error state.
- [x] Smoke recipe covers: in-process path (wiki-ingest absent), subprocess fallback (NO_VENDORED env), unavailable-both error, mypy, pytest, sync script dry-run, VENDORED_FROM.md fields.
