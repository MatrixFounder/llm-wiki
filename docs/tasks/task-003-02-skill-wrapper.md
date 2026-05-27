# Task 003-02: Skill wrapper + slash command [DOCS-ONLY]

## Meta

- **Bead ID**: `task-003-02-skill-wrapper`
- **Slug**: `skill-wrapper`
- **Maps to**: Issue **I-7.2**; RTM row **R-30**.
- **Depends on**: task-003-00 (so the SKILL.md example uses the correct neutral-module import) and task-003-01 (so the SKILL.md examples reference the actual argparse surface).
- **Estimated time**: 0.25 day
- **Priority**: Medium (does not block any downstream bead — runs in parallel with 003-03..003-11)

## Use Case Connection

- **UC-08 (operator invocation)**: documents the slash command `/wiki-extract-concepts` that's the operator-facing entry point.

## Task Goal

Create the skill wrapper documentation and slash-command file for `wiki-extract-concepts`. Follow the existing template at `skills/wiki-enrich/SKILL.md` and `.claude/commands/wiki-enrich.md`. Add symlinks into `.agent/skills/` (per CLAUDE.md "Conventions").

**This is a documentation-only bead** — no code surface, no Phase 1 stub phase.

## Stub-First Plan

**Phase 1 — n/a (documentation-only per PLAN.md §3 row 003-02).**

**Phase 2 — Direct write**:

1. Inspect the existing template at `skills/wiki-enrich/SKILL.md` to mirror its shape: front-matter (if any), When-to-use block, Inputs/Outputs sections, Example invocations, Failure modes, Cross-references.
2. Write `skills/wiki-extract-concepts/SKILL.md`:
   - **When to use**: source page is already indexed (via `/wiki-enrich` or `/wiki-index-upsert`) and operator wants to populate `_concepts/<slug>.md` + entity rows.
   - **Inputs**: `--vault`, `--vault-root`, `--source-page`, optional `--db-path`, `--model`, `--ingest`, `--max-tokens`.
   - **Outputs (without `--ingest`)**: manifest JSON on stdout; concept pages written to `_concepts/`; entity + ref rows in DB.
   - **Outputs (with `--ingest`)**: combined `{"extraction": <manifest>, "index": <summary>}` JSON; same DB writes plus indexer mirror.
   - **Example invocations**: both inspection mode and auto-dispatch mode (mirror TASK.md §3 invocation block).
   - **Failure modes**: exit codes 0-6 per R-42 with brief explanations.
   - **Cross-references**: link to TASK.md, ARCHITECTURE.md §2.1, ADR-001, WIKI-INGEST-V1.1-CONTRACT.md.
   - **Note on neutral-module dependency**: brief paragraph explaining that this skill imports `validate_manifest` + `index_from_manifest` + `WikiIngestError` from the neutral `_manifest_consumer` module — NOT from `wiki_enrich` directly (Decision-16).
3. Write `.claude/commands/wiki-extract-concepts.md`:
   - Operator-facing slash-command card. Short description + canonical invocation example.
   - Reference: `skills/wiki-enrich/.claude/commands/wiki-enrich.md` (or wherever the existing template lives — locate via `ls .claude/commands/`).
4. Create symlinks per CLAUDE.md convention:
   - `.agent/skills/wiki-extract-concepts/SKILL.md` → `../../../skills/wiki-extract-concepts/SKILL.md`
   - `.claude/skills/wiki-extract-concepts/SKILL.md` → `../../../skills/wiki-extract-concepts/SKILL.md` (if pattern exists in repo)
   - Verify by inspecting how `wiki-enrich`'s symlinks are wired: `ls -la .agent/skills/wiki-enrich/ .claude/skills/wiki-enrich/ 2>/dev/null`.

## Changes Description

### New Files

- `skills/wiki-extract-concepts/SKILL.md` — the canonical skill description.
- `.claude/commands/wiki-extract-concepts.md` — slash command card.
- Symlinks per repo convention:
  - `.agent/skills/wiki-extract-concepts/SKILL.md` → `../../../skills/wiki-extract-concepts/SKILL.md`
  - (and any other symlinks the existing template creates — match `wiki-enrich`'s setup exactly).

### Changes in Existing Files

- None (docs-only).

### Component Integration

- This bead does not touch any Python code or test code. Its sole output is documentation that operators (and future maintainers) discover when looking up the skill via slash-command autocomplete or skill-system catalog.

## Files Touched (explicit list)

- `skills/wiki-extract-concepts/SKILL.md` (new)
- `.claude/commands/wiki-extract-concepts.md` (new)
- `.agent/skills/wiki-extract-concepts/SKILL.md` (new symlink, target = `../../../skills/wiki-extract-concepts/SKILL.md`)
- (any additional symlinks discovered by mirroring the `wiki-enrich` pattern)

## Test Surface

- **No automated tests.** Verification is manual: render the markdown, run the slash-command help path, confirm symlinks resolve.

## Acceptance Criteria

- [ ] **R-30(a)**: `skills/wiki-extract-concepts/SKILL.md` exists and follows the structure of `skills/wiki-enrich/SKILL.md` (verified by section-header match).
- [ ] **R-30(b)**: `.claude/commands/wiki-extract-concepts.md` symlinked or created per existing skill template pattern.
- [ ] Symlinks resolve: `readlink .agent/skills/wiki-extract-concepts/SKILL.md` returns a valid path that exists.
- [ ] SKILL.md mentions:
  - the neutral-module dependency (`_manifest_consumer`) per Decision-16
  - both invocation modes (without and with `--ingest`)
  - exit codes 0-6 per R-42
- [ ] No regressions: `pytest tests/ -q` still passes (336+ green from 003-00 + 003-01).

## Verification

```bash
# Render check
cat skills/wiki-extract-concepts/SKILL.md | head -60

# Symlink resolution
readlink .agent/skills/wiki-extract-concepts/SKILL.md
ls -la .agent/skills/wiki-extract-concepts/

# Cross-reference check (section parity with wiki-enrich)
diff <(grep "^##" skills/wiki-enrich/SKILL.md) <(grep "^##" skills/wiki-extract-concepts/SKILL.md) | head

# No regressions
pytest tests/ -q
```

## Rollback

`rm -rf skills/wiki-extract-concepts/ .claude/commands/wiki-extract-concepts.md .agent/skills/wiki-extract-concepts/`. No code touched; trivial.

## Notes

- This bead is intentionally docs-only. It does not gate any downstream code bead — operator can run `python -m scripts.wiki_skills.wiki_extract_concepts ...` even without the SKILL.md. But the slash-command UX requires it, so it lands as a sibling to 003-01 in Phase 1.
- The SKILL.md is the place to document the **operator-visible** Decision-15 + Decision-16 consequences (no `--manifest-*` flags on `wiki-enrich`; the neutral-module-based dispatch). Architecture details belong in ARCHITECTURE.md (already updated).
- If a future bead changes the argparse surface, SKILL.md must be re-synced. Add a comment at the top: `<!-- Sync with scripts/wiki_skills/wiki_extract_concepts.py argparse on every change. -->`
