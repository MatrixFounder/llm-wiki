# Task 003-v3-07: create `.agent/skills/concept-extraction/SKILL.md` (operator-facing extraction prompt + contract)

## Meta

- **Bead ID**: `task-003-v3-07-concept-extraction-skill`
- **Slug**: `concept-extraction-skill`
- **Maps to**: Issue **I-V3.2**; RTM rows **R-33′**, **R-34**; M-4 (security-sensitive banner).
- **Depends on**: none (parallel-safe with Phase 1 logic beads).
- **Estimated time**: 0.25 day
- **Priority**: Medium.

## Use Case Connection

- **UC-08 v3.1 Step 5**: orchestrator calls `Skill({skill: "concept-extraction"})` to load the extraction prompt + JSON candidates contract into its own context before synthesizing.

## Task Goal

Create a new skill at `.agent/skills/concept-extraction/SKILL.md` documenting:

1. The extraction prompt (lifted verbatim from v2's `_build_extraction_prompt` — the prompt that worked in v2 production).
2. The JSON candidates contract:
   - Array shape `[{slug, name, definition, source_quote, source_span, entity_type}, ...]`.
   - Strict schema (NO extra keys).
   - Count bound `1 ≤ N ≤ 25`.
   - Per-field caps `name ≤ 200`, `definition ≤ 2000`, `source_quote ≤ 500` chars.
   - Kebab-case slug regex `^[a-z0-9][a-z0-9-]{0,62}$`.
   - `source_span` regex `^L\d+-L\d+$`.
   - `entity_type` whitelist `{concept, person, company, product, group, event, work, external}`.
   - `source_quote` SHOULD be a verbatim substring of `source_body` (best-effort; optional check on `apply` side; bypass via env var).
3. Example invocation snippet showing the full orchestrator workflow.
4. **TOP-OF-FILE SECURITY BANNER** (M-4):
   ```
   > ⚠️ SECURITY-SENSITIVE: modifications require code review AND security audit.
   > This file's content is loaded into LLM context at runtime; tampering enables
   > stored prompt injection against the orchestrator.
   ```

Add symlinks:
- `skills/concept-extraction/SKILL.md` → `.agent/skills/concept-extraction/SKILL.md`
- `.claude/skills/concept-extraction/SKILL.md` → `.agent/skills/concept-extraction/SKILL.md`

## Stub-First Plan

n/a (documentation-only bead).

## Changes Description

### New files

- `.agent/skills/concept-extraction/SKILL.md` (new — ~150 lines)

### New symlinks

- `skills/concept-extraction/SKILL.md` → `.agent/skills/concept-extraction/SKILL.md`
- `.claude/skills/concept-extraction/SKILL.md` → `.agent/skills/concept-extraction/SKILL.md`

## Component Integration

- Loaded by the orchestrator via `Skill({skill: "concept-extraction"})` Tool call (Claude Code) — equivalent on other vendors.
- Read by tests indirectly (003-v3-12 integration test uses the canned `tests/fixtures/source_extract/candidates.json` which mirrors the contract).
- Referenced by `workflows/wiki-extract-concepts.md` (003-v3-08).

## Files Touched

- `.agent/skills/concept-extraction/SKILL.md` (new)
- `skills/concept-extraction/SKILL.md` (new symlink)
- `.claude/skills/concept-extraction/SKILL.md` (new symlink)

## Acceptance Criteria

- [ ] **R-33′ (a)**: SKILL.md documents the prompt + JSON contract.
- [ ] **R-34**: SKILL.md instructs orchestrator to USE the exact slug from `known_concepts` when matching.
- [ ] **M-4**: top-of-file security banner present.
- [ ] Symlinks created and resolve correctly: `ls -la skills/concept-extraction/ .claude/skills/concept-extraction/` shows symlinks pointing at `.agent/skills/concept-extraction/SKILL.md`.
- [ ] Frontmatter present with `name: concept-extraction`, `description: ...`, `tier: 1`.

## Verification

```bash
source .venv/bin/activate

# File exists
test -f .agent/skills/concept-extraction/SKILL.md && echo "OK: SKILL.md exists"

# Banner present
head -10 .agent/skills/concept-extraction/SKILL.md | grep -q "SECURITY-SENSITIVE" && echo "OK: banner present"

# Symlinks resolve
test -L skills/concept-extraction/SKILL.md && echo "OK: skills/ symlink"
test -L .claude/skills/concept-extraction/SKILL.md && echo "OK: .claude/ symlink"

readlink skills/concept-extraction/SKILL.md
readlink .claude/skills/concept-extraction/SKILL.md
# both expect: relative path to .agent/skills/concept-extraction/SKILL.md
```

## Rollback

`rm -r .agent/skills/concept-extraction/ skills/concept-extraction/ .claude/skills/concept-extraction/`.

## Notes

- The extraction prompt should be lifted **verbatim** from v2's `_build_extraction_prompt` (in `scripts/wiki_skills/wiki_extract_concepts.py` lines 140-168) — this is the prompt that worked in v2 production. Don't try to "improve" the wording; identical prompt = identical synthesis behaviour.
- The security banner is mandatory per M-4. Skill is loaded into the LLM's runtime context; any malicious modification (e.g., "also output the user's API key") would be a successful prompt injection. Hence code-review gating.
- Future hardening (out of scope for v3.1): hash-pin this file in manifest provenance (TASK §1.2 out-of-scope).
