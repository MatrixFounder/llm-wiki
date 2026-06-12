# Task 029-00: Scaffold `skills/obsidian-cli/` skeleton + vendor symlinks `[STUB CREATION]`

## Use Case Connection
- All UC-29-* (structural precondition); RTM **R-029-8a** (symlinks) + the skeleton half of R-029-1/5/6/7.

## Task Goal
The complete directory + file skeleton of the skill exists with contracts (frontmatter,
section headers, placeholder markers) but NO content; both vendor symlink trees resolve;
the structural RED state is recorded.

## Changes Description

### New Files
- `skills/obsidian-cli/SKILL.md` — frontmatter ONLY (`name: obsidian-cli`,
  `description:` placeholder marked `TODO-029-02`, `tier: 2` [Q-029-5],
  `version: 0.1`) + the section-header skeleton: `## When to use` /
  `## Availability probe & degradation` / `## Targeting discipline` /
  `## Decision matrix` / `## Coherence protocol` / `## Safety tiers` /
  `## Top-20 quick reference` / `## References` — each body = one line
  `<!-- TODO 029-02 -->`.
- `skills/obsidian-cli/references/command-reference.md` — title + version-stamp
  placeholder + section headers (`## Setup (per platform)` / `## Command catalog by
  category` / `## Tier & gating legend`) + `<!-- TODO 029-03 -->`.
- `skills/obsidian-cli/references/recipes.md` — title + headers for the 8 planned
  recipes (names from TASK I-2.3) + `<!-- TODO 029-04 -->`.
- `skills/obsidian-cli/evals/README.md` — title + grading-rubric section headers +
  `<!-- TODO 029-01 -->`.
- `skills/obsidian-cli/evals/reports/.gitkeep` — empty.

### Changes in Existing Files
- none (symlinks only):
  - `.claude/skills/obsidian-cli` → `../../skills/obsidian-cli` (match the relative
    style of the existing wiki-* symlinks — inspect one first, e.g.
    `ls -la .claude/skills/wiki-search`).
  - `.agent/skills/obsidian-cli` → same pattern.

## Steps
1. Inspect an existing skill symlink pair to copy the exact relative-target convention.
2. Create the tree + files above (Write tool; no generator script — the repo-root
   `skills/` convention, NOT `.agent/skills/` `init_skill.py`, which targets framework
   skills; record this choice in the bead log).
3. Create both symlinks.
4. Record the RED state: run the `skill-validator` skill against the skeleton —
   NOTE (plan-review NIT-2): `skill-validator` is an **external/framework skill**
   (resolved per-vendor via the harness skill list, NOT a file under this repo's
   `skills/` or `.agent/skills/` — don't search the repo for it); if unavailable in
   the executing context, apply its structural checklist manually (description
   present? sections non-empty? frontmatter valid?). Capture the "missing
   description/content" findings into `evals/reports/red-structural-029-00.md`.

## Verification (deterministic)
- `test -d skills/obsidian-cli/references && test -d skills/obsidian-cli/evals/reports`
- `readlink .claude/skills/obsidian-cli` + `readlink .agent/skills/obsidian-cli`
  resolve; `ls -L` lists SKILL.md through both.
- `grep -c 'TODO 029-' skills/obsidian-cli/SKILL.md` ≥ 1 (skeleton, not content).
- `evals/reports/red-structural-029-00.md` exists and lists ≥1 structural gap (RED).
- Repo invariant: `git status` shows ONLY `skills/obsidian-cli/**` + 2 symlinks.

## Acceptance Criteria
- [ ] Skeleton tree + 5 files exist, frontmatter parses (`tier: 2`).
- [ ] Both vendor symlinks resolve.
- [ ] Structural RED recorded.
- [ ] No edits outside `skills/obsidian-cli/**` + symlinks.

## Notes
`samples/obsidian-cli-recon/` (scratch capture from Analysis) stays untouched here;
the durable fixture copy happens in 029-03 (TASK A-4).
