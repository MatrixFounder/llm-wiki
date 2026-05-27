# Task 003-01: `wiki_extract_concepts.py` argparse entry-point + stub helpers

## Meta

- **Bead ID**: `task-003-01-extract-concepts-entrypoint`
- **Slug**: `extract-concepts-entrypoint`
- **Maps to**: Issue **I-7.1**; RTM rows **R-30**, **R-31**, **R-42**.
- **Depends on**: task-003-00 (manifest-consumer module available for the module-top import)
- **Estimated time**: 0.5 day
- **Priority**: Critical (its helper stubs are the integration points filled by I-7.3..I-7.11)

## Use Case Connection

- **UC-08 step 1**: operator invokes `/wiki-extract-concepts ...` — this bead wires the CLI surface.
- **UC-08 step 2**: argparse path-validation (R-26 guard via `validate_inside_vault`).

## Task Goal

Create `scripts/wiki_skills/wiki_extract_concepts.py` with:
1. Full argparse surface (`--vault`, `--vault-root`, `--source-page`, `--db-path`, `--model`, `--ingest`) per R-31.
2. `main(argv)` function consistent with `wiki_enrich.py`'s shape (returns int exit code; calls helpers in sequence).
3. **Module-top import** of the neutral module (pinned for stable patch targets — see I-7.12 patch-target lock):
   ```python
   from scripts.wiki_skills._manifest_consumer import (
       WikiIngestError,
       index_from_manifest,
       validate_manifest,
   )
   ```
4. **Stub helpers** — every internal function defined as `raise NotImplementedError("task-003-NN <bead>")`:
   - `load_known_entities(repo, vault_id) -> list[dict]` (003-03)
   - `extract_concepts_llm(source_body, known_entities, model, max_tokens) -> list[dict]` (003-04)
   - `classify_candidates(llm_results, known_slugs) -> tuple[list, list]` (003-05)
   - `write_concept_page(vault_root, candidate, source_slug, today) -> Path` (003-06)
   - `upsert_extracted_entity(repo, vault_id, candidate, source_slug, today) -> str` (003-07b)
   - `upsert_entity_refs(repo, vault_id, source_slug, source_project, all_candidates) -> None` (003-08)
   - `check_idempotency(repo, vault_id, source_slug, current_hash) -> bool` (003-09)
   - `build_manifest(vault_id, source_slug, source_hash, create_list, mention_list, log_event, vault_root) -> dict` (003-10)
   - `dispatch_to_indexer(manifest_dict, vault_id, vault_root, db_path) -> dict` (003-11)
5. Exit-code mapping per R-42 (0 success/unchanged; 1 argparse; 2 source-not-found; 3 LLM unavailable; 4 EXTRACTION_PARSE_ERROR; 5 PARTIAL_INDEX_FAILURE; 6 MANIFEST_INVALID).

## Stub-First Plan

**Phase 1 — Stubs + E2E argparse test (Red→Green)**:

1. Write `scripts/wiki_skills/wiki_extract_concepts.py` with:
   - Module docstring referencing TASK 003 v2 and Decision-15/16.
   - Module-top imports (the three neutral-module symbols, stdlib, `IndexRepository` factory).
   - `main(argv: list[str] | None = None) -> int` with full argparse definition.
   - All 9 helper functions defined with `raise NotImplementedError("task-003-XX stub")` bodies and correct type annotations.
   - The `main(argv)` body should be a sequence of helper calls wrapped in `try/except` mapping errors to exit codes — even though every call will `NotImplementedError`, the wiring shape is in place.
   - The argparse error path (missing required flag) must reach exit 1 BEFORE any helper is invoked, so the Phase-1 E2E test passes without any helper logic.
2. Write `tests/test_wiki_extract_concepts.py` (initial Phase-1 fixtures only):
   - `test_argparse_missing_vault_returns_exit_1` — call `main([])` → SystemExit with code 2 (argparse default for missing arg) OR `main(["--vault-root","/x","--source-page","s"])` → exit 1.
   - `test_argparse_help_text_contains_ingest_flag` — call `main(["--help"])` (catch SystemExit) and assert `--ingest` appears in help text.
   - `test_module_imports_neutral_manifest_consumer` — `import scripts.wiki_skills.wiki_extract_concepts as wec; assert wec.validate_manifest is not None; assert wec.index_from_manifest is not None`.
   - `test_helpers_raise_not_implemented` — instantiate each helper with placeholder args and assert `NotImplementedError`.
3. Run `pytest tests/test_wiki_extract_concepts.py -v` — all 4 tests pass (the argparse + import shape works; the helpers correctly raise).

**Phase 2 — n/a**: the Phase-2 work for this bead is "all subsequent beads (003-03..003-11) replace the helper stubs one-by-one". The entry-point itself is complete after Phase 1.

## Changes Description

### New Files

