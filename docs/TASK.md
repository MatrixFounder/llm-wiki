# TASK 059 — docs-sync: reconcile documentation with the TASK 058 post-ship feature set

## 0. Meta Information
- **Task ID**: 059
- **Slug**: docs-sync-task-058-post-ship
- **Origin**: `/update-docs + docs/manuals` (operator, 2026-07-11)
- **Type**: Chore (documentation only — zero code changes)
- **Effort**: S

## 1. Problem

TASK 058 shipped `wiki-config` and was then extended by five post-ship UX commits
(`bc6b1d7` → `c2bf9c1`) that changed **only code** — no documentation surface was
updated. Additionally, the `.AGENTS.md` memory files never received entries for the
TASK 058 artifacts at all (not even from the main merge `6080fde`).

Undocumented post-ship features:

1. `show` folder argument is now optional — defaults to the **active Obsidian note's
   folder** → CWD → vault root (envelope `folder_source`); shared helper extracted to
   `scripts/wiki_skills/_active_note.py` (Decision-16).
2. `report` nav renders the full folder **hierarchy** (configured spine + ancestors).
3. `serve` UI: full vault tree with override/delete-config on any folder; collapsible
   tree (+ expand/collapse-all, persisted state); per-folder pending edits surviving
   folder switches (red dots + "Save all N"); template picker in the panel header
   (Quick setup / re-init); restore-from-backup UI for accidentally deleted configs.

## 2. Scope (files to update)

- [x] Rotate completed TASK/PLAN 058 → `docs/tasks/` + `docs/plans/` (lockstep)
- [x] `docs/manuals/obsidian-llm-wiki_manual.md` — wiki-config row + `.wiki/sync.yaml`
      cross-references (operator-requested focus)
- [x] `README.md` — CLI count 17→18 in the components table; add the missing
      `wiki-config` row to the Health table
- [x] `skills/wiki-config/SKILL.md` — `show [<folder>]` default, serve UI features (v1.1)
- [x] `commands/wiki-config.md` — `show` default-folder note
- [x] `CLAUDE.md` — one-line `show` default amendment
- [x] `.AGENTS.md`: `scripts/wiki_skills/` (wiki_config package + `_active_note.py`),
      `templates/` (sync-profiles), `config/` (x-wiki-* + .json projection),
      `tests/` (TASK 058 test surface)
- [x] `docs/architectures/technology-stack.md` — `ruamel.yaml` dependency record +
      §6.2 Frontend correction ("None" → the deliberate wiki-config vanilla-JS web layer)
- [x] **Found during the pass**: `templates/CLAUDE.md.tmpl` + `CLAUDE.layout.md.tmpl`
      still said "17 CLIs" with no `wiki-config` (the Currency invariant —
      staleness propagates into real user vaults); fixed + history note in
      `templates/.AGENTS.md`

## 3. Acceptance

- Every surface above names the post-ship behavior it documents; no stale "17 CLIs"
  remains outside the historical Currency note in `templates/.AGENTS.md`.
- No source/test files touched (`git diff --stat` shows docs/memory files only).
- Follow-up (operator): run `/vdd-multi` comprehensive review after the docs commit.

## 4. Completion

Shipped as a single docs commit on `main` (see git log for this date). All checklist
items above verified against the working tree before commit.
