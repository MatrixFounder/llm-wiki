# Task 003-v3-12: refactor `tests/test_wiki_extract_concepts_integration.py` (canned candidates fixture; prepare+apply subprocess pattern)

## Meta

- **Bead ID**: `task-003-v3-12-integration-test-refactor`
- **Slug**: `integration-test-refactor`
- **Maps to**: Issue **I-V3.7**; RTM row **R-43**.
- **Depends on**: task-003-v3-03 (apply subcommand exists). Parallel-safe with 003-v3-09, 11.
- **Estimated time**: 0.5 day
- **Priority**: Critical.

## Use Case Connection

- Integration tests cover the prepare+apply round-trip end-to-end (subprocess invocation; real sqlite; real filesystem). Mirrors the operator workflow without an actual orchestrator LLM call.

## Task Goal

Refactor `tests/test_wiki_extract_concepts_integration.py`:

1. **Drop the anthropic mock** infrastructure.
2. **Rename + restructure fixture**: `tests/fixtures/source_extract/llm-response.json` → `tests/fixtures/source_extract/candidates.json`. Strip the metadata wrapper (the v2 LLM-response had a top-level object with the array nested inside; v3.1 candidates JSON is just the raw `[{...}]` array per Q6).
3. **Refactor 3 integration tests** to use the prepare+apply subprocess pattern:
   - **`test_integration_first_extraction`**: seed a vault with `_sources/<slug>.md`; invoke `prepare` via subprocess → capture JSON; load canned candidates JSON; invoke `apply --candidates-file <fixture> --source-hash <hash>` via subprocess; assert exit 0, manifest JSON on stdout, `_concepts/<slug>.md` exists on disk, entity row in DB.
   - **`test_integration_unchanged_on_rerun`**: as above; then re-invoke `prepare`; assert `is_unchanged=true`; orchestrator-level short-circuit (UC-09 v3.1).
   - **`test_integration_with_ingest`**: as `test_integration_first_extraction` but pass `--ingest` to apply; assert combined `{extraction, index}` envelope; assert indexer mirrored entity into FTS5 / index tables.

## Stub-First Plan

### Phase 1 — Fixture rename + 3 tests refactored

1. Move + restructure fixture:
   ```bash
   git mv tests/fixtures/source_extract/llm-response.json tests/fixtures/source_extract/candidates.json
   # Edit candidates.json to be a raw [{...}] array (no metadata wrapper).
   ```
2. Edit `tests/test_wiki_extract_concepts_integration.py`:
   - Remove `import unittest.mock` calls targeting anthropic.
   - Replace each test body with the subprocess pattern (use `subprocess.run` with `python -m scripts.wiki_skills.wiki_extract_concepts ...`).
   - Use `pytest tmpdir` fixture for vault root; `:memory:` SQLite per test (or per-tmpdir DB file path).
3. Run `pytest tests/test_wiki_extract_concepts_integration.py -v` → 3 tests pass.

### Phase 2 — n/a

## Changes Description

### Renamed files

- `tests/fixtures/source_extract/llm-response.json` → `tests/fixtures/source_extract/candidates.json` (restructured).

### Edited files

- `tests/test_wiki_extract_concepts_integration.py`: full rewrite of 3 test bodies.

## Component Integration

- The fixture file is now the contract that `apply --candidates-file <fixture>` consumes. Format matches `.agent/skills/concept-extraction/SKILL.md` (003-v3-07) documentation.
- Tests use the actual subprocess CLI invocation (vs. importing `main()` directly) — closer to operator reality; catches argparse + dispatch regressions.

## Files Touched

- `tests/fixtures/source_extract/candidates.json` (renamed from llm-response.json; restructured)
- `tests/test_wiki_extract_concepts_integration.py` (rewrite of 3 tests)

## Acceptance Criteria

- [ ] **R-43**: 3 integration tests pass.
- [ ] `grep -nE "anthropic|mock\\.patch|LLMUnavailableError" tests/test_wiki_extract_concepts_integration.py` → 0 matches.
- [ ] Fixture file `tests/fixtures/source_extract/candidates.json` is a raw `[{...}]` JSON array (parseable as a list).
- [ ] **Full pytest sweep**: `pytest tests/ -q` → no regression from immediately-prior bead's count.

## Verification

```bash
source .venv/bin/activate

# Fixture renamed + restructured
test -f tests/fixtures/source_extract/candidates.json && echo "OK: fixture exists"
test ! -f tests/fixtures/source_extract/llm-response.json && echo "OK: old fixture gone"
python -c "import json; d = json.load(open('tests/fixtures/source_extract/candidates.json')); assert isinstance(d, list); print(f'OK: array with {len(d)} candidates')"

# 3 tests pass
pytest tests/test_wiki_extract_concepts_integration.py -v
# expect: 3 passed

# No anthropic refs
grep -nE "anthropic|mock\\.patch|LLMUnavailableError" tests/test_wiki_extract_concepts_integration.py
# expect: empty

# Full sweep
pytest tests/ -q
# expect: no regression
```

## Rollback

`git checkout HEAD~1 tests/fixtures/source_extract/ tests/test_wiki_extract_concepts_integration.py`.

## Notes

- Subprocess pattern: `subprocess.run([sys.executable, "-m", "scripts.wiki_skills.wiki_extract_concepts", "prepare", ...], capture_output=True, text=True)`. Use `text=True` for utf-8 stdout/stderr.
- Pass `--db-path` pointing at `tmp_path / "test.db"` so each test is isolated.
- For the `--ingest` test, the in-process `dispatch_to_indexer` does the indexer work — no extra subprocess hop. The combined `{extraction, index}` envelope shape is asserted on stdout.
