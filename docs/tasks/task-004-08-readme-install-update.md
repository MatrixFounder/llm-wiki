# Task 004-08: README install simplification — drop `ln -s wiki-ingest` requirement [DOCS — no stub]

## Meta

- **Bead ID**: `task-004-08-readme-install-update`
- **Slug**: `readme-install-update`
- **Maps to**: Issue **I-V.8**; RTM rows **R-53**
- **Depends on**: `task-004-05-wiki-enrich-refactor` (so the doc reflects shipped behavior, not aspirational)
- **Estimated time**: 0.25 day
- **Priority**: Medium

## Use Case Connection

- **UC-V2**: End-user installs via single command — README is the source-of-truth for what that "single command" looks like.

## Task Goal

Update `README.md` `## Installation` section (and any quick-start recipe that references `wiki-ingest` as a prerequisite) to remove the `ln -s wiki-ingest` step from the required install path. Note that `wiki-ingest` on PATH is **optional** (enables subprocess fallback, useful for debugging or for operators who already have the standalone CLI installed).

## Stub-First Plan

**No stub phase** — this bead is direct documentation writing. Per `tdd-stub-first` skill, docs-only beads skip Phase 1.

**Approach**:
1. `Read` `README.md` and locate the `## Installation` section + any quick-start recipe mentioning `wiki-ingest`.
2. Identify the current sentence/step that says something like "create a symlink for wiki-ingest" or "install wiki-ingest globally and symlink".
3. Replace with: brief note that wiki-ingest is now vendored at `scripts/wiki_ingest/` and that external `wiki-ingest` on PATH is **optional** (for subprocess fallback / debugging via `WIKI_ENRICH_NO_VENDORED=1`).
4. Update the `## External Dependencies` section (if it lists `wiki-ingest` as required) to mark it as optional.

## Changes Description

### New Files

- None.

### Changes in Existing Files

#### File: `README.md`

**Section `## Installation`:**

Before (illustrative):
> ```
> 1. Clone the repo
> 2. `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
> 3. Install wiki-ingest globally and symlink:
>    ln -s /path/to/Universal-skills/skills/wiki-ingest/scripts/wiki-ingest ~/.local/bin/wiki-ingest
> 4. ...
> ```

After:
> ```
> 1. Clone the repo
> 2. `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
> 3. (Optional) For subprocess-fallback debugging — install wiki-ingest globally:
>    ln -s /path/to/Universal-skills/skills/wiki-ingest/scripts/wiki-ingest ~/.local/bin/wiki-ingest
>    (As of TASK 004, wiki-ingest is vendored at scripts/wiki_ingest/ and called in-process by default.
>     Set WIKI_ENRICH_NO_VENDORED=1 to force the subprocess path when wiki-ingest is on PATH.)
> 4. ...
> ```

**Section `## External Dependencies`** (if present):
- Move `wiki-ingest` from "Required" to "Optional (for subprocess fallback)".
- Note the vendored snapshot location: `scripts/wiki_ingest/` + reference to `VENDORED_FROM.md` for provenance.

**Quick-start recipe** (if present):
- Remove any step that runs `which wiki-ingest` as a sanity check.
- Update the first `wiki-enrich` invocation example to NOT assume `wiki-ingest` is on PATH.

### Component Integration

- This bead is the user-visible counterpart of I-V.5 + I-V.6 — together they make the "single-command install" UC-V2 acceptance criterion true.
- No code is touched; no tests are added.

## Files Touched (explicit list)

- `README.md` (modified — `## Installation` + `## External Dependencies` + quick-start sections)

## Test Surface

- **No automated tests**.
- **Manual verification**: end-user follows the new README install steps in a fresh environment without `wiki-ingest` on PATH → `wiki-enrich` works (verified by I-V.11 Smoke 1).

## Acceptance

- [ ] R-53(a): README `## Installation` section no longer lists `ln -s wiki-ingest` as a required step.
- [ ] R-53(b): README notes `wiki-ingest` on PATH is optional (enables subprocess fallback, useful for debugging).
- [ ] R-53(c): Any quick-start recipe that previously used `wiki-ingest` as a required prerequisite is updated to reflect the in-process default.
- [ ] `grep -n 'wiki-ingest' README.md` shows no remaining "required" framing for the external CLI.

## Rollback

`git checkout README.md`. Documentation returns to pre-bead state.

## Notes

- This bead is **time-boxed at 0.25 day** — it's pure prose editing. If the edit balloons (e.g., operator asks for a broader install overhaul), defer the broader change to a follow-up bead and ship only the R-53 acceptance bullets here.
- Do NOT touch `CLAUDE.md` or `docs/ARCHITECTURE.md` — those are owned by other agents/beads (and `ARCHITECTURE.md` was already updated by the architect in commit `3b57d81`).
- If the existing README is sparse on install steps, this bead may be larger than expected; flag for plan-reviewer if the diff exceeds ~50 lines.
