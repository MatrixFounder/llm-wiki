# Task 003-v3-01: `prepare` subcommand implementation

## Meta

- **Bead ID**: `task-003-v3-01-prepare-subcommand`
- **Slug**: `prepare-subcommand`
- **Maps to**: Issue **I-V3.1b**; RTM rows **R-31**, **R-32**, **R-39**, **R-42**; Q4, Q5, Q16; M-3 (SOURCE_TOO_LARGE), M-1 (missing_concept_files).
- **Depends on**: task-003-v3-00 (subparser scaffold exists).
- **Estimated time**: 0.75 day
- **Priority**: Critical (blocks `apply` since apply consumes `source_hash` emitted by prepare).

## Use Case Connection

- **UC-08 v3.1 Step 1+2+3**: prepare is the recon subcommand the orchestrator runs first. Emits `source_path`, `source_hash`, `is_unchanged`, `known_concepts`, `missing_concept_files`. Orchestrator short-circuits if `is_unchanged=true` (UC-09 v3.1).
- **UC-09 v3.1**: idempotency check happens here; no LLM call needed in the unchanged case.

## Task Goal

Implement `prepare(args) -> int` in `scripts/wiki_skills/wiki_extract_concepts.py` to:

1. Resolve `--source-page` (slug-form or relative path) inside `--vault-root` (re-use the v2 `main()` resolution logic — `_sources/<slug>.md` first, fallback to relative path).
2. Validate `INVALID_SOURCE_PATH` (absolute) and `SOURCE_NOT_FOUND` (file missing or outside vault) per v2 behaviour (exit 2 envelopes preserved).
3. `INVALID_SOURCE_SLUG` check on the derived `source_slug` (preserved from v2).
4. **NEW (M-3)**: `stat().st_size` check against `_MAX_SOURCE_BODY_BYTES = 10_485_760` BEFORE `read_text()` — reject with `SOURCE_TOO_LARGE` (exit 2 envelope) if oversized.
5. Read body, compute `source_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()`.
6. Open the repo (existing v2 pattern).
7. Query `source_state` (via existing `check_idempotency` helper, NOT `update_idempotency_state`) — returns `is_unchanged: bool`.
8. Call `load_known_entities(repo, args.vault)` (existing v2 helper, unchanged).
9. **NEW (M-1)**: build `missing_concept_files: list[str]` — iterate over known entities; for each, check whether `vault_root / "_concepts" / f"{slug}.md"` exists; if not, append `slug` to the list. (P-9 / Q16 deferred — this is the eager O(N) impl; KNOWN_ISSUES P-9 documents future lazy variant.)
10. Emit JSON envelope to stdout:
    ```json
    {
      "vault_id": "<vault>",
      "source_slug": "<slug>",
      "source_path": "<absolute>",
      "source_hash": "<sha256>",
      "is_unchanged": false,
      "known_concepts": [...],
      "missing_concept_files": ["<slug1>", "<slug2>"]
    }
    ```
11. Return exit code 0 on success, exit code 2 on input-validation failure.

## Stub-First Plan

### Phase 1 — Stub + 6 new unit tests (Red→Green)

1. In `scripts/wiki_skills/wiki_extract_concepts.py`:
   - Add module-level constant:
     ```python
     # M-3 (TASK 003 v3.1): DoS protection on prepare's sha256+read pipeline.
     # Stat-checks st_size BEFORE read_text to bound memory.
     _MAX_SOURCE_BODY_BYTES = 10_485_760  # 10 MiB
     ```
   - Replace `prepare()` stub body with the full implementation (logic listed above). Use `emit({...})` from `_common` for envelope output (consistent with v2 main()).
2. Add 7 new tests to `tests/test_wiki_extract_concepts.py` (the original 6 + 1 ingest-partial-failure C-1 lives in 003-v3-03; 2 of the 7 below are explicit regression migrations from 003-v3-11a):
   - `test_prepare_happy_path` — seed a vault directory with `_sources/sample-doc.md`; run `prepare(args)`; capture stdout; assert JSON has `is_unchanged=false`, `source_hash` is 64-char hex, `known_concepts == []`, `missing_concept_files == []`.
   - `test_prepare_source_not_found` — pass a non-existent `--source-page`; assert exit 2, envelope `error="SOURCE_NOT_FOUND"`.
   - `test_prepare_invalid_slug` — seed `_sources/Foo.Bar.md`; pass `--source-page=Foo.Bar`; assert exit 2, envelope `error="INVALID_SOURCE_SLUG"`. **H-3 regression migration from 003-v3-11a** (was `test_main_rejects_invalid_source_slug` at line 486 of pre-bead test file).
   - `test_prepare_invalid_source_path_absolute` — pass `--source-page=/etc/passwd`; assert exit 2, envelope `error="INVALID_SOURCE_PATH"`. **H-1 regression migration from 003-v3-11a** (was `test_main_rejects_absolute_source_page_path` at line 458 of pre-bead test file). Critical: also assert that NO `_concepts/*.md` files were written before the error (same invariant H-1 originally guarded).
   - `test_prepare_idempotency_match_returns_unchanged_true` — seed source file; insert prior `source_state` row with matching hash; assert `is_unchanged=true`.
   - `test_prepare_source_too_large_M3` — seed a file ≥ 10_485_761 bytes (use `tempfile` + write 10 MiB + 1 byte of `\x00`); assert exit 2, envelope `error="SOURCE_TOO_LARGE"`, envelope does NOT contain the file content.
   - `test_prepare_missing_concept_files_warns` — seed vault with 3 known entities in the DB; create on-disk pages for only 2 of them; assert prepare's JSON has `missing_concept_files=["<the-missing-slug>"]`.
