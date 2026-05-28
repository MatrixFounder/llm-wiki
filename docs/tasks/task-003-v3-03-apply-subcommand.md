# Task 003-v3-03: `apply` subcommand implementation

## Meta

- **Bead ID**: `task-003-v3-03-apply-subcommand`
- **Slug**: `apply-subcommand`
- **Maps to**: Issue **I-V3.1d**; RTM rows **R-31**, **R-33′**, **R-35**, **R-37**, **R-38**, **R-39**, **R-41**, **R-42**; Q5, Q6, Q11, Q12; H-1, H-5, H-6; C-1.
- **Depends on**: task-003-v3-01 (prepare emits source_hash), task-003-v3-02 (strict validator), task-003-v3-04 (write_concept_page reshape — apply calls into it).
- **Estimated time**: 1.0 day
- **Priority**: Critical (the synthesis-write half of the v3.1 surface).

## Use Case Connection

- **UC-08 v3.1 Step 6+7+8+9**: orchestrator pipes candidates JSON to `apply`; apply validates, writes pages, upserts entities + refs, builds manifest, dispatches if `--ingest`.
- **UC-08 v3.1 A6** (operator edits source between prepare and apply): hash mismatch → exit 2.
- **UC-08 v3.1 A10/A11**: candidates-file validation (inside vault + size cap).

## Task Goal

Implement `apply(args) -> int` in `scripts/wiki_skills/wiki_extract_concepts.py`:

1. **Load candidates** (with `_MAX_CANDIDATES_BYTES = 1_048_576` cap):
   - If `--candidates-stdin`: `data = sys.stdin.buffer.read(_MAX_CANDIDATES_BYTES + 1)`; if `len(data) > _MAX_CANDIDATES_BYTES` → exit 4 `CANDIDATES_TOO_LARGE` (Risk R-6 mitigation).
   - If `--candidates-file PATH`:
     - **Validate inside vault (H-5)**: `validate_inside_vault(Path(args.candidates_file).resolve(strict=True), vault_root)` → on PathTraversalError, exit 2 `INVALID_CANDIDATES_PATH`. Envelope emits the path string, NEVER the file content.
     - Stat-check `st_size > _MAX_CANDIDATES_BYTES` BEFORE read → exit 4 `CANDIDATES_TOO_LARGE`.
     - Read bytes.
   - Parse JSON; on `JSONDecodeError`, exit 4 `EXTRACTION_PARSE_ERROR`. Envelope emits `at line N column M` from the exception (NOT the file content).
2. **Re-read source** from disk + recompute sha256.
3. **Hash check (H-1, Q5)**: if `current_hash != args.source_hash`, exit 2 `SOURCE_CHANGED_DURING_EXTRACTION`. Envelope emits `expected=<truncated-prefix>, got=<truncated-prefix>` (first 16 hex chars of each); NO source content leaked.
4. **Validate schema**: `_validate_candidates_schema(candidates, source_body=current_body)` — surfaces `ExtractionParseError` with structured (error, field, reason); on raise, exit 4 with the envelope code from `e.error`.
5. **Classify**: `create_list, mention_list = classify_candidates(candidates, known_slugs)` (preserves v2 logic; v2 helper unchanged).
6. **Write concept pages**: for each `cand in create_list`, call `write_concept_page(vault_root, cand, source_slug, today, vault_id=args.vault)` (reshape lands in 003-v3-04 — this bead just calls it). Annotate `cand["file_write_action"]` with the returned action label.
7. **Upsert entities**: for each `cand in create_list`, call `upsert_extracted_entity(repo, args.vault, cand, source_slug, today, orchestrator_id=args.orchestrator_id)` (the `orchestrator_id` plumbing lands in 003-v3-05; this bead passes through whatever attribute exists on `args`).
8. **Upsert refs**: `upsert_entity_refs(repo, args.vault, source_slug, "_vault_", create_list + mention_list)` (unchanged from v2).
9. **Build manifest**: `manifest = build_manifest(args.vault, source_slug, current_hash, create_list, mention_list, log_event, vault_root)` (unchanged from v2).
10. **Dispatch (optional)**: if `args.ingest`, call `dispatch_to_indexer(manifest, args.vault, vault_root, args.db_path)`; check `summary["failed"]`; exit 5 on partial failure.
11. **Update idempotency state**: AFTER dispatch (if any). Gated on `summary["failed"]` being empty when `--ingest` is set (C-1 invariant from v2 carried forward).
12. Emit final envelope (manifest or `{extraction, index}` combined) + exit 0.

