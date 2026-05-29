# Task 005-10: `wiki-alias` CLI (R-5.1, R-5.2)

## Use Case Connection
- UC-11 (register / manage an alias)

## Task Goal
Ship `wiki-alias`: `--add`/`--remove`/`--list` an alias. Mutate the entity page's Class A `aliases:` frontmatter **and** mirror to `entity_aliases` (Class B). Refuse collisions with `ALIAS_COLLISION`.

## Changes Description

### New Files
- `scripts/wiki_skills/wiki_alias.py` — argparse `main(argv) -> int`.
- `bin/wiki-alias` — thin wrapper; `chmod +x`.
- `.AGENTS.md` entry under `scripts/wiki_skills/`.

### CLI surface
- `wiki-alias <slug> --add "<surface>" [--type T] --vault V [--db-path PATH]` — collision pre-check (`resolve_entity` + `find_alias_collisions`); if `<surface>` already resolves to / equals a **different** entity → `ALIAS_COLLISION` (exit 5, names the conflicting slug, no content echo). Else append to frontmatter `aliases:` (flat list, atomic write, `_sanitize_*` + length cap) + `repo.add_alias(...)` (`alias_type` default `spelling_variant`, override `--type`). Idempotent re-add → `unchanged`.
- `wiki-alias <slug> --remove "<surface>" --vault V` — drop from frontmatter + `repo.remove_alias`; absent → `unchanged` exit 0.
- `wiki-alias <slug> --list --vault V` — print `repo.list_aliases`.

### Exit codes
0 ok · 2 `INVALID_ARG` · 3 `ENTITY_NOT_FOUND` · 4 `ENTITY_FILE_MISSING` · 5 `ALIAS_COLLISION`.

## Test Cases
### E2E (`tests/test_wiki_alias.py` — new)
1. **TC-E2E-01:** `--add "Hermes"` → frontmatter `aliases:` contains it **and** `entity_aliases` row exists; JSON `action:"added"`.
2. **TC-E2E-02:** re-add same surface → `action:"unchanged"` exit 0.
3. **TC-E2E-03:** `--add` a surface already an alias of a different entity → exit 5 `ALIAS_COLLISION` naming the other slug; no frontmatter/DB write.
4. **TC-E2E-04:** `--remove` → dropped from both; `--list` reflects current set.
5. **TC-E2E-05 (security):** `--add` a surface with YAML-delimiter / `[[ ]]` injection chars → sanitized; envelope (if rejected) never echoes the raw surface.
### Regression
- `bin/wiki-alias --help` exit 0; full reindex rebuilds the alias from frontmatter (cross-check with 005-03); `pytest tests/` green.

## Acceptance Criteria
- [ ] `--add` writes Class A frontmatter **and** Class B DB; collision → exit 5 (named, no echo).
- [ ] `--remove`/`--list` per tests; idempotent re-add/remove.
- [ ] Surfaces sanitized + length-capped (CWE-117/209).
- [ ] `bin/` wrapper + `.AGENTS.md`; `mypy --strict` clean.

## Notes
Phase-1: argparse + `bin` + RED flow tests (mock DAL); Phase-2: frontmatter mutation + real DAL. Depends on 005-06, 005-07. Docs/symlinks in 005-15.
