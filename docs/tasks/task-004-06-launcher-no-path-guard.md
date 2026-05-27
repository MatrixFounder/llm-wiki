# Task 004-06: `bin/wiki-enrich` launcher — drop `which wiki-ingest` guard [LOGIC]

## Meta

- **Bead ID**: `task-004-06-launcher-no-path-guard`
- **Slug**: `launcher-no-path-guard`
- **Maps to**: Issue **I-V.6**; RTM rows **R-52**
- **Depends on**: `task-004-05-wiki-enrich-refactor` (launcher behavior must follow `wiki_enrich.py` semantics)
- **Estimated time**: 0.1 day
- **Priority**: Medium

## Use Case Connection

- **UC-V2**: End-user installs via single command — the launcher must not pre-empt the in-process path with a PATH check.

## Task Goal

Inspect `bin/wiki-enrich` and remove any `which wiki-ingest || exit` or `command -v wiki-ingest || ...` guard if present. The launcher's job is to `cd` into the repo, source `.venv`, and `exec python -m scripts.wiki_skills.wiki_enrich "$@"`. The PATH check (if needed) belongs to the Python entry point's fallback path, not the bash launcher.

## Stub-First Plan

This bead is a single-line (or no-op) edit. No stub phase.

**Approach**:
1. `Read` `bin/wiki-enrich`. If a `which wiki-ingest` / `command -v wiki-ingest` guard is present, remove it.
2. Verify the launcher's body is now: shebang → `cd` to repo root → source `.venv/bin/activate` → `exec python -m scripts.wiki_skills.wiki_enrich "$@"`.
3. Smoke test: `PATH=$(echo $PATH | tr ':' '\n' | grep -v wiki-ingest | tr '\n' ':') bin/wiki-enrich --help` exits 0.

## Changes Description

### New Files

- None.

### Changes in Existing Files

#### File: `bin/wiki-enrich`

- Remove any `which wiki-ingest` / `command -v wiki-ingest` guard line(s) if present.
- Preserve: shebang, `cd "$(dirname "$0")/.."` (or equivalent), venv activation, `exec python -m scripts.wiki_skills.wiki_enrich "$@"`.

### Component Integration

- The launcher is one of the 4-file-of-same-name set (`commands/`, `skills/`, `bin/`, `scripts/wiki_skills/`) — convention from ARCHITECTURE.md §1.5.1.
- After this bead, the symlink graph in §1.5.5 loses `~/.local/bin/wiki-ingest` as a *required* link (it becomes optional, enabling subprocess fallback).

## Files Touched (explicit list)

- `bin/wiki-enrich` (modified — remove guard line if present)

## Test Surface

- **Shell smoke** (added to `tests/test_launcher_smoke.py` or similar if a launcher-test harness exists; otherwise manual):
  - `test_launcher_runs_without_wiki_ingest_on_path`: subprocess invocation with sanitized PATH → exit 0 on `--help`.
- **If no test harness exists for `bin/`**: rely on I-V.11 Smoke 1 for end-to-end verification.

## Acceptance

- [ ] R-52(a): Invoking `wiki-enrich --vault V --vault-root P --source S` with `wiki-ingest` absent from PATH succeeds (exit 0) when vendored path works. **Verified by Smoke 1 in I-V.11.**
- [ ] R-52(b): `bin/wiki-enrich` does NOT perform a `which wiki-ingest` guard at the launcher level — confirmed by `grep -E 'which wiki-ingest|command -v wiki-ingest' bin/wiki-enrich` returning zero matches.
- [ ] `bin/wiki-enrich --help` exits 0 in a shell environment with `wiki-ingest` absent from PATH (manual smoke).

## Rollback

`git checkout bin/wiki-enrich`. The launcher returns to its pre-bead state. If no guard was present originally, this is a no-op.

## Notes

- This bead may be **a no-op** if the launcher never had the guard. Confirm with the initial `Read` before editing. If no-op, mark the acceptance bullets as satisfied trivially.
- The launcher must not introduce new logic — keep it minimal. PATH semantics belong to the Python entry point.