## Stub-First Plan

### Phase 1 — Logic + 6 new unit tests (Red→Green)

1. In `scripts/wiki_skills/wiki_extract_concepts.py`:
   - Add module-level constant:
     ```python
     # H-5/H-6 (TASK 003 v3.1): DoS protection on candidates input
     # (file or stdin). Capped before any parse.
     _MAX_CANDIDATES_BYTES = 1_048_576  # 1 MiB
     ```
   - Replace `apply()` stub body with the full implementation (logic listed above).
   - Add a helper `_load_candidates(args, vault_root) -> list[Any]` that encapsulates the load + cap + path-validate + parse logic (keeps `apply()` body shallow and testable).
2. Add 9 new tests to `tests/test_wiki_extract_concepts.py` (3 of which are explicit regression migrations from 003-v3-11a — C-1 / ingest e2e / no-ingest manifest):
   - `test_apply_canned_json_happy` — seed vault with `_sources/sample-doc.md`; pre-run prepare to get hash; pipe canned 1-candidate JSON through stdin OR pass `--candidates-file`; assert exit 0; assert envelope is a manifest with `status="ok"`; assert `_concepts/sample-concept.md` exists.
   - `test_apply_stdin_vs_file_mutex` — pass BOTH `--candidates-stdin` and `--candidates-file`; assert argparse error (SystemExit 2).
   - `test_apply_source_hash_mismatch_exits_2_SOURCE_CHANGED_H1` — seed source; compute prepare hash; mutate source body on disk; pass the OLD hash; assert exit 2, envelope `error="SOURCE_CHANGED_DURING_EXTRACTION"`. Assert envelope does NOT contain new source body content.
   - `test_apply_candidates_file_outside_vault_exits_2_INVALID_CANDIDATES_PATH_H5` — pass `--candidates-file /etc/passwd`; assert exit 2, envelope `error="INVALID_CANDIDATES_PATH"`; envelope contains the path string but NOT the file content.
   - `test_apply_candidates_file_too_large_exits_4_H6` — create a 1_048_577-byte JSON-looking file inside vault; pass `--candidates-file`; assert exit 4, envelope `error="CANDIDATES_TOO_LARGE"`.
   - `test_apply_with_ingest_end_to_end_mocked_dispatch` — patch `scripts.wiki_skills.wiki_extract_concepts.dispatch_to_indexer` to return `{"failed": [], "indexed": 1}`; run apply with `--ingest`; assert envelope shape `{extraction, index}`; assert `dispatch_to_indexer` called once. **Regression migration from 003-v3-11a** (was `test_main_with_ingest_calls_dispatch_and_emits_combined` at line 1071).
   - `test_apply_without_ingest_emits_manifest_only` — same setup as the previous test but WITHOUT `--ingest`; assert exit 0; assert envelope is a bare manifest (NOT `{extraction, index}`); assert `dispatch_to_indexer` was NOT called (`mock.assert_not_called()`). **Regression migration from 003-v3-11a** (was `test_main_without_ingest_emits_manifest_only` at line 1140).
   - `test_apply_with_ingest_partial_failure_exits_5_C1` — patch `dispatch_to_indexer` to return `{"failed": ["sample-concept"], "indexed": 0}`; run apply; assert exit 5; assert `source_state` NOT updated (mock `update_idempotency_state` to record call count — assert 0 calls). **Regression migration from 003-v3-11a** (was `test_main_ingest_partial_failure_does_not_update_source_state` at line 522).
   - `test_apply_validator_unknown_field_exits_4_with_structured_envelope` — pipe candidates with extra key `evil="leak"`; assert exit 4, envelope `error="UNKNOWN_FIELD"`, `field="evil"`, NO `evil` value in envelope.
3. Delete the corresponding TODO markers in `tests/test_wiki_extract_concepts.py` left by 003-v3-11a (the 3 entries that referenced "Migrated to: 003-v3-03 ...").
4. Run `pytest tests/test_wiki_extract_concepts.py -k apply -v` → 9 new tests pass. Net delta this bead: +9 tests minus -1 (the stub-dispatch test `test_main_dispatches_to_apply_stub` from 003-v3-00 is now obsolete and removed) = **+8 tests**.

### Phase 2 — n/a (logic IS the deliverable)

## Changes Description

### Edited files

- `scripts/wiki_skills/wiki_extract_concepts.py`:
  - Add `_MAX_CANDIDATES_BYTES`.
  - Add `_load_candidates()` helper.
  - Replace `apply()` stub with full impl.
