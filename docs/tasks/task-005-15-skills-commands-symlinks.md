# Task 005-15: skill/command/workflow docs + symlinks for the 3 new CLIs (C-1)

## Use Case Connection
- UC-09/10/11/15 (operator discoverability of `wiki-confirm`/`wiki-alias`/`wiki-merge`)

## Task Goal
Give each new CLI the full repo-convention surface (per CLAUDE.md): a `skills/<name>/SKILL.md`, `commands/<name>.md`, `workflows/<name>.md`, and the symlink set into `.claude/skills/`, `.claude/commands/`, `.agent/skills/`, `.agent/workflows/`.

## Changes Description

### New Files (per CLI: `wiki-confirm`, `wiki-alias`, `wiki-merge`)
- `skills/wiki-confirm/SKILL.md`, `skills/wiki-alias/SKILL.md`, `skills/wiki-merge/SKILL.md` — frontmatter (name, description with triggers) + usage + exit-code table (mirror the shipped CLI contract).
- `commands/wiki-confirm.md`, `commands/wiki-alias.md`, `commands/wiki-merge.md`.
- `workflows/wiki-confirm.md`, `workflows/wiki-alias.md`, `workflows/wiki-merge.md`.

### Symlinks (use existing helpers)
- Run `bin/link-skill.sh`, `bin/link-command.sh`, `bin/link-workflow.sh` (or `bin/install-project-symlinks.sh`) for each name → creates `.claude/`/`.agent/` symlinks.

## Test Cases
### Verification (shell / `tests/`)
1. **TC-V-01:** each `skills/<name>/SKILL.md` exists with valid frontmatter (run `python3 .agent/skills/skill-creator/scripts/validate_skill.py` if applicable, else assert frontmatter keys).
2. **TC-V-02:** `.claude/skills/<name>`, `.agent/skills/<name>`, `.claude/commands/<name>.md`, `.agent/workflows/<name>.md` symlinks resolve.
3. **TC-V-03:** `bin/wiki-confirm --help`, `bin/wiki-alias --help`, `bin/wiki-merge --help` all exit 0.

## Acceptance Criteria
- [ ] 3 × {SKILL.md, command.md, workflow.md} created with accurate triggers + exit-code tables.
- [ ] Symlink set present and resolving in `.claude/` + `.agent/`.
- [ ] No skill created by hand under `.agent/skills/` (use `skill-creator init_skill.py` if a TIER skill is needed — these are operator CLIs, so plain `skills/<name>/SKILL.md` per repo convention).

## Notes
Docs/symlinks bead — no Python logic, no stub phase. Depends on 005-09/10/11 (CLIs must exist so docs reflect shipped behavior). Mirrors how the existing 9 skills/commands/wrappers are wired.
