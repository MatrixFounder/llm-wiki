# Task 003-00: Extract manifest consumer to neutral module [PHASE 0 — BLOCKING-FIRST REFACTOR]

## Meta

- **Bead ID**: `task-003-00-manifest-consumer-refactor`
- **Slug**: `manifest-consumer-refactor`
- **Maps to**: Issue **I-7.0**; RTM rows **R-41** (refactor enables clean in-process dispatch); also **R-43** (4 new tests).
- **Depends on**: none (entry point of TASK 003 v2)
- **Estimated time**: 0.5 day
- **Priority**: Critical (blocks every other bead in TASK 003 — no parallel work until this lands)

## Use Case Connection

- **UC-08 main scenario (with `--ingest`)**: the in-process dispatch path (step 12′-14′ of TASK.md §5.1) depends on the neutral module created by this bead.
- **UC-08 step 12′ import target**: `from scripts.wiki_skills._manifest_consumer import validate_manifest, index_from_manifest, WikiIngestError`.

## Task Goal

Extract three symbols from `scripts/wiki_skills/wiki_enrich.py` into a new neutral module `scripts/wiki_skills/_manifest_consumer.py`, eliminating the cross-skill coupling that Decision-15 would otherwise introduce (Decision-16):

1. `_validate_manifest(...)` → renamed to public `validate_manifest(manifest: dict[str, Any], expected_vault_id: str, vault_root: Path) -> None` (no leading underscore — promoted).
2. `index_from_manifest(manifest: dict[str, Any], vault_id: str, vault_root: Path, db_path: str | None = None) -> dict[str, Any]` (moved verbatim).
3. `class WikiIngestError(Exception)` (moved verbatim).

`wiki_enrich.py` MUST re-export all three symbols and assign `_validate_manifest = validate_manifest` so existing test imports keep working for one release cycle (back-compat hatch — exercised by the test suite, NOT dead code).

This bead is a **pure mechanical extract** (~131 LoC move surface per architecture-reviewer measurement of `wiki_enrich.py:152-282`). The function bodies are copied verbatim; only the rename + re-export shim differs.

## Stub-First Plan

**Phase 1 — Red→Green on stubs**:

1. Create `scripts/wiki_skills/_manifest_consumer.py` with stub bodies:
   ```python
   """Neutral manifest-consumer module — sub-layer below the skills tier.

   Created by TASK 003 / I-7.0 to break cross-skill coupling (Decision-16).
   Both wiki_enrich.py (back-compat re-export) and wiki_extract_concepts.py
   (new in TASK 003) import from this module.
   """
   from __future__ import annotations

   from pathlib import Path
   from typing import Any


   class WikiIngestError(Exception):
       """Raised when a manifest violates the v1.1 contract."""


   def validate_manifest(
       manifest: dict[str, Any],
       expected_vault_id: str,
       vault_root: Path,
   ) -> None:
       raise NotImplementedError("task-003-00 phase 1 stub")


   def index_from_manifest(
       manifest: dict[str, Any],
       vault_id: str,
       vault_root: Path,
       db_path: str | None = None,
   ) -> dict[str, Any]:
       raise NotImplementedError("task-003-00 phase 1 stub")
   ```

2. Create `tests/test_manifest_consumer.py` with 4 tests:
   - `test_validate_manifest_happy_path` — passes a minimal v1.1-compatible dict; asserts no exception.
   - `test_validate_manifest_rejects_non_ok_status` — `status="error"` → `WikiIngestError`.
   - `test_validate_manifest_rejects_vault_id_mismatch` — manifest `vault_id` differs from `expected_vault_id` → `WikiIngestError`.
   - `test_validate_manifest_rejects_path_traversal` — `written[0].path` starts with `../` → `WikiIngestError`.

   On the Phase-1 stub, all four tests fail with `NotImplementedError` (Red).

3. Run `pytest tests/test_manifest_consumer.py -v` — confirm Red (4 NotImplementedError failures).

**Phase 2 — Logic (mechanical move)**:

