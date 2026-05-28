# Task 003-v3-00: argparse subparser scaffold (`prepare` + `apply`)

## Meta

- **Bead ID**: `task-003-v3-00-argparse-subparser-scaffold`
- **Slug**: `argparse-subparser-scaffold`
- **Maps to**: Issue **I-V3.1a**; RTM rows **R-30**, **R-31**, **R-42**.
- **Depends on**: **task-003-v3-11a** (must complete first — 11a removes the 6 legacy-shape `main([... legacy args ...])` tests that would otherwise fail under this bead's `add_subparsers(required=True)` change). No other deps.
- **Estimated time**: 0.5 day
- **Priority**: Critical (blocks every code-bearing v3.1 bead; gated on 11a per Option A green-throughout invariant)

## Use Case Connection

- **UC-08 v3.1 Step 1**: operator invokes `/wiki-extract-concepts`; calling agent reads workflow; first subprocess call is `wiki-extract-concepts prepare ...`.
- **UC-08 v3.1 A6** legacy-invocation breakage: operator running v2 form (no subcommand) sees a helpful argparse error pointing at the new surface (H-4).

## Task Goal

Refactor the argparse layer of `scripts/wiki_skills/wiki_extract_concepts.py` to support two subcommands:

1. **`prepare`** — pre-flight (recon + idempotency check). Reads source, emits JSON for orchestrator consumption.
2. **`apply`** — write path. Consumes operator-synthesized candidates JSON, validates, writes concept pages + entities + refs, emits manifest.

Both subcommands are **stub functions** in this bead (`raise NotImplementedError("task-003-v3-NN")`); logic lands in 003-v3-01..05.

The legacy v2 `main()` body, `extract_concepts_llm()`, `_build_extraction_prompt()`, and `LLMUnavailableError` remain in the module file for now (deleted in 003-v3-06) — this preserves a green test suite throughout Phase 1.

## Stub-First Plan

### Phase 1 — Stubs + E2E argparse tests (Red→Green)

1. Edit `scripts/wiki_skills/wiki_extract_concepts.py`:
   - Rename existing `_build_parser` → `_build_legacy_parser` (will be removed in 003-v3-06).
   - Add new `_build_parser_v3() -> argparse.ArgumentParser` that uses `add_subparsers(dest="cmd", required=True)` with two subparsers:
     - `prepare`: args `--vault`, `--vault-root` (Path), `--source-page`, `[--db-path]`. NO `--model`, NO `--max-tokens`, NO `--ingest`.
     - `apply`: args `--vault`, `--vault-root` (Path), `--source-page`, `--source-hash HEX` (REQUIRED), `[--db-path]`, `[--ingest]`. Mutex group: `--candidates-file PATH | --candidates-stdin`. `--orchestrator-id` is added in 003-v3-05 (NOT in this bead).
   - Add stub functions at module-level:
     ```python
     def prepare(args: argparse.Namespace) -> int:
         """`wiki-extract-concepts prepare` subcommand — implemented in task-003-v3-01."""
         raise NotImplementedError("task-003-v3-01 prepare subcommand")

     def apply(args: argparse.Namespace) -> int:
         """`wiki-extract-concepts apply` subcommand — implemented in task-003-v3-03."""
         raise NotImplementedError("task-003-v3-03 apply subcommand")
     ```
   - Replace `main()` body with a dispatch shim:
     ```python
     def main(argv: list[str] | None = None) -> int:
         args = _build_parser_v3().parse_args(argv)
         if args.cmd == "prepare":
             return prepare(args)
         if args.cmd == "apply":
             return apply(args)
         # argparse(required=True) makes this unreachable, but mypy-strict
         # likes the safety net.
         return 1
     ```
2. Add tests to `tests/test_wiki_extract_concepts.py`:
   - `test_argparse_no_subcommand_returns_helpful_error` — invoke `_build_parser_v3().parse_args([])` inside a SystemExit context; assert exit code 2 (argparse default); capture stderr; assert it contains both `prepare` and `apply`.
   - `test_argparse_prepare_subparser_exists` — parse `["prepare", "--vault", "X", "--vault-root", "/tmp", "--source-page", "S"]`; assert `args.cmd == "prepare"`.
   - `test_argparse_apply_subparser_exists` — parse `["apply", "--vault", "X", "--vault-root", "/tmp", "--source-page", "S", "--source-hash", "deadbeef", "--candidates-stdin"]`; assert `args.cmd == "apply"`, `args.source_hash == "deadbeef"`.
   - `test_main_dispatches_to_prepare_stub` — `main(["prepare", ...])` raises `NotImplementedError("task-003-v3-01 ...")`.
   - `test_main_dispatches_to_apply_stub` — `main(["apply", ...])` raises `NotImplementedError("task-003-v3-03 ...")`.
   - `test_argparse_top_level_help_shows_subcommands` (replacement for the 11a-deleted `test_argparse_help_text_contains_ingest_flag`) — `wec.main(["--help"])` → `SystemExit(0)`; stdout contains `{prepare,apply}` choices.
3. Rename the surviving `test_argparse_missing_vault_returns_exit` (line 28 — calls `wec.main([])`) → `test_argparse_no_args_returns_exit_2`. Mechanical rename; assertion `ei.value.code == 2` continues to hold (argparse now fires SystemExit(2) on missing required subcommand instead of missing `--vault`).
4. Run `pytest tests/test_wiki_extract_concepts.py -v` — all **51 surviving** tests pass (6 legacy-shape tests were deleted in 003-v3-11a; their regression intent is migrated to 003-v3-01/003-v3-03) + **6 new** tests pass = **57 total in the file** after this bead.

### Phase 2 — n/a

The Phase-2 logic for this bead is "subsequent beads (003-v3-01..05) replace the stubs". The argparse layer is complete after Phase 1.

## Changes Description

### Edited files

- `scripts/wiki_skills/wiki_extract_concepts.py`:
  - Add `_build_parser_v3()` with subparsers.
  - Add `prepare()` and `apply()` stub functions.
  - Replace `main()` body with subcommand-dispatch shim.
  - **Preserve**: `_build_legacy_parser` (renamed from `_build_parser`), all v2 logic, `extract_concepts_llm`, `_build_extraction_prompt`, `LLMUnavailableError`, `_MAX_SOURCE_BODY_CHARS`, `import anthropic`. These die in 003-v3-06.

### New tests

- 6 new tests in `tests/test_wiki_extract_concepts.py` (5 dispatch/subparser tests + 1 replacement help-text test, listed above).
- 1 mechanical rename of `test_argparse_missing_vault_returns_exit` → `test_argparse_no_args_returns_exit_2`.

## Component Integration

- The argparse refactor is the entry point of the v3.1 surface. Every Phase-1 bead (003-v3-01..05) fills in either the `prepare` body, the `apply` body, the validator, or the `write_concept_page` helper that `apply` calls.
- Module-top imports of `validate_manifest`, `index_from_manifest`, `WikiIngestError` remain unchanged — the patch-target lock is preserved.
- `_MAX_SOURCE_BODY_BYTES` and `_MAX_CANDIDATES_BYTES` constants are defined in 003-v3-01 and 003-v3-03 respectively (NOT this bead).

## Files Touched (explicit list)

- `scripts/wiki_skills/wiki_extract_concepts.py` (modified)
- `tests/test_wiki_extract_concepts.py` (5 new tests added)

## Acceptance Criteria

- [ ] **R-30(c)**: `main(argv)` dispatches via `subparsers(required=True)`.
- [ ] **R-30**: `_build_parser_v3()` defines both `prepare` and `apply` subparsers.
- [ ] **R-31 (prepare)**: argparse for `prepare` accepts `--vault`, `--vault-root`, `--source-page`, `[--db-path]`. Does NOT accept `--model`, `--max-tokens`, `--ingest` (those flags removed from prepare surface per Decision-17).
- [ ] **R-31 (apply, partial)**: argparse for `apply` accepts `--vault`, `--vault-root`, `--source-page`, `--source-hash` (REQUIRED), `[--db-path]`, `[--ingest]`, mutex group `--candidates-file / --candidates-stdin`. `--orchestrator-id` is added later (003-v3-05).
- [ ] Both `prepare()` and `apply()` are defined as module-level functions and raise `NotImplementedError` with a descriptive message referencing the bead that fills them in.
- [ ] **H-4 BREAKING CHANGE smoke**: `main([])` AND `main(["--vault", "X"])` (legacy v2 form, no subcommand) → `SystemExit(2)` with stderr containing `prepare` and `apply` strings.
- [ ] **6 new tests pass** (5 dispatch/subparser tests + replacement help-text test): `pytest tests/test_wiki_extract_concepts.py -k "argparse or dispatches" -v` → 6 passed (note: `test_argparse_no_args_returns_exit_2` is the renamed survivor — still counts toward this filter).
- [ ] **All 51 surviving v2 tests pass** (after 11a removed 6 legacy-shape tests): `pytest tests/test_wiki_extract_concepts.py -q` reports 51 + 6 = **57 passed in this file**.
- [ ] **Full pytest sweep**: `pytest tests/ -q` → 390 (post-11a baseline) + 6 (new) = **≥ 396 passed, 0 failed**. (No regression vs. pre-11a baseline; net +0 because 11a removed 6 and 00 adds 6.)
- [ ] `mypy --strict scripts/wiki_skills/wiki_extract_concepts.py` clean.

## Verification

```bash
source .venv/bin/activate
pytest tests/test_wiki_extract_concepts.py -k "argparse or dispatches" -v
# expect: 6 passed (5 new dispatch/subparser tests + 1 renamed survivor `test_argparse_no_args_returns_exit_2`)

pytest tests/ -q
# expect: ≥ 396 passed (390 post-11a baseline + 6 new = 396 per PLAN §2 suite-size table)

mypy --strict scripts/wiki_skills/wiki_extract_concepts.py
# expect: Success: no issues found

python -m scripts.wiki_skills.wiki_extract_concepts 2>&1 | head -5
# expect: argparse error referencing 'prepare' and 'apply'

python -m scripts.wiki_skills.wiki_extract_concepts prepare --help | head -10
# expect: --vault, --vault-root, --source-page; NO --model, NO --max-tokens, NO --ingest

python -m scripts.wiki_skills.wiki_extract_concepts apply --help | head -10
# expect: --vault, --vault-root, --source-page, --source-hash, --candidates-file/--candidates-stdin
```

## Rollback

Revert `scripts/wiki_skills/wiki_extract_concepts.py` to its pre-bead state. Remove 6 new tests from `tests/test_wiki_extract_concepts.py`; restore the `test_argparse_missing_vault_returns_exit` name. NOTE: rollback of 003-v3-00 does NOT also rollback 003-v3-11a — if you want to also un-delete the 6 legacy-shape tests, separately revert 003-v3-11a's commit.

## Notes

- The v2 `main()` body is preserved as the OLD body and is unreachable from `main()` after the dispatch refactor; it remains in the file as dead code until 003-v3-06 deletes it. This is acceptable because (a) mypy doesn't object to unused functions; (b) `extract_concepts_llm()` and friends remain importable (003-v3-11 still has 9 anthropic-mock function tests against them until that bead deletes them); (c) the deletion of legacy code happens AFTER both 003-v3-11 and the regression-migration tests in 003-v3-01/003-v3-03 land.
- **Option A green-throughout invariant** (decided 2026-05-28 adversarial review): 11a → 00 → 01..05 → 11 → 06 → 10 ordering ensures `pytest tests/ -q` floor stays at ≥ 390 between any two bead boundaries (was originally claimed ≥ 396, but that was unachievable — the 6 legacy-shape tests would have failed at 00's argparse change).
- After this bead lands, `bin/wiki-extract-concepts` wrapper continues to work — it's a pass-through that delegates to `python -m`. Legacy invocation (`bin/wiki-extract-concepts --vault X --source-page Y` with no subcommand) now fails at argparse with a `prepare`/`apply` hint — that IS the BREAKING CHANGE.
