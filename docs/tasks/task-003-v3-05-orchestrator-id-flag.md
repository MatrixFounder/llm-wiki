# Task 003-v3-05: `--orchestrator-id` flag on `apply` + plumbing through `upsert_extracted_entity`

## Meta

- **Bead ID**: `task-003-v3-05-orchestrator-id-flag`
- **Slug**: `orchestrator-id-flag`
- **Maps to**: Issue **I-V3.1g**; RTM row **R-37**; Q9 (canonicalized_by); H-8.
- **Depends on**: task-003-v3-03 (apply argparse exists).
- **Estimated time**: 0.25 day
- **Priority**: High (recovers v2's audit-trail attribution lost by Q9-v3.0).

## Use Case Connection

- **UC-08 v3.1 Step 8**: orchestrator passes `--orchestrator-id "claude-opus-4-7"` so `canonicalized_by = "llm:claude-opus-4-7@2026-05-28"` in the entity row. Operator who omits the flag gets the literal `"orchestrator"` (honest unknown beats hallucinated specific).

## Task Goal

1. **Argparse extension**: add `--orchestrator-id STRING` (optional) to the `apply` subparser. Validation regex: `^[a-z0-9._:@-]{1,64}$`. argparse-level type validator that raises `argparse.ArgumentTypeError` on regex fail (so the operator gets exit 2 / argparse error, NOT exit 4).
2. **Plumbing**: extend `upsert_extracted_entity` signature with `orchestrator_id: str = "orchestrator"`. Inside the function, compute `canonicalized_by = f"llm:{orchestrator_id}@{today.isoformat()}"`. Default value is the literal string `"orchestrator"`.
3. **Apply call site**: in `apply()` body (003-v3-03), pass `orchestrator_id=args.orchestrator_id`.

## Stub-First Plan

### Phase 1 — Logic + 3 new tests (Red→Green)

1. In `scripts/wiki_skills/wiki_extract_concepts.py`:
   - Add module-level constant + helper:
     ```python
     _ORCHESTRATOR_ID_RE = re.compile(r"^[a-z0-9._:@-]{1,64}$")

     def _validate_orchestrator_id(value: str) -> str:
         if not _ORCHESTRATOR_ID_RE.match(value):
             raise argparse.ArgumentTypeError(
                 f"--orchestrator-id {value!r} must match regex "
                 f"^[a-z0-9._:@-]{{1,64}}$"
             )
         return value
     ```
   - Edit `_build_parser_v3()`'s `apply` subparser:
     ```python
     apply_sp.add_argument(
         "--orchestrator-id",
         type=_validate_orchestrator_id,
         default="orchestrator",
         help="Free-form orchestrator identifier (e.g., 'claude-opus-4-7'). "
              "Populates entities.canonicalized_by. Regex: ^[a-z0-9._:@-]{1,64}$",
     )
     ```
   - Edit `upsert_extracted_entity(repo, vault_id, candidate, source_slug, today, orchestrator_id="orchestrator")`:
     - Replace the existing `canonicalized_by = "llm:claude-sonnet-4-6@..."` (or whatever v2 hard-coded) with `canonicalized_by = f"llm:{orchestrator_id}@{today.isoformat()}"`.
   - Edit `apply()` call site: `upsert_extracted_entity(repo, args.vault, cand, source_slug, today, orchestrator_id=args.orchestrator_id)`.

2. Add 3 new tests:
   - `test_apply_orchestrator_id_valid_populates_canonicalized_by_H8` — pass `--orchestrator-id claude-opus-4-7`; assert entity row has `canonicalized_by = "llm:claude-opus-4-7@<today>"`.
   - `test_apply_orchestrator_id_invalid_regex_argparse_error_H8` — pass `--orchestrator-id "with spaces"`; assert SystemExit 2 (argparse error).
   - `test_apply_orchestrator_id_default_is_orchestrator_H8` — omit the flag; assert entity row has `canonicalized_by = "llm:orchestrator@<today>"`.

3. Run `pytest tests/test_wiki_extract_concepts.py -k orchestrator -v` → 3 new tests pass.

### Phase 2 — n/a

## Changes Description

### Edited files

- `scripts/wiki_skills/wiki_extract_concepts.py`:
  - Add `_ORCHESTRATOR_ID_RE` + `_validate_orchestrator_id` helper.
  - Argparse `apply` subparser adds `--orchestrator-id`.
  - `upsert_extracted_entity` accepts + uses `orchestrator_id`.
  - `apply()` passes `args.orchestrator_id` through.
- `tests/test_wiki_extract_concepts.py`: add 3 new tests.

## Component Integration

- `_lookup_entity_row` (v2 helper, unchanged) reads `canonicalized_by` from the row but doesn't construct it. The construction happens inside `upsert_extracted_entity`.
- v2 tests for `upsert_extracted_entity` that asserted `canonicalized_by="llm:claude-sonnet-4-6@..."` need to be updated to assert against `"llm:orchestrator@..."` (the new default). This is part of 003-v3-11 (test refactor) — note that this bead lands BEFORE 003-v3-11 and may cause those v2 assertions to fail temporarily UNLESS we update them in lockstep here.

   **Resolution**: this bead also updates the affected v2 assertions in `tests/test_wiki_extract_concepts.py` (estimated 2-3 tests). The full 12-LLM-mock-test deletion happens in 003-v3-11.

## Files Touched

- `scripts/wiki_skills/wiki_extract_concepts.py`
- `tests/test_wiki_extract_concepts.py` (3 new tests + ~2-3 updates to v2 canonicalized_by assertions)

## Acceptance Criteria

- [ ] **R-37 (H-8)**: `canonicalized_by = f"llm:{orchestrator_id}@{today}"` with default `"orchestrator"`.
- [ ] argparse-level regex validation; invalid value → argparse error (exit 2 / SystemExit 2).
- [ ] 3 new tests pass.
- [ ] **Full pytest sweep**: `pytest tests/ -q` → 430 (post-04) + 3 = **≥ 433 passed, 0 failed** (per PLAN §2 suite-size table).
- [ ] `mypy --strict scripts/wiki_skills/wiki_extract_concepts.py` clean.

## Verification

```bash
source .venv/bin/activate

pytest tests/test_wiki_extract_concepts.py -k orchestrator -v
# expect: 3 passed

pytest tests/ -q
# expect: ≥ 433 passed

mypy --strict scripts/wiki_skills/wiki_extract_concepts.py
```

## Rollback

Revert edits. Test count drops back to 430 (post-04 baseline per PLAN §2).

## Notes

- The regex `^[a-z0-9._:@-]{1,64}$` allows model name (`claude-opus-4-7`) AND extended forms like `claude-opus-4-7@anthropic` or `gemini-1.5-pro.beta`. Stays strict enough to prevent newlines / control chars / shell metachars.
- The default `"orchestrator"` is the literal string per Q9-v3.1 ("honest unknown beats hallucinated specific"). Operators who care about audit trail will pass their model name explicitly.
