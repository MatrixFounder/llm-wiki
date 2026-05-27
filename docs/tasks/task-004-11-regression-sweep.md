# Task 004-11: Regression sweep — full pytest + mypy + manual Smokes 1-7 [VERIFY — acceptance gate]

## Meta

- **Bead ID**: `task-004-11-regression-sweep`
- **Slug**: `regression-sweep`
- **Maps to**: Issue **I-V.11**; RTM rows **R-50, R-51, R-57, all RTM rows** (TASK 004 acceptance gate)
- **Depends on**: **all prior beads** — task-004-01 through task-004-10
- **Estimated time**: 0.5 day
- **Priority**: Critical (acceptance gate — TASK 004 is not Done until this bead is green)

## Use Case Connection

- **UC-V1**: Operator updates vendored snapshot (Smoke 7 exercises this).
- **UC-V2**: End-user installs via single command, no external `wiki-ingest` (Smokes 1, 4 exercise this).
- **Cross-cutting**: full quality gate (pytest, mypy, sync-script dry-run, VENDORED_FROM.md fields).

## Task Goal

Run the full TASK 004 acceptance recipe from TASK.md §7. Verify all 7 smokes pass + `pytest tests/ -q` reports ≥ 298 passed / 0 failed + `mypy --strict scripts/` is clean across the whole tree (not just `scripts/wiki_ingest/`). Verify all R-56 invariants (`--source required=True`, `WikiIngestError` class preserved, `index_from_manifest()` signature unchanged) and R-57 invariants (`Universal-skills/skills/wiki-ingest/` untouched per `git status` in that repo + standalone CLI Smoke 4 works).

This bead is the **TASK 004 Definition of Done**. If any smoke fails, the task is NOT done.

## Stub-First Plan

**No stub phase** — verification work. This bead consumes the green state from all 10 prior beads and runs the recipe.

**Approach** (sequential — each step must pass before the next):
1. `pytest tests/ -q` → ≥ 298 passed, 0 failed.
2. `mypy --strict scripts/` (full tree) → `Success: no issues found`.
3. Run Smokes 1-7 from TASK.md §7 in order. Each smoke has a specific expected output; verify each.
4. Verify R-56 invariants:
   - `grep -n 'required=True' scripts/wiki_skills/wiki_enrich.py | grep -- '--source'` shows the flag still has `required=True`.
   - `grep -n 'class WikiIngestError' scripts/wiki_skills/wiki_enrich.py` shows the class is still defined.
   - `git diff HEAD~<N> -- scripts/wiki_skills/wiki_enrich.py` (where N covers TASK 004) shows no signature change to `index_from_manifest` or `_validate_manifest`.
5. Verify R-57 invariants:
   - `cd ../Universal-skills && git status` → clean (no edits to upstream wiki-ingest).
   - Smoke 4 from TASK.md §7 (vendored CLI module): `python -m scripts.wiki_ingest.commands.ingest --source X --vault Y --output-format json` exits 0 with `status: "ok"` in the output.
   - **R-57(b) hardening smoke** (explicit upstream-still-works check): `~/.local/bin/wiki-ingest --version` (or `Universal-skills/skills/wiki-ingest/scripts/wiki-ingest --version`) prints `wiki-ingest 1.1.0` exit 0 — proves the upstream standalone binary is untouched and functional. Combined with the `git status` check above, this hardens R-57(b) beyond "file not edited" to "file still works".

## Changes Description

### New Files

- None (verification only; may create a `docs/reviews/task-004-acceptance-2026-05-XX.md` log if operator requests audit trail — optional).

### Changes in Existing Files

- None.

### Component Integration

- This bead is the **TASK 004 acceptance gate**. All 10 prior beads converge here.
- After this bead is green, TASK 004 is ready to be archived (TASK.md → docs/tasks/task-004-wiki-ingest-vendoring.md, PLAN.md → docs/plans/plan-004-wiki-ingest-vendoring.md per `skill-archive-task`).
- Triggers the resume of TASK 003 (`wiki-extract-concepts`), which was paused pending this task's ship.

## Files Touched (explicit list)

- None (verification only).

## Test Surface

- **Existing tests** (must all pass):
  - All 295+ tests in `tests/` from Phase 3a baseline.
  - ≥ 4 new tests from I-V.7 (R-51 acceptance).
  - 1 test from I-V.1 (`tests/test_vendored_import.py`).
  - 6 tests from I-V.3 (`tests/test_vendored_ingest_api.py`).
  - 4-5 tests from I-V.2 (`tests/test_sync_script.py`).
  - **Total**: ≥ 310 tests (295 baseline + 15-16 new). Acceptance bullet says ≥ 298 (looser bound).