- `tests/test_wiki_extract_concepts.py`: add 9 new tests (3 are explicit regression migrations from 003-v3-11a — C-1, ingest e2e, no-ingest manifest). Remove the stub-dispatch test `test_main_dispatches_to_apply_stub` from 003-v3-00 (obsolete once apply has real body). Net: +9 −1 = **+8 tests this bead**.

## Component Integration

- `apply` is the call site for ALL preserved v2 helpers: `classify_candidates`, `write_concept_page`, `upsert_extracted_entity`, `upsert_entity_refs`, `build_manifest`, `dispatch_to_indexer`, `update_idempotency_state`. The v2 invariants (SQL downgrade-guard, atomic page write, manifest v1.1 contract) are preserved transitively because the helpers are unchanged.
- **Patch-target lock (R-1)**: tests in this bead that mock `dispatch_to_indexer` MUST patch `scripts.wiki_skills.wiki_extract_concepts.dispatch_to_indexer`, NOT `scripts.wiki_skills._manifest_consumer.index_from_manifest`. (Carried forward from v2 PLAN R-2.)

## Files Touched

- `scripts/wiki_skills/wiki_extract_concepts.py`
- `tests/test_wiki_extract_concepts.py`

## Acceptance Criteria

- [ ] **R-31 (apply argparse)**: full surface validated by 003-v3-00; apply body consumes correctly.
- [ ] **R-33′**: `apply` calls `_validate_candidates_schema` with `source_body` for the optional quote check.
- [ ] **R-35**: manifest emission preserved.
- [ ] **R-37**: entity upsert with `is_candidate=1` + SQL downgrade-guard preserved.
- [ ] **R-38**: refs upsert with `trust_level='medium'` preserved.
- [ ] **R-39 (H-1)**: `--source-hash` mismatch → exit 2 `SOURCE_CHANGED_DURING_EXTRACTION`. Envelope NOT echoing source content.
- [ ] **R-41**: in-process dispatch via `dispatch_to_indexer` preserved.
- [ ] **R-42 (H-5)**: `--candidates-file` outside vault → exit 2 `INVALID_CANDIDATES_PATH`.
- [ ] **R-42 (H-6)**: candidates payload > 1 MiB → exit 4 `CANDIDATES_TOO_LARGE`.
- [ ] **R-42 (C-1)**: on `--ingest` partial failure, `update_idempotency_state` NOT called; exit 5.
- [ ] **CWE-117 audit**: all envelopes emitted by apply have NO `content`, `value`, `raw`, `received` keys. (003-v3-17 parametrized test enforces.)
- [ ] **9 new tests pass** (3 explicit regression migrations from 003-v3-11a flagged in code comments).
- [ ] **Regression-migration markers cleaned**: `grep -n "Migrated to: 003-v3-03" tests/test_wiki_extract_concepts.py` → 0 matches (TODO markers from 11a have been replaced by real tests).
- [ ] **Full pytest sweep**: `pytest tests/ -q` → (post-002 baseline) + 8 = **≥ 8 more than the pre-bead state, 0 failed**. Concrete: pre-bead state at end of 002 = 410; post-003 = ≥ 418 passed.
- [ ] `mypy --strict scripts/wiki_skills/wiki_extract_concepts.py` clean.

## Verification

```bash
source .venv/bin/activate

pytest tests/test_wiki_extract_concepts.py -k apply -v
# expect: 8 passed

pytest tests/ -q
# expect: ≥ 418 passed

mypy --strict scripts/wiki_skills/wiki_extract_concepts.py

# Patch-target lock invariant
grep -rn "patch.*_manifest_consumer\\.\\(index_from_manifest\\|validate_manifest\\|WikiIngestError\\)" tests/
# expect: empty output
```

## Rollback

Revert the file edits. Test count returns to the post-002 baseline (~410). NOTE: C-1 / ingest e2e / no-ingest regression coverage disappears on rollback — those tests were deleted in 003-v3-11a. To restore, also revert 003-v3-11a.

## Notes

- Argparse mutex group: use `parser.add_mutually_exclusive_group(required=True).add_argument(...)` for `--candidates-stdin` + `--candidates-file`.
- The `_load_candidates` helper is small (~30 LoC) but keeps `apply()` readable. Worth the abstraction.
- For test isolation, use `tempfile.mkdtemp()` for vault root + `:memory:` SQLite per test.
- The `--orchestrator-id` arg is added to `apply` argparse in 003-v3-05; this bead's apply body simply reads `getattr(args, "orchestrator_id", "orchestrator")` defensively.