3. Run `pytest tests/test_wiki_extract_concepts.py -k prepare -v` → 7 new tests pass. The `test_main_dispatches_to_prepare_stub` test added in 003-v3-00 is REMOVED here (since prepare no longer raises NotImplementedError); replaced by `test_prepare_happy_path`. Net delta of this bead: +7 new tests − 1 removed stub-dispatch test = **+6 tests**.

### Phase 2 — n/a (logic lands in Phase 1 — Stub-First applies via Red→Green test cycle)

## Changes Description

### Edited files

- `scripts/wiki_skills/wiki_extract_concepts.py`:
  - Add `_MAX_SOURCE_BODY_BYTES` constant.
  - Replace `prepare()` stub with full implementation.
- `tests/test_wiki_extract_concepts.py`:
  - Add 7 new tests (test_prepare_*), including 2 explicit regression migrations from 003-v3-11a (H-1, H-3).
  - REMOVE `test_main_dispatches_to_prepare_stub` from 003-v3-00 (since prepare no longer raises NotImplementedError). Net delta: +7 tests, -1 test = **+6 tests this bead**.
  - Remove the corresponding TODO markers from 003-v3-11a that say "Migrated to: 003-v3-01 ..." once the migration tests exist.

## Component Integration

- `prepare` uses existing v2 helpers verbatim: `load_known_entities`, `check_idempotency`. The internal logic of these is unchanged in this bead.
- `validate_inside_vault` from `wiki_index.security` enforces R-26 path-traversal guard (unchanged from v2).
- Emit shape (`{vault_id, source_slug, source_path, source_hash, is_unchanged, known_concepts, missing_concept_files}`) is the contract consumed by both the calling agent (between prepare and apply) AND by 003-v3-12 (integration test fixture).

## Files Touched (explicit list)

- `scripts/wiki_skills/wiki_extract_concepts.py` (prepare body + constant)
- `tests/test_wiki_extract_concepts.py` (6 new tests, 1 removed)

## Acceptance Criteria

- [ ] **R-31 (prepare)**: argparse surface validated by 003-v3-00; prepare body consumes the parsed args correctly.
- [ ] **R-32**: `known_concepts` populated from `load_known_entities`; empty vault → `[]`.
- [ ] **R-32 (M-1)**: `missing_concept_files` lists known-entity slugs whose `_concepts/<slug>.md` does NOT exist on disk; empty list if everything is consistent.
- [ ] **R-39**: `is_unchanged: true` returned when `source_state.source_hash == current_hash` AND `source_state.source_kind == 'extract-concepts'`.
- [ ] **R-42 (M-3)**: file with `st_size > _MAX_SOURCE_BODY_BYTES` → exit 2, envelope `{"error": "SOURCE_TOO_LARGE", "message": "...st_size... > 10485760..."}`. Envelope does NOT echo file content (CWE-117 regression guard).
- [ ] **R-42**: `INVALID_SOURCE_PATH` and `SOURCE_NOT_FOUND` and `INVALID_SOURCE_SLUG` envelopes preserved from v2.
- [ ] **Q4**: prepare emits `source_path` (absolute) only — NOT `source_body` (orchestrator reads via Read tool, not via prepare envelope).
- [ ] **Q5 (paired with apply)**: prepare emits `source_hash`; this exact value is what `apply --source-hash` is checked against (003-v3-03).
- [ ] **7 new tests pass**: `pytest tests/test_wiki_extract_concepts.py -k prepare -v` → 7 passed (+1 removed stub-dispatch test from 003-v3-00; net +6).
- [ ] **H-1 / H-3 regression migration verified**: `grep -n "H-1 regression\|H-3 regression" tests/test_wiki_extract_concepts.py` → at least 2 matches (the migrated tests). Grep that 003-v3-11a's TODO markers for H-1 / H-3 in the test file are deleted as part of this bead.
- [ ] **Full pytest sweep**: `pytest tests/ -q` → 396 (post-003-v3-00) + 6 (this bead net) = **≥ 402 passed, 0 failed**.
- [ ] `mypy --strict scripts/wiki_skills/wiki_extract_concepts.py` clean.

## Verification

```bash
source .venv/bin/activate

# Phase 1 tests
pytest tests/test_wiki_extract_concepts.py -k prepare -v
# expect: 7 passed (6 net new + 1 happy-path replacement for the obsolete stub-dispatch test)

# Full sweep (no regression)
pytest tests/ -q
# expect: ≥ 402 passed (per PLAN §2 suite-size table)

# Mypy
mypy --strict scripts/wiki_skills/wiki_extract_concepts.py

# Manual smoke (requires a registered vault)
# python -m scripts.wiki_skills.wiki_extract_concepts prepare \
#   --vault X --vault-root /path --source-page some-page \
#   --db-path /tmp/test.db
```

## Rollback

Revert the two edited files to post-003-v3-00 state. Test count drops back to 396. NOTE: H-1 / H-3 regressions disappear on rollback — they were deleted in 003-v3-11a. To restore them, also revert 003-v3-11a.

## Notes

- `missing_concept_files` is eager (O(N) stat) per TASK Q16. At trade-agents scale (~100 entities) cost is ~10ms; at 10k entities approaches 1000ms — see KNOWN_ISSUES P-9 (003-v3-14 adds this entry). Future bead converts to lazy via `--check-drift` flag OR materialized SQL view.
- Q17 envelope-oracle: `SOURCE_NOT_FOUND` vs `INVALID_SOURCE_PATH` distinction is preserved (operator-trust scope, not multi-tenant); documented in KNOWN_ISSUES as nit row (003-v3-14).
