# TASK 063-04 — **[STUB CREATION]** package, CLI surface, exit-code table

**Phase**: 2 (the rail) · **RTM**: R-063-11 · **Type**: code (stubs) · **Effort**: 2–3h
**Depends on**: — · **Unblocks**: 063-05 … 063-14

## Goal

The whole `wiki-extract-decisions` surface exists and is callable — returning **hardcoded stub
envelopes**. E2E tests pass **on the stubs**. No logic. This is the Stub-First boundary: the
interface, the exit-code contract, and the `no import anthropic` gate all land **before** there is
any logic that could violate them.

## Context — files (new)

```
scripts/wiki_skills/wiki_extract_decisions/
    __init__.py       # argparse (prepare|apply) + main(); stub prepare()/apply()
    __main__.py       # `python -m` entry (clone of wiki_extract_concepts/__main__.py)
    _errors.py        # error types + _envelope_from_parse_error  (the dependency SINK)
    _validation.py    # candidate schema constants + validators   (stubs)
    _pages.py         # typed-page writer                          (stub)
    _db.py            # source_state / typed-page reads            (stubs)
bin/wiki-extract-decisions                 # exec shim (clone bin/wiki-extract-concepts)
commands/wiki-extract-decisions.md         # the /slash command
```
Symlink into `.claude/commands/` per CLAUDE.md conventions (`bin/link-command.sh`).

**Read (precedent)**: `scripts/wiki_skills/wiki_extract_concepts/__init__.py` — the module docstring's
exit-code table, `_build_parser_v3`, the `prepare`/`apply` split, `emit()` from
`scripts/wiki_skills/_common`.

## The CLI

```
wiki-extract-decisions prepare --vault V --vault-root R --source-page S [--db-path P]
wiki-extract-decisions apply   --vault V --vault-root R --source-page S --source-hash H
                               (--candidates-file F | --candidates-stdin)
                               [--ingest] [--no-reconcile] [--prune] [--force]
                               [--orchestrator-id ID] [--db-path P]
```

## Exit-code table (pin it in the module docstring — it is the contract)

| code | meaning |
|---|---|
| 0 | success — incl. **`action: no_candidates`** (an empty candidate set is SUCCESS, R-063-7) and `action: unchanged` |
| 1 | argparse / usage |
| 2 | input validation: `SOURCE_NOT_FOUND`, `INVALID_SOURCE_PATH`, `SOURCE_TOO_LARGE`, `SOURCE_CHANGED_DURING_EXTRACTION`, `INVALID_SOURCE_HASH`, `INVALID_CANDIDATES_PATH`, `LAYOUT_CANNOT_INDEX_CLASSES` (prepare preflight), `TYPED_DIR_NOT_COVERED_BY_LAYOUT` |
| 4 | **contract violation ⇒ ZERO writes**: `EXTRACTION_PARSE_ERROR`, `CANDIDATES_TOO_LARGE`, `FIELD_TOO_LONG`, `UNKNOWN_FIELD`, `FIELD_QUOTE_NOT_IN_BODY`, `ONTOLOGY_VIOLATION`, `UNRESOLVED_REF`, `IN_BATCH_SLUG_COLLISION`, `DROPPED_CANDIDATE_STILL_REFERENCED`, `REQUIRES_STATUS_RECONCILIATION` |
| 5 | `PARTIAL_INDEX_FAILURE`, `DB_WRITE_FAILED`, `IDEMPOTENCY_UPDATE_FAILED` — `source_state` **NOT** updated ⇒ retry safe |
| 6 | `MANIFEST_INVALID` |

**Note the asymmetry with the precedent, deliberately:** `wiki_extract_concepts._validation` has
`_CANDIDATE_COUNT_MIN = 1`. **This skill sets `CANDIDATE_COUNT_MIN = 0`** (063-06). Cloning the 1
would make *"this note has no decisions"* an exit-4 failure — and the model's cheapest path to a green
run would be to **invent one**. Write the constant with that comment attached, in this bead, so no
later bead "restores parity".

## Steps

1. Create the package; every function raises `NotImplementedError` **except** `main()`/argparse and
   the two subcommand entrypoints, which emit a stub envelope:
   `prepare` → `{"action": "stub", "source_slug": …, "ontology": {}, "known_typed_pages": [],
   "existing_page_slugs": [], "validation": {…zeros…}}`, exit 0.
   `apply` → `{"action": "stub", "written": [], "reconciled": [], "stale": []}`, exit 0.
2. `bin/wiki-extract-decisions` + `commands/wiki-extract-decisions.md` + symlinks.
3. Docstrings describe the future logic in full (TDD stub rule 3) — the next bead's author reads them.

## Tests (RED first) — `tests/test_extract_decisions_cli.py` (new)

- `test_help_lists_both_subcommands` — `main(["--help"])` mentions `prepare` and `apply`.
- `test_no_subcommand_is_usage_error` — exit 1 (parity with the precedent's H-4 breaking change).
- `test_prepare_stub_envelope` / `test_apply_stub_envelope` — one JSON object on stdout, exit 0.
  *(These are the Stub-First E2E tests: they assert the hardcoded values and are REWRITTEN to assert
  real values in 063-05/063-12 — not deleted.)*
- `test_exit_code_table_is_documented` — every error string in the table above appears in the module
  docstring. Cheap, and it stops the table rotting.

## Exit criteria

- [ ] `pytest tests/ -q` ≥ 2477 passed. `mypy --strict scripts/` clean (the package is in the
      `scripts/` contract from bead 1 — stubs must be **typed**, not `Any`-shaped).
- [ ] **GREP-THE-SURFACES — I-2, a denominator claim ("no LLM-client import anywhere").**
      ⚠️ **BOTH import forms** (plan-review **M-8**): the house precedent
      `tests/test_wiki_sync.py:634-639` asserts `"import anthropic"` **and** `"from anthropic"`.
      v1 greps only the first — so `from anthropic import Anthropic` **slips straight through** a gate
      whose whole purpose is to stop it. *A gate narrower than the precedent it clones is a gate with
      a documented hole.*
      ```bash
      # enumerate the population, then assert over ALL of it — never spot-check one file
      find scripts/wiki_skills/wiki_extract_decisions -name '*.py' | tee /dev/stderr | \
        xargs grep -lE "import anthropic|from anthropic" ; test $? -ne 0
      ```
      Add it as a **test** (`test_no_anthropic_import_in_package`) that globs the package dir at
      runtime, so a *new file* added by a later bead is covered automatically. A grep over a
      hand-typed file list would be exactly this project's failure mode.
- [ ] **MUT (both forms — run each):** add `import anthropic` to any file ⇒ RED; add
      `from anthropic import Anthropic` to any file ⇒ **also RED**. v1's gate would have passed the
      second.
- [ ] `bin/wiki-extract-decisions prepare --help` runs from a clean shell.

## Rollback

Delete the package + bin shim + command file + symlinks. Nothing else references them.
