# Task 005-11: `wiki-merge` CLI (R-4.7)

## Use Case Connection
- UC-15 (merge a duplicate entity into the canonical one)

## Task Goal
Ship `wiki-merge <from> <into>`: **Class A first** (append `into.aliases`, delete the `from` page atomically), then the `merge_entities` DB transaction. Redirect via the alias table (C-7, no wikilink rewriting). `--dry-run` reports without writing.

## Changes Description

### New Files
- `scripts/wiki_skills/wiki_merge.py` — argparse `main(argv) -> int`.
- `bin/wiki-merge` — thin wrapper; `chmod +x`.
- `.AGENTS.md` entry under `scripts/wiki_skills/`.

### CLI surface & order (C-8)
- `wiki-merge <from-slug> <into-slug> --vault V [--dry-run] [--db-path PATH]`:
  1. Validate both entities exist (`resolve_entity`); refuse `from == into` → `INVALID_MERGE` (exit 5).
  2. `--dry-run`: read-only counts (refs that would re-point, aliases that would move) → JSON `{... "dry_run": true}`, exit 0, no writes.
  3. **Class A:** append `from`-slug + `from`-name + `from`'s aliases to `into`'s frontmatter `aliases:` (`alias_type=former_name`, atomic write, sanitized); then **delete** `_concepts/<from>.md` (atomic `os.unlink`, `O_NOFOLLOW` guard). On `from` file missing → `ENTITY_FILE_MISSING` (exit 4).
  4. **Class B:** `repo.merge_entities(v, from, into)`. On DB failure **after** the file ops → `MERGE_MIRROR_FAILED` (exit 6) pointing the operator at `wiki-reindex --delta`.
  5. Emit `{"from","into","refs_repointed","aliases_absorbed","aliases_skipped","action":"merged"}`.

### Exit codes
0 ok (incl. dry-run) · 2 `INVALID_ARG` · 3 `ENTITY_NOT_FOUND` · 4 `ENTITY_FILE_MISSING` · 5 `INVALID_MERGE` · 6 `MERGE_MIRROR_FAILED`.

## Test Cases
### E2E (`tests/test_wiki_merge.py` — new)
1. **TC-E2E-01:** merge `hermes-framework` → `hermes-agent`: `_concepts/hermes-framework.md` deleted; `hermes-agent` frontmatter `aliases:` gains `hermes-framework` + its name; `entities` row for `from` gone; refs re-pointed; JSON `action:"merged"`.
2. **TC-E2E-02:** `--dry-run` → report only, no file/DB mutation.
3. **TC-E2E-03:** self-merge → exit 5 `INVALID_MERGE`.
4. **TC-E2E-04:** missing endpoint → exit 3 `ENTITY_NOT_FOUND` (names side); `from` file missing → exit 4.
5. **TC-E2E-05 (C-8 recovery):** simulate DB failure after the file ops (monkeypatch `merge_entities` to raise) → exit 6 `MERGE_MIRROR_FAILED`; a subsequent `wiki-reindex --delta` restores consistency from Class A.
### Regression
- `bin/wiki-merge --help` exit 0; `pytest tests/` green.

## Acceptance Criteria
- [ ] Class A mutated before DB (C-8); `from` page deleted; `into.aliases` carries old surfaces.
- [ ] `--dry-run` writes nothing; self-merge → 5; missing → 3/4; mirror-fail → 6.
- [ ] Redirect via alias table only (no `[[...]]` rewriting).
- [ ] `bin/` wrapper + `.AGENTS.md`; `mypy --strict` clean.

## Notes
Phase-1: argparse + `bin` + RED flow tests (mock `merge_entities`); Phase-2: Class-A orchestration + real DAL. Depends on 005-08. Durability proven end-to-end in 005-16 (UC-15 §D8 gate). Docs/symlinks in 005-15.
