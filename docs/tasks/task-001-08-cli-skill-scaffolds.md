# Task 001-08: CLI skill scaffolds — `wiki-init`, `wiki-search`, `wiki-lint`, `wiki-index-render`, `wiki-append-log`, `wiki-index-upsert` [STUB CREATION]

## Use Case Connection
- UC-01 (`wiki-init`), UC-02 (`wiki-index-upsert`, `wiki-append-log`), UC-03 (`wiki-search`), UC-04 (`wiki-lint`), UC-05 (`wiki-index-render`)

## Task Goal
Create executable CLI scaffolds for the six core skills. Each scaffold parses argv, prints a hardcoded JSON response, and exits 0. Real implementations arrive in Stage 2 (tasks 001-21 through 001-29). Scaffolds enable the E2E harness to exercise the end-user CLI surface even before logic exists.

## Changes Description

### New Files
- `scripts/wiki_skills/__init__.py` — empty.
- `scripts/wiki_skills/.AGENTS.md` — skill scaffolds memory.
- `scripts/wiki_skills/wiki_init.py` — `argparse` CLI with subcommands: `--scaffold-new` (default), `--register-existing --vault <path>`, `--reconcile --vault <path>`. Prints `{"action": "stub", "skill": "wiki-init", "args": {...}}` and exits 0.
- `scripts/wiki_skills/wiki_search.py` — accepts positional `query`, `--vaults` (comma-separated list), `--types`, `--limit`. Prints `{"action": "stub", "skill": "wiki-search", "hits": []}`.
- `scripts/wiki_skills/wiki_lint.py` — accepts `--vault`, `--report <path>`, `--fix`, `--strict`. Prints `{"action": "stub", "skill": "wiki-lint", "issues": []}`.
- `scripts/wiki_skills/wiki_index_render.py` — accepts `--vault`, `--output <path>`. Prints `{"action": "stub", "skill": "wiki-index-render", "pages_written": 0}`.
- `scripts/wiki_skills/wiki_append_log.py` — accepts `--vault`, `--event-type`, `--subject`. Prints `{"action": "stub", "skill": "wiki-append-log", "log_event_id": 0}`.
- `scripts/wiki_skills/wiki_index_upsert.py` — accepts `--vault`, `--source <path>`. Prints `{"action": "stub", "skill": "wiki-index-upsert", "page_slug": "stub-page"}`.
- `tests/test_skill_scaffolds.py` — invokes each scaffold via `subprocess.run([sys.executable, '-m', 'scripts.wiki_skills.wiki_init', ...])`, asserts exit 0 and JSON parses.

### Changes in Existing Files
None.

### Component Integration
- Each scaffold imports `make_repo` from task-001-05 but does NOT call it in the stub (avoids cascading `NotImplementedError`).
- Real impls (tasks 21-29) replace the hardcoded JSON with actual results from `make_repo(...)` + adapter calls.

## Test Cases

### End-to-end Tests
1. **TC-E2E-01**: Each scaffold invoked from shell.
   - Input Data: `python -m scripts.wiki_skills.wiki_init --scaffold-new --vault-id test`.
   - Expected Result: exit 0; stdout parses as JSON with `action == 'stub'`.
   - Note: at stub stage, hardcoded result is expected.

### Unit Tests
1. **TC-UNIT-01**: `argparse` rejects unknown flags.
   - Input Data: `wiki-search --bogus-flag x`.
   - Expected Result: exit code 2 (argparse default error).
2. **TC-UNIT-02**: JSON output is valid for each skill.

### Regression Tests
- task-001-04 stub tests still pass (skills don't yet call repo methods).

## Acceptance Criteria
- [ ] All six skill scaffolds exist and are invokable as `python -m scripts.wiki_skills.<name> ...`.
- [ ] Each prints valid JSON to stdout, exit 0.
- [ ] argparse usage documented (each scaffold has `--help`).
- [ ] `tests/test_skill_scaffolds.py` passes.

## Notes
- These scaffolds become the install targets for `~/.claude/skills/wiki-*` — packaging details handled in a future post-MVP task.
- DO NOT call `make_repo()` from scaffolds yet — would crash on `NotImplementedError`. The harness in task-001-11 exercises this controlled-error contract separately.