1. Open `scripts/wiki_skills/wiki_enrich.py`. Identify the three symbols:
   - `WikiIngestError` at lines 65-66 (verify exact lines on the current file).
   - `_validate_manifest` at lines 152-177.
   - `index_from_manifest` at lines 180-282.
2. **Move (cut, not copy)** the bodies into `_manifest_consumer.py`, replacing the stubs. Rename `_validate_manifest` → `validate_manifest` (no underscore). Preserve all internal imports (`json`, `Path`, `_safety`, etc.) — copy any helper imports needed.
3. In `wiki_enrich.py`, replace the moved code with:
   ```python
   from scripts.wiki_skills._manifest_consumer import (
       WikiIngestError,
       index_from_manifest,
       validate_manifest,
   )

   # Back-compat alias for one release cycle (TASK 003 I-7.0 acceptance bullet c).
   # Existing tests in tests/test_wiki_enrich.py (lines 21, 98, 104, 112, 467) import
   # _validate_manifest — those imports STAY POINTED HERE for one release cycle so
   # the alias is exercised, not dead code.
   _validate_manifest = validate_manifest
   ```
4. Update the internal call site at `wiki_enrich.py:388` (or wherever `_validate_manifest(...)` is invoked inside the same file): change to `validate_manifest(...)` (no underscore).
5. Re-run `pytest tests/test_manifest_consumer.py -v` — all 4 tests pass (Green).
6. Re-run `pytest tests/test_wiki_enrich.py -v` — all existing tests continue to pass via the back-compat alias.
7. Run full suite: `pytest tests/ -q` — **332 passed** (328 baseline + 4 new).

**Phase 3 — Stale-doc sweep (reviewer caveat 1)**:

1. Grep across the repo for any residual references to dropped v1 surfaces:
   ```bash
   grep -rn "manifest-file\|manifest-stdin\|R-44\|I-7.15\|dispatch_to_wiki_enrich" docs/ skills/ .claude/commands/ scripts/
   ```
2. Architecture-reviewer pre-flagged `docs/ARCHITECTURE.md` lines 179 + 429 as already-swept; bead verifies with grep that nothing slipped through. If any residue appears, remove it inline. PR diff must show `git grep` returns empty for the patterns above (with the exception of TASK.md itself, where the retraction is documented intentionally).

## Changes Description

### New Files

- `scripts/wiki_skills/_manifest_consumer.py` — three public symbols: `WikiIngestError`, `validate_manifest`, `index_from_manifest`. Module-level docstring explains the neutral-sub-layer role.
- `tests/test_manifest_consumer.py` — 4 new unit tests exercising the public surface directly.

### Changes in Existing Files

#### File: `scripts/wiki_skills/wiki_enrich.py`

- Remove the bodies of `WikiIngestError`, `_validate_manifest`, `index_from_manifest` (lines ~65-66, 152-177, 180-282).
- Add the three-symbol import from `_manifest_consumer`.
- Add `_validate_manifest = validate_manifest` alias.
- Update the internal call at line 388 from `_validate_manifest(...)` → `validate_manifest(...)`.
- Net change ≤ 200 LoC (acceptance bullet g).

#### File: `tests/test_wiki_enrich.py`

- **NO CHANGES** in this bead — the existing imports of `_validate_manifest` at lines 21, 98, 104, 112, 467 STAY POINTED at `wiki_enrich._validate_manifest` to exercise the back-compat alias. A separate follow-up bead (post-release) will migrate these imports and remove the alias.

### Component Integration

- After this bead lands, **all** subsequent TASK 003 beads (I-7.1..I-7.14) may begin. I-7.1 in particular pins `from scripts.wiki_skills._manifest_consumer import ...` at module top of `wiki_extract_concepts.py`.
- The signatures of `validate_manifest` and `index_from_manifest` become the **integration contract**. Any future refactor that breaks them is a coordinated change (TASK.md §1.3 non-goal note).

## Files Touched (explicit list)

- `scripts/wiki_skills/_manifest_consumer.py` (new)
- `scripts/wiki_skills/wiki_enrich.py` (modified — extract + re-export + alias)
- `tests/test_manifest_consumer.py` (new)
- (potentially) `docs/ARCHITECTURE.md` — sweep verification only; no edit expected (already swept inline by architect)