## Acceptance (TASK 004 Definition of Done)

- [ ] `pytest tests/ -q` → **≥ 298 passed, 0 failed**.
- [ ] `mypy --strict scripts/` (full tree, not just `scripts/wiki_ingest/`) → **Success: no issues found**.
- [ ] **Smoke 1**: in-process path WITHOUT `wiki-ingest` on PATH — exit 0; output JSON has `action: "enriched"`, `vault_id` matches input, `index.upserted` is a list.
- [ ] **Smoke 2**: subprocess fallback via `WIKI_ENRICH_NO_VENDORED=1` — exit 0; output JSON has `action ∈ {"enriched", "partial"}`.
- [ ] **Smoke 3**: ImportError on vendored (simulated via rename) AND `wiki-ingest` absent — exit 6; output JSON has `error: "WIKI_INGEST_UNAVAILABLE"`.
- [ ] **Smoke 4** (R-57): `python -m scripts.wiki_ingest.commands.ingest --source X --vault Y --output-format json` — exit 0; manifest has `status: "ok"`.
- [ ] **Smoke 5**: `mypy --strict scripts/wiki_ingest/` AND `mypy --strict scripts/wiki_skills/wiki_enrich.py` — both clean.
- [ ] **Smoke 6**: `pytest tests/ -q` — 298+ green (subsumes the first acceptance bullet; explicit here per TASK.md §7).
- [ ] **Smoke 7a**: `bash scripts/sync_wiki_ingest.sh --dry-run --source ...` — exits 0, prints list of would-be-synced files, no file mutations.
- [ ] **Smoke 7b**: `VENDORED_FROM.md` has all required fields (`source_commit`, `synced_at`, `source_path`, `file_hashes`) — verified by inline Python script in TASK.md §7.
- [ ] R-56(a) invariant: `grep -n 'required=True' scripts/wiki_skills/wiki_enrich.py | grep -- '--source'` shows the `--source` flag still has `required=True`.
- [ ] R-56(c) invariant: `class WikiIngestError(Exception)` still present in `scripts/wiki_skills/wiki_enrich.py`.
- [ ] R-57(b) invariant: `cd ../Universal-skills && git status` → clean (the Universal-skills repo was NOT modified by TASK 004).
- [ ] R-57(b) hardening: upstream standalone `wiki-ingest --version` still exits 0 with `wiki-ingest 1.1.0` (proves binary functional, not just file untouched).
- [ ] All 7 acceptance smokes from TASK.md §7 passed; output captured (optional: in `docs/reviews/task-004-acceptance-<date>.md` for audit).

## Rollback

This bead has no edits to roll back. If a smoke fails, the rollback is **fix the failing bead and re-run this sweep** — not roll back the sweep itself.

If a critical regression is discovered late (e.g., R-56 invariant broken):
1. Identify which bead introduced it (most likely I-V.5 or I-V.7).
2. Roll back that bead per its own Rollback section.
3. Fix.
4. Re-run task-004-11 from scratch.

## Notes

- **Smoke ordering matters**: Smoke 1 must run with `wiki-ingest` NOT on PATH; Smoke 2 restores PATH before running. The recipe in TASK.md §7 has the precise shell snippets — follow them verbatim.
- **Smoke 3 uses `trap` to restore the vendored dir on EXIT** — make sure the trap is set before the `mv` to guarantee cleanup even if the smoke command fails mid-run.
- **Smoke 4 invokes the vendored module as a CLI** (`python -m scripts.wiki_ingest.commands.ingest --source X --vault Y --output-format json`). This explicitly tests R-57 (the `execute()` wrapper around `ingest()` did not regress the CLI surface) — do NOT skip it even if "we trust the wrapper".
- **TASK 004 is Done only when this bead is green.** If a smoke fails, the task remains in flight; do not archive TASK.md until every box above is checked.
- After this bead lands green, the operator may proceed to: (a) archive TASK 004 (`docs/TASK.md` → `docs/tasks/task-004-wiki-ingest-vendoring.md`, `docs/PLAN.md` → `docs/plans/plan-004-wiki-ingest-vendoring.md`), and (b) resume TASK 003 (`wiki-extract-concepts`) from its paused state.
