# Task 004-02: `scripts/sync_wiki_ingest.sh` snapshot sync script [STUB + LOGIC]

## Meta

- **Bead ID**: `task-004-02-sync-script`
- **Slug**: `sync-script`
- **Maps to**: Issue **I-V.2**; RTM rows **R-49**
- **Depends on**: `task-004-01-vendor-bootstrap` (needs the `VENDORED_FROM.md` format established by I-V.1, especially the `file_hashes` block)
- **Estimated time**: 0.75 day
- **Priority**: High

## Use Case Connection

- **UC-V1**: Operator updates vendored snapshot via sync script (this bead **is** the script behind that UC).

## Task Goal

Implement `scripts/sync_wiki_ingest.sh` — a bash script that refreshes `scripts/wiki_ingest/` from a configurable upstream path (default: `../../Universal-skills/skills/wiki-ingest/scripts/wiki_ingest/`). The script must (a) detect local divergence by SHA256 hash comparison against `VENDORED_FROM.md::file_hashes` before overwriting, (b) support `--dry-run` (no mutations), (c) support `--source <path>` override, (d) support `--accept-local-divergence` escape hatch, (e) exclude `__pycache__/` and `*.pyc`, (f) rewrite `VENDORED_FROM.md` with new `source_commit`, `synced_at`, and refreshed `file_hashes` block on success.

## Stub-First Plan

**Phase 1 — Stub**:
1. Create `scripts/sync_wiki_ingest.sh` with shebang `#!/usr/bin/env bash`, `set -euo pipefail`, and a body that just prints `"NOT IMPLEMENTED — task-004-02 phase 1"` and `exit 0`.
2. `chmod +x scripts/sync_wiki_ingest.sh`.
3. Create `tests/test_sync_script.py::test_sync_script_stub_runs` — invokes `bash scripts/sync_wiki_ingest.sh --dry-run` via `subprocess.run`, asserts exit 0 and the stub message appears on stdout.

**Phase 2 — Logic**:
1. Implement argparse-equivalent: parse `--source <path>` (default), `--dry-run`, `--accept-local-divergence`, `--help`.
2. Read `scripts/wiki_ingest/VENDORED_FROM.md` and extract the `file_hashes` block.
3. For every `*.py` in `scripts/wiki_ingest/`: compute SHA256, compare against recorded hash. If any file diverges AND `--accept-local-divergence` is NOT set AND the file path is NOT in `local_patches` → print per-file diff list and exit 1.
4. Run `rsync -av --delete --exclude=__pycache__ --exclude='*.pyc' "$SOURCE_PATH/" scripts/wiki_ingest/` (or print the command on `--dry-run`).
5. Recompute file hashes after sync; if `--dry-run`, skip writing.
6. Rewrite `VENDORED_FROM.md` with: `source_commit = $(cd "$SOURCE_PATH/../.." && git rev-parse HEAD 2>/dev/null || echo "non-git")`, `synced_at = $(date -u +%Y-%m-%dT%H:%M:%SZ)`, refreshed `file_hashes` block. Preserve `local_patches` list verbatim.
7. Update `tests/test_sync_script.py` with 4 tests (see Test Surface).

## Changes Description

### New Files

- `scripts/sync_wiki_ingest.sh` (executable bash script, ~150 lines):
  - Shebang + `set -euo pipefail` + `umask 022`.
  - Default `SOURCE_PATH="$(dirname "$0")/../../Universal-skills/skills/wiki-ingest/scripts/wiki_ingest"`.
  - Argument parsing loop for `--source`, `--dry-run`, `--accept-local-divergence`, `--help`.
  - Divergence-check function: reads `VENDORED_FROM.md::file_hashes`, recomputes per-file SHA256, compares.
  - rsync invocation (with `--dry-run` flag passthrough).
  - `VENDORED_FROM.md` rewriter function.
- `tests/test_sync_script.py` (Python pytest file invoking the bash script via `subprocess.run`):
  - 4 test cases (see Test Surface).

### Changes in Existing Files

- None.

### Component Integration

- This bead is **standalone** — no Python import path depends on it. The script is invoked by operators (UC-V1) or via the I-V.11 regression sweep (Smoke 7).
- The hash-comparison format must match the one established in I-V.1's `VENDORED_FROM.md` (binary SHA256, no normalization).

## Files Touched (explicit list)

- `scripts/sync_wiki_ingest.sh` (new, executable)
- `tests/test_sync_script.py` (new)

## Test Surface

- **New**: `tests/test_sync_script.py`:
  1. `test_dry_run_no_mutations`: snapshot mtime of every file in `scripts/wiki_ingest/`; invoke `bash scripts/sync_wiki_ingest.sh --dry-run`; assert exit 0 + all mtimes unchanged.
  2. `test_dry_run_prints_would_be_synced`: stdout contains `"Dry run complete"` and the file list.
  3. `test_divergence_check_blocks_overwrite`: monkeypatch a single byte change in `scripts/wiki_ingest/_safety.py`, run without `--accept-local-divergence` → exit 1, stderr contains per-file diff entry.
  4. `test_accept_local_divergence_escape_hatch`: same as 3 but with `--accept-local-divergence` → exit 0 (rsync proceeds).
- **Optional additional unit**: `test_source_path_not_found`: invoke with `--source /nonexistent/path` → exit 1 with `"upstream source directory not found"` message.

## Acceptance

- [ ] R-49(a): Script accepts `--source <path>` flag with default `../../Universal-skills/skills/wiki-ingest/scripts/wiki_ingest/`.
- [ ] R-49(b): Divergence-check mechanism uses SHA256-content-hashes from `VENDORED_FROM.md::file_hashes`; aborts with per-file diff list when divergence detected (unless `--accept-local-divergence`).
- [ ] R-49(c): After successful sync, `VENDORED_FROM.md` updated with current `git rev-parse HEAD` SHA (or `"non-git"`), ISO-8601 timestamp, refreshed `file_hashes` block.
- [ ] R-49(d): rsync excludes `__pycache__/` and `*.pyc`.
- [ ] R-49(e): Script is executable (`chmod +x` applied) and runnable as `bash scripts/sync_wiki_ingest.sh`.
- [ ] R-49(f): `--dry-run` mode prints what would be synced without modifying any files (verified by mtime snapshot).
- [ ] All 4 new tests in `tests/test_sync_script.py` pass.
- [ ] Smoke 7 (from TASK.md §7) passes: `bash scripts/sync_wiki_ingest.sh --dry-run --source ...` exits 0 with the expected stdout.

## Rollback

`rm scripts/sync_wiki_ingest.sh tests/test_sync_script.py`. No other repo file is touched.

## Notes

- **Risk R-2 (divergence-check edge cases)**: hash computation MUST use binary read mode (`sha256sum` directly on the file, not via `cat | iconv`) to avoid trailing-newline / encoding sensitivity. Test 3 explicitly verifies a 1-byte change is detected.
- The `VENDORED_FROM.md` rewriter must preserve the `local_patches` block verbatim (I-V.4 populates it). Use a marker-based replace, not a full rewrite from scratch.
- The script is **idempotent** on a no-op sync (no upstream changes since last sync) — re-running immediately produces "no changes detected".
- Do NOT use `git` commands as a dependency for divergence detection (per Decision-12 + R-49(b) rationale: hash-based works regardless of git state).