## Test Surface

- **New**: `tests/test_manifest_consumer.py`:
  - Phase-1: 4 tests assert `NotImplementedError` raised initially.
  - Phase-2: same 4 tests now pass with real validation behavior.
- **Touched (regression)**: `tests/test_wiki_enrich.py` — all existing tests continue to pass through the back-compat alias.

## Acceptance Criteria

- [ ] **R-41(a)**: `scripts/wiki_skills/_manifest_consumer.py` exists and exports `validate_manifest`, `index_from_manifest`, `WikiIngestError`.
- [ ] **R-41(b)**: `scripts/wiki_skills/wiki_enrich.py` re-exports the same three symbols.
- [ ] **R-41(c)**: `wiki_enrich._validate_manifest is wiki_enrich.validate_manifest` (back-compat alias preserved).
- [ ] **R-41(d)**: `wiki_enrich.py:388` internal call uses `validate_manifest(...)` (no underscore).
- [ ] **R-41(e)**: `tests/test_manifest_consumer.py` adds 4 new tests, all passing.
- [ ] **R-43(a-h)** baseline: full pytest sweep `pytest tests/ -q` → **332 passed** (328 baseline + 4 new), 0 failed.
- [ ] **`mypy --strict scripts/wiki_skills/`** → clean.
- [ ] **Net diff size**: `git diff --stat scripts/wiki_skills/ tests/test_manifest_consumer.py` shows ≤ **200 LoC** added/removed combined (acceptance bullet g in TASK.md).
- [ ] **Stale-doc sweep**: `grep -rn "manifest-file\|manifest-stdin\|R-44\|I-7.15\|dispatch_to_wiki_enrich" docs/ skills/ .claude/commands/ scripts/` returns empty (TASK.md is the only legitimate documenter of the retraction).

## Verification

```bash
# Phase 1 (Red)
pytest tests/test_manifest_consumer.py -v   # expect 4 failures (NotImplementedError)

# Phase 2 (Green)
pytest tests/test_manifest_consumer.py -v   # expect 4 passed
pytest tests/test_wiki_enrich.py -v         # expect all green (existing baseline preserved)
pytest tests/ -q                             # expect 332 passed, 0 failed

# Mypy
mypy --strict scripts/wiki_skills/

# Size guard
git diff --stat scripts/wiki_skills/_manifest_consumer.py scripts/wiki_skills/wiki_enrich.py tests/test_manifest_consumer.py
# expect insertions+deletions ≤ 200

# Stale-doc sweep
grep -rn "manifest-file\|manifest-stdin\|dispatch_to_wiki_enrich" docs/ skills/ .claude/commands/ scripts/ \
  | grep -v "docs/TASK.md\|docs/tasks/" \
  | grep -v "docs/plans/plan-004"
# expect empty
```

## Rollback

`git checkout scripts/wiki_skills/wiki_enrich.py && rm scripts/wiki_skills/_manifest_consumer.py tests/test_manifest_consumer.py`. Because the wiki_enrich.py body is restored verbatim, the consumer path returns to its pre-refactor state. No subsequent TASK 003 bead has shipped yet, so no breakage propagates.

## Notes

- This bead is the canonical example of "blocking-first refactor" — landing a clean module *before* any consumer writes code against it. The alternative (write `wiki_extract_concepts.py` first, refactor later) was rejected by Decision-16 on layering grounds.
- The 200-LoC ceiling is a "did something unexpected happen?" guard, NOT a hard limit on the legitimate move. Per architecture-reviewer caveat 3, if the diff legitimately exceeds 200 LoC because of additional shared imports, split into 003-00a (validate_manifest only) + 003-00b (index_from_manifest + WikiIngestError). Both halves still ship before any other TASK 003 bead.
- The back-compat alias survives **one release cycle**. A separate follow-up bead (not in TASK 003 scope) will deprecate it with a `DeprecationWarning` and migrate the test imports.