- `scripts/wiki_skills/wiki_extract_concepts.py` — argparse + stubbed helpers (~150-200 LoC).
- `tests/test_wiki_extract_concepts.py` — Phase-1 argparse tests (4 tests).

### Argparse surface (R-31 detail)

```python
parser = argparse.ArgumentParser(prog="wiki-extract-concepts", ...)
parser.add_argument("--vault", required=True, help="Vault ID (registered in vaults table)")
parser.add_argument("--vault-root", required=True, type=Path, help="Absolute path to vault root directory")
parser.add_argument("--source-page", required=True, help="Source page slug or relative path within vault")
parser.add_argument("--db-path", default=None, help="Override global DB path (default: standard XDG location)")
parser.add_argument("--model", default="claude-sonnet-4-6", help="Anthropic model ID")
parser.add_argument("--ingest", action="store_true", help="In-process indexer dispatch (Decision-15) — call index_from_manifest after manifest emit")
parser.add_argument("--max-tokens", type=int, default=4096, help="LLM extraction max_tokens cap (R-33c)")
```

### Component Integration

- This entry-point becomes the single integration target for I-7.3..I-7.11. Each downstream bead replaces exactly one `NotImplementedError`.
- The module-top imports of `validate_manifest` + `index_from_manifest` + `WikiIngestError` from `_manifest_consumer` mean `unittest.mock.patch` sites in tests target `scripts.wiki_skills.wiki_extract_concepts.<symbol>` (the bound name in this module), NOT `scripts.wiki_skills._manifest_consumer.<symbol>` (the source) — see I-7.12 patch-target lock.

## Files Touched (explicit list)

- `scripts/wiki_skills/wiki_extract_concepts.py` (new)
- `tests/test_wiki_extract_concepts.py` (new)

## Test Surface

- **New**: `tests/test_wiki_extract_concepts.py` — 4 Phase-1 tests:
  - `test_argparse_missing_vault_returns_exit_1`
  - `test_argparse_help_text_contains_ingest_flag`
  - `test_module_imports_neutral_manifest_consumer`
  - `test_helpers_raise_not_implemented`

## Acceptance Criteria

- [ ] **R-30(c)**: `scripts/wiki_skills/wiki_extract_concepts.py` exists with `main(argv)` signature consistent with other wiki skills.
- [ ] **R-31(a-e)**: all six flags (`--vault`, `--vault-root`, `--source-page`, `--db-path`, `--model`, `--ingest`) present in argparse surface.
- [ ] **R-31(a) & R-31(b)**: missing `--vault` OR missing `--source-page` → argparse error + non-zero exit.
- [ ] **R-42(a)**: exit 1 on argument/usage error (verified by `test_argparse_missing_vault_returns_exit_1`).
- [ ] **R-42 baseline**: exit-code mapping placeholders in `main()` body for codes 2/3/4/5/6 are syntactically present (even if no helper raises them yet — they'll fill in via 003-04 and 003-11).
- [ ] All 4 Phase-1 tests pass: `pytest tests/test_wiki_extract_concepts.py -v`.
- [ ] **Module-top import lock**: `grep -n "from scripts.wiki_skills._manifest_consumer import" scripts/wiki_skills/wiki_extract_concepts.py` returns exactly one line, at the top of the file (before any function definition).
- [ ] `mypy --strict scripts/wiki_skills/wiki_extract_concepts.py` clean (with `NotImplementedError` bodies — mypy doesn't object to unreachable code in stubs because all are annotated returns).
- [ ] Full sweep `pytest tests/ -q` → **336 passed** (332 from 003-00 + 4 new).

## Verification

```bash
# Phase 1 (Green directly — stubs + argparse only)
pytest tests/test_wiki_extract_concepts.py -v   # expect 4 passed

# Module-top import lock
grep -n "from scripts.wiki_skills._manifest_consumer" scripts/wiki_skills/wiki_extract_concepts.py
# expect: exactly one line, near the top

# Help text
python -m scripts.wiki_skills.wiki_extract_concepts --help | grep -E "ingest|vault|source-page"
# expect: all three flags visible

# Argparse error path
python -m scripts.wiki_skills.wiki_extract_concepts ; echo "exit=$?"
# expect: exit=2 (argparse) or exit=1 (post-argparse)

# Mypy
mypy --strict scripts/wiki_skills/wiki_extract_concepts.py
```

## Rollback

`rm scripts/wiki_skills/wiki_extract_concepts.py tests/test_wiki_extract_concepts.py`. No other repo file modified; trivially reversible.

## Notes

- The Phase-1 stubs are intentionally exhaustive (9 helpers) so that downstream beads (003-03..003-11) have a clear, named target to replace. This is the explicit Stub-First pattern: scaffold the call graph first, fill in bodies after.
- `--max-tokens` defaults to 4096 (R-33c cap). Operator may override for long source pages.
- `--ingest` is a boolean flag (no value); default is False. When False, only manifest emitted to stdout; when True, in-process dispatch occurs (Decision-15) — but the dispatch logic lands in 003-11.
