# Task 003-v3-06: delete legacy LLM-call code path (the actual Decision-17 deliverable)

## Meta

- **Bead ID**: `task-003-v3-06-delete-llm-call`
- **Slug**: `delete-llm-call`
- **Maps to**: Issue **I-V3.1f**; RTM row **R-30**; Decision-17.
- **Depends on**: **task-003-v3-11a** (Phase -1; 6 legacy-shape `main()` tests deleted), **task-003-v3-00**, **task-003-v3-01**, **task-003-v3-02**, **task-003-v3-03**, **task-003-v3-04**, **task-003-v3-05** (all new logic landed), **task-003-v3-11** (Phase 3; 9 anthropic-mock function tests deleted).
- **Estimated time**: 0.25 day
- **Priority**: Critical (the actual deliverable of Decision-17; MUST be last among Phase-1 code-bearing beads so the suite stays green throughout).

## Use Case Connection

- Removes the v2 LLM call from the skill. After this bead, `wiki_extract_concepts.py` makes ZERO Anthropic SDK calls.

## Task Goal

**Delete dead code** that was preserved during Phase 1 for test-suite continuity:

1. `extract_concepts_llm()` function (~80 LoC).
2. `_build_extraction_prompt()` function (~30 LoC).
3. `_validate_extraction_schema` alias (the renamed-to `_validate_candidates_schema` from 003-v3-02 carried this alias for backward compatibility).
4. `_REQUIRED_LLM_KEYS` alias (the renamed-to `_REQUIRED_CANDIDATE_KEYS` from 003-v3-02 carried this alias).
5. `LLMUnavailableError` exception class.
6. `_MAX_SOURCE_BODY_CHARS` constant (replaced by `_MAX_SOURCE_BODY_BYTES` in 003-v3-01).
7. `import anthropic` and any other anthropic-SDK references.
8. Exit-3 (`LLM_API_UNAVAILABLE`) mapping in the (no-longer-present) v2 `main()` body.
9. `_build_legacy_parser` (renamed from `_build_parser` in 003-v3-00).
10. The v2 `main()` body that lived as dead code post-003-v3-00 (the subcommand dispatch in `main()` is now the only path).

Update module docstring to reflect v3.1 surface (zero LLM calls, two subcommands, calling-agent-driven synthesis).

## Stub-First Plan

### Phase 1 — n/a (pure delete; correctness verified by full sweep)

1. Edit `scripts/wiki_skills/wiki_extract_concepts.py`:
   - Remove the 10 items listed in Task Goal.
   - Update module docstring (top of file) to describe v3.1 architecture: deterministic prepare/apply skill, calling-agent-driven synthesis, no anthropic SDK call, exit codes 0/1/2/4/5/6 (NOT 0/1/2/3/4/5/6).
2. Verify by grep:
   ```bash
   grep -n "extract_concepts_llm\|_build_extraction_prompt\|LLMUnavailableError\|_MAX_SOURCE_BODY_CHARS\|import anthropic\|LLM_API_UNAVAILABLE\|_build_legacy_parser" scripts/wiki_skills/wiki_extract_concepts.py
   ```
   Expected: 0 matches.
3. Run `pytest tests/ -q` — assert ≥ 390 passed (Option A floor; this bead's correctness is "no test regression from immediately-prior bead 003-v3-11"; expected actual ≈ 436).

## Changes Description

### Edited files

- `scripts/wiki_skills/wiki_extract_concepts.py`: delete ~150 LoC of dead code; update docstring.

### Tests touched

- None directly; this bead depends on 003-v3-11a (Phase -1) having deleted the 6 legacy-shape `main()` tests AND 003-v3-11 (Phase 3) having deleted the 9 remaining anthropic-mock function tests.

## Component Integration

- After this bead lands, `scripts/wiki_skills/wiki_extract_concepts.py` should be ~600 LoC (down from v2's 803 LoC).
- The grep invariant `grep -n "extract_concepts_llm" scripts/wiki_skills/wiki_extract_concepts.py` → 0 lines is the contract.
- `_validate_candidates_schema` is now the only validator symbol. `_REQUIRED_CANDIDATE_KEYS` is the only constant.

## Files Touched

- `scripts/wiki_skills/wiki_extract_concepts.py` (only)

## Acceptance Criteria

- [ ] **R-30 (Decision-17)**: `scripts/wiki_skills/wiki_extract_concepts.py` no longer contains any of: `extract_concepts_llm`, `_build_extraction_prompt`, `LLMUnavailableError`, `_MAX_SOURCE_BODY_CHARS`, `_validate_extraction_schema` (alias deleted), `_REQUIRED_LLM_KEYS` (alias deleted), `import anthropic`, `LLM_API_UNAVAILABLE`, `_build_legacy_parser`.
- [ ] Module docstring describes v3.1 surface (deterministic prepare/apply, calling-agent synthesis, exit 0/1/2/4/5/6).
- [ ] `grep -n "anthropic" scripts/wiki_skills/wiki_extract_concepts.py` → 0 matches (case-insensitive: 0 matches).
- [ ] **Full pytest sweep**: `pytest tests/ -q` → ≥ 390 (Option A floor); expected actual ≈ 436 passed, 0 failed.
- [ ] `mypy --strict scripts/` → no issues.

## Verification

```bash
source .venv/bin/activate

# Invariant grep
grep -nE "extract_concepts_llm|_build_extraction_prompt|LLMUnavailableError|_MAX_SOURCE_BODY_CHARS|_validate_extraction_schema|_REQUIRED_LLM_KEYS|import anthropic|LLM_API_UNAVAILABLE|_build_legacy_parser" scripts/wiki_skills/wiki_extract_concepts.py
# expect: 0 matches

grep -ni "anthropic" scripts/wiki_skills/wiki_extract_concepts.py
# expect: 0 matches

pytest tests/ -q
# expect: ≥ 390 passed (Option A floor); actual ≈ 436

mypy --strict scripts/wiki_skills/wiki_extract_concepts.py

# Check LoC delta
wc -l scripts/wiki_skills/wiki_extract_concepts.py
# expect: ~600 (down from v2's 803)
```

## Rollback

`git checkout HEAD~1 scripts/wiki_skills/wiki_extract_concepts.py`. Test suite returns to immediately-prior-bead state.

## Notes

- This is the most consequential bead in the v3.1 task, but mechanically it's a delete. The work was done in earlier beads (the new surface was built; the old surface is now unreachable).
- After this bead, the `requirements.txt` change (003-v3-10) becomes safe — no Python import of `anthropic` remains in `scripts/`.
- Any v2-era TODO comments or `# H-X fix` comments referring to LLM-call sites should also be deleted as part of this sweep (incidental cleanup).
