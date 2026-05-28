# Task 003-v3-09: rewrite `skills/wiki-extract-concepts/SKILL.md` (BREAKING CHANGE notice + subcommand surface)

## Meta

- **Bead ID**: `task-003-v3-09-skill-wrapper-rewrite`
- **Slug**: `skill-wrapper-rewrite`
- **Maps to**: Issue **I-V3.4**; RTM row **R-30**; H-4 (BREAKING CHANGE).
- **Depends on**: task-003-v3-03 (apply argument set finalised), task-003-v3-05 (--orchestrator-id present).
- **Estimated time**: 0.25 day
- **Priority**: Medium.

## Use Case Connection

- Operator-facing reference doc. Read by operators (and by orchestrator implementations) to discover the new subcommand surface, exit codes, and the BREAKING CHANGE from v2.

## Task Goal

Rewrite `skills/wiki-extract-concepts/SKILL.md`:

1. **BREAKING CHANGE banner at top** (H-4):
   ```
   > ⚠️ BREAKING CHANGE (v2 → v3.1) — operator-facing CLI surface
   >
   > v2: wiki-extract-concepts --vault X --vault-root P --source-page Y [--ingest]
   > v3.1: wiki-extract-concepts prepare ...   AND   wiki-extract-concepts apply ...
   >
   > Legacy invocation (no subcommand) errors out with help text pointing at the
   > new surface. Every existing script, shell alias, agent prompt, or muscle-memory
   > invocation using v2 form will break. Migration: run prepare, then apply with --source-hash.
   ```

2. **Subcommand surface tables**:
   - `prepare` arguments: `--vault`, `--vault-root`, `--source-page`, `[--db-path]`. No `--model`, `--max-tokens`, `--ingest`.
   - `apply` arguments: `--vault`, `--vault-root`, `--source-page`, `--source-hash HEX` (REQUIRED), mutex `--candidates-file PATH | --candidates-stdin`, `[--db-path]`, `[--ingest]`, `[--orchestrator-id STRING]`.

3. **Exit-code table** (R-42 v3.1):

   | Code | Meaning | Sub-envelopes |
   |---|---|---|
   | 0 | Success or `is_unchanged=true` | — |
   | 1 | argparse / usage error | — |
   | 2 | Input-validation failure | `SOURCE_NOT_FOUND`, `INVALID_SOURCE_PATH`, `INVALID_SOURCE_SLUG`, `SOURCE_TOO_LARGE`, `SOURCE_CHANGED_DURING_EXTRACTION`, `INVALID_CANDIDATES_PATH` |
   | 4 | Candidates schema violation | `EXTRACTION_PARSE_ERROR`, `CANDIDATES_TOO_LARGE`, `CANDIDATE_COUNT_OUT_OF_BOUNDS`, `FIELD_TOO_LONG`, `UNKNOWN_FIELD`, `FIELD_QUOTE_NOT_IN_BODY` |
   | 5 | Partial index failure (`--ingest`) | `PARTIAL_INDEX_FAILURE` |
   | 6 | Manifest invalid (`--ingest`) | `MANIFEST_INVALID` |

   Note: exit-3 (`LLM_API_UNAVAILABLE`) RETIRED in v3.1.

4. **Workflow reference**: link to `workflows/wiki-extract-concepts.md` (003-v3-08).

5. **Example invocations**:
   ```bash
   # Step 1: prepare
   wiki-extract-concepts prepare --vault myvault --vault-root /path \
     --source-page some-summary

   # Step 2 (after orchestrator synthesizes candidates JSON):
   echo '[{...},{...}]' | wiki-extract-concepts apply \
     --vault myvault --vault-root /path --source-page some-summary \
     --source-hash <hash-from-prepare> --candidates-stdin \
     [--orchestrator-id "claude-opus-4-7"] [--ingest]
   ```

6. **Migration note** (specifically for operators who had v2 muscle memory): no shim or alias is provided; CLI surface change is intentional.

Existing symlinks `skills/wiki-extract-concepts/SKILL.md` ↔ `.agent/skills/wiki-extract-concepts/SKILL.md` ↔ `.claude/skills/wiki-extract-concepts/SKILL.md` from v2 are preserved.

## Stub-First Plan

n/a (documentation-only rewrite).

## Changes Description

### Edited files

- `skills/wiki-extract-concepts/SKILL.md` (rewrite; symlinks unchanged so other copies sync automatically).

## Component Integration

- Read by operators and by other docs (`docs/ARCHITECTURE.md` §2.1 references the SKILL.md surface).
- The exit-code table mirrors the in-code envelope shapes (R-42 v3.1).

## Files Touched

- `skills/wiki-extract-concepts/SKILL.md`

## Acceptance Criteria

- [ ] **R-30 (a)**: SKILL.md describes the new prepare/apply surface.
- [ ] **H-4**: prominent BREAKING CHANGE banner at top.
- [ ] Exit-code table covers 0/1/2/4/5/6 with all sub-envelopes.
- [ ] Migration note present.
- [ ] References `workflows/wiki-extract-concepts.md` and `.agent/skills/concept-extraction/SKILL.md`.
- [ ] Symlink resolution: `.claude/skills/wiki-extract-concepts/SKILL.md` and `.agent/skills/wiki-extract-concepts/SKILL.md` show the new content (via existing symlinks).

## Verification

```bash
# BREAKING CHANGE banner present
head -20 skills/wiki-extract-concepts/SKILL.md | grep -q "BREAKING CHANGE" && echo "OK: H-4 banner"

# Subcommand surface documented
grep -q "wiki-extract-concepts prepare" skills/wiki-extract-concepts/SKILL.md && echo "OK: prepare"
grep -q "wiki-extract-concepts apply" skills/wiki-extract-concepts/SKILL.md && echo "OK: apply"
grep -q "source-hash" skills/wiki-extract-concepts/SKILL.md && echo "OK: --source-hash"
grep -q "orchestrator-id" skills/wiki-extract-concepts/SKILL.md && echo "OK: --orchestrator-id"

# Exit-code table
grep -q "SOURCE_CHANGED_DURING_EXTRACTION" skills/wiki-extract-concepts/SKILL.md && echo "OK: H-1 envelope"
grep -q "CANDIDATE_COUNT_OUT_OF_BOUNDS" skills/wiki-extract-concepts/SKILL.md && echo "OK: H-2 envelope"

# No exit-3 reference
grep -q "LLM_API_UNAVAILABLE" skills/wiki-extract-concepts/SKILL.md && echo "FAIL: exit-3 should be retired" || echo "OK: no exit-3"

# Cross-references
grep -q "concept-extraction" skills/wiki-extract-concepts/SKILL.md && echo "OK: cross-ref skill"
grep -q "workflows/wiki-extract-concepts" skills/wiki-extract-concepts/SKILL.md && echo "OK: cross-ref workflow"
```

## Rollback

`git checkout HEAD~1 skills/wiki-extract-concepts/SKILL.md`.

## Notes

- The existing v2 SKILL.md content can be referenced for the table-of-flags structure, but the content is essentially a rewrite. Keep tone matching the rest of the repo's skill docs (terse, operator-oriented).
- The BREAKING CHANGE banner is the FIRST thing on the page, before frontmatter description text. This is intentional for visibility.
