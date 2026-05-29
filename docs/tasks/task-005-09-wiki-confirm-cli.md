# Task 005-09: `wiki-confirm` CLI (R-4.2, R-4.3, R-4.4)

## Use Case Connection
- UC-09 (confirm), UC-10 (auto-promote)

## Task Goal
Ship the `wiki-confirm` CLI: promote a candidate → confirmed (`--undo` reverses), and bulk `--auto [--threshold N] [--dry-run]`. Class A frontmatter write-back **first**, then the DB mirror via `set_entity_candidate`.

## Changes Description

### New Files
- `scripts/wiki_skills/wiki_confirm.py` — argparse entry (`prepare`-style `main(argv) -> int`).
- `bin/wiki-confirm` — thin wrapper (`exec python -m scripts.wiki_skills.wiki_confirm "$@"`), mirror the existing `bin/wiki-search` pattern; `chmod +x`.
- `scripts/wiki_skills/.AGENTS.md` — add `wiki_confirm.py` entry (Developer updates).

### Changes in Existing Files
- (reuse) `scripts/wiki_skills/_common.py` / `wiki_extract_concepts.py` helpers: `_read_file_bounded`, atomic-temp write, `O_NOFOLLOW`, `_sanitize_*`.

### CLI surface
- `wiki-confirm <slug> --vault V [--undo] [--db-path PATH]` — locate `entities.file_path`; atomically rewrite frontmatter `is_candidate: false` (or `true` on `--undo`) and drop/add the `candidate` tag, preserving other keys/body; then `repo.set_entity_candidate(...)`. Idempotent (`changed:false`). One `entity-confirmed` log event per promotion (Q5 default).
- `wiki-confirm --auto [--threshold N] [--dry-run] --vault V` — `repo.auto_promote_candidates(v, N or 3)`; `--dry-run` lists would-promote via `list_candidates` + recompute, writes nothing.

### Exit codes
0 ok (incl. idempotent) · 2 `INVALID_ARG` · 3 `ENTITY_NOT_FOUND` · 4 `ENTITY_FILE_MISSING`. Envelope `{error, field?, reason}` — never echoes content.

## Test Cases
### E2E (`tests/test_wiki_confirm.py` — new)
1. **TC-E2E-01:** confirm a candidate → frontmatter `is_candidate: false` on disk **and** DB row `0`; JSON `{"status":"confirmed","changed":true}` exit 0.
2. **TC-E2E-02:** re-run → `changed:false` exit 0 (idempotent).
3. **TC-E2E-03:** `--undo` → frontmatter+DB back to candidate.
4. **TC-E2E-04:** `--auto --threshold 3` on a vault with one 3-mention + one 1-mention candidate → promotes only the first; `--dry-run` writes nothing.
5. **TC-E2E-05:** unknown slug → exit 3 `ENTITY_NOT_FOUND`; `file_path` missing on disk → exit 4.
### Regression
- `bin/wiki-confirm --help` exit 0; `pytest tests/` green.

## Acceptance Criteria
- [ ] Confirm flips Class A frontmatter **and** DB; `--undo` reverses; idempotent.
- [ ] `--auto`/`--threshold`/`--dry-run` behave per UC-10 (`>=` boundary; no-write dry-run).
- [ ] Envelopes 2/3/4 correct; never echo offending value.
- [ ] `bin/` wrapper + `.AGENTS.md` updated; `mypy --strict` clean.

## Notes
Phase-1: argparse + handlers call stubbed DAL (mocked) + `bin` wrapper → RED `--help`/flow tests; Phase-2: frontmatter rewrite + real DAL. Depends on 005-05. SKILL/command/workflow docs + symlinks in 005-15.
