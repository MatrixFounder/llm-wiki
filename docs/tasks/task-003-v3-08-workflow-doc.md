# Task 003-v3-08: create `workflows/wiki-extract-concepts.md` (6-step orchestrator workflow)

## Meta

- **Bead ID**: `task-003-v3-08-workflow-doc`
- **Slug**: `workflow-doc`
- **Maps to**: Issue **I-V3.3**; RTM row **R-30**; H-1 (workflow ensures `--source-hash` is propagated).
- **Depends on**: task-003-v3-00 (subcommand names finalised).
- **Estimated time**: 0.25 day
- **Priority**: Medium.

## Use Case Connection

- The workflow file is what the orchestrator reads via `Workflow({name: "wiki-extract-concepts"})` (Claude Code) when the operator invokes `/wiki-extract-concepts`. Documents the 6-step recipe end-to-end.

## Task Goal

Create `workflows/wiki-extract-concepts.md` documenting:

1. **Step 1 — Pre-flight**: Parse `--vault`, `--vault-root`, `--source-page` from operator invocation.
2. **Step 2 — Invoke `wiki-extract-concepts prepare`** with the three flags + optional `--db-path`. Capture stdout JSON.
3. **Step 3 — Check `is_unchanged`**:
   - If `prepare_output["is_unchanged"] == true` → emit `{status: "unchanged"}` envelope to operator; STOP (UC-09 v3.1).
   - Otherwise continue.
4. **Step 4 — Load extraction skill**: `Skill({skill: "concept-extraction"})` to load prompt + JSON contract into orchestrator context.
5. **Step 5 — Read source**: `Read({file_path: prepare_output["source_path"]})` (orchestrator reads via Read tool).
6. **Step 6 — Synthesize**: orchestrator emits candidates JSON array in own context, per the strict schema documented in `concept-extraction` skill (1 ≤ N ≤ 25, per-field caps, no extra keys, slug regex, span regex, type whitelist).
7. **Step 7 — Invoke `wiki-extract-concepts apply`** via subprocess (bash):
   ```bash
   echo '<candidates-array>' | wiki-extract-concepts apply \
     --vault <vault> --vault-root <root> --source-page <slug> \
     --source-hash <prepare_output.source_hash> \
     --candidates-stdin \
     [--orchestrator-id "<model-name>"] \
     [--ingest]
   ```
   Capture stdout (manifest or `{extraction, index}` envelope). Surface to operator.

**Error handling**:
- prepare exit 2 → forward envelope to operator; STOP.
- apply exit 2 (SOURCE_CHANGED) → instruct operator to re-run `/wiki-extract-concepts` (the workflow loops; the orchestrator does NOT auto-retry).
- apply exit 4 → forward envelope; STOP.
- apply exit 5 (PARTIAL_INDEX_FAILURE) → forward envelope; STOP.

Add symlink: `.agent/workflows/wiki-extract-concepts.md` → `workflows/wiki-extract-concepts.md`.

Update `.claude/commands/wiki-extract-concepts.md` (if exists) to delegate to the workflow.

## Stub-First Plan

n/a (documentation-only).

## Changes Description

### New files

- `workflows/wiki-extract-concepts.md`

### New symlinks

- `.agent/workflows/wiki-extract-concepts.md` → `workflows/wiki-extract-concepts.md`

### Edited files

- `.claude/commands/wiki-extract-concepts.md` (existing file; updated to delegate).

## Component Integration

- Loaded by orchestrator at the start of the `/wiki-extract-concepts` slash command invocation.
- References (a) the `concept-extraction` skill (003-v3-07) by name; (b) the `prepare`/`apply` subcommands (003-v3-00..03); (c) the exit-code surface (R-42).

## Files Touched

- `workflows/wiki-extract-concepts.md` (new)
- `.agent/workflows/wiki-extract-concepts.md` (new symlink)
- `.claude/commands/wiki-extract-concepts.md` (edited)

## Acceptance Criteria

- [ ] **R-30**: workflow file documents the 6-step recipe.
- [ ] **H-1**: workflow explicitly instructs orchestrator to pass `--source-hash` from prepare's output to apply.
- [ ] Workflow describes orchestrator-level short-circuit on `is_unchanged=true` (UC-09 v3.1 alignment).
- [ ] Error-handling section covers each exit code (2, 4, 5).
- [ ] Frontmatter present: `description:` field; symlink resolves.
- [ ] `.claude/commands/wiki-extract-concepts.md` updated to delegate.

## Verification

```bash
test -f workflows/wiki-extract-concepts.md && echo "OK: workflow file"
test -L .agent/workflows/wiki-extract-concepts.md && echo "OK: symlink"
readlink .agent/workflows/wiki-extract-concepts.md
# expect: relative path to workflows/wiki-extract-concepts.md

grep -q "source-hash" workflows/wiki-extract-concepts.md && echo "OK: H-1 reference"
grep -q "is_unchanged" workflows/wiki-extract-concepts.md && echo "OK: UC-09 short-circuit"
```

## Rollback

`rm workflows/wiki-extract-concepts.md .agent/workflows/wiki-extract-concepts.md`; revert `.claude/commands/wiki-extract-concepts.md`.

## Notes

- Use `workflows/wiki-enrich.md` as a structural template (matches repo conventions).
- The orchestrator-id flag is documented as OPTIONAL but RECOMMENDED. Example uses Claude Opus 4.7 (matching the version of the orchestrator the user is most likely running today, 2026-05-28).
