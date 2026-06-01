# task-015-09 — Implement batch apply

**Parent:** TASK 015. **Depends on:** 015-08. **RTM:** R-015-5, AC-015-7, AC-015-8.

## Goal
Implement `_batch_apply`: open one repo, process each combined.json entry with an
independent transaction per entry, dispatch `index_from_manifest` once per entry with the
shared repo, emit the batch result envelope.

## Design (locked — ARCHITECTURE.md functional-architecture §Concept Extractor batch apply)

**Factor `_apply_candidates_to_db` from `apply()`:**
```python
def _apply_candidates_to_db(
    source_path: Path,
    source_hash_expected: str,
    vault_id: str,
    vault_root: Path,
    candidates: list[dict[str, Any]],
    orchestrator_id: str,
    today: date,
    db_path: str | None,
    repo: Any,
) -> dict[str, Any]:
    """Core DB-write phase for one source page's candidates.

    Accepts an already-open repo; wraps all DB writes in an independent
    BEGIN IMMEDIATE transaction. Returns the wiki-ingest v1.1-compatible
    manifest dict on success, or raises on unrecoverable failure.

    apply() calls this after loading candidates from file/stdin.
    _batch_apply() calls this per entry with the shared repo.
    """
```

Contents (extracted from `apply()`):
- `source_path` already resolved + read; re-read here to recompute hash (TOCTOU check
  vs `source_hash_expected`).
- `_validate_candidates_schema` + `_preflight_sanitize`.
- `classify_candidates` + `write_concept_page` loop (file writes happen BEFORE tx open).
- `BEGIN IMMEDIATE` transaction; `upsert_extracted_entity` + `upsert_entity_refs` +
  `build_manifest`; commit. On failure: rollback (files remain — Class A canonical).
- Returns manifest dict (NOT the full apply envelope; caller wraps it).
- Does NOT call `emit()`, does NOT call `dispatch_to_indexer`.

**`apply()` after refactor:**
- Loads candidates, resolves `source_path`, calls `_apply_candidates_to_db(…, repo)`.
- Calls `emit(manifest)`.
- If `--ingest`: calls `dispatch_to_indexer(manifest, …, repo=repo)` (passes repo).
- Calls `_try_update_idempotency_state`.

**`_batch_apply(args)`:**
```python
def _batch_apply(args: argparse.Namespace) -> int:
    combined_path = args.batch_candidates
    # 1. Read + bounded parse combined_path (validate_inside_vault NOT required — operator file)
    # 2. Validate: must be list[{source_slug, source_hash, candidates}]
    vault_root = args.vault_root.resolve(strict=True)
    repo = make_repo({"vault_id": args.vault, …})
    try:
        batch_results = []
        today = date.today()
        for entry in entries:
            source_slug = entry["source_slug"]
            source_hash = entry["source_hash"]
            candidates = entry["candidates"]
            try:
                # Resolve source path
                resolved = _resolve_source_inside_sources(source_slug, vault_root)
                if isinstance(resolved, dict):  # error envelope
                    batch_results.append({**resolved, "source_slug": source_slug})
                    continue
                source_path, _ = resolved
                # _apply_candidates_to_db wraps its DB writes in BEGIN IMMEDIATE
                manifest = _apply_candidates_to_db(
                    source_path, source_hash, args.vault, vault_root,
                    candidates, args.orchestrator_id, today, args.db_path, repo
                )
                if args.ingest:
                    dispatch_to_indexer(manifest, args.vault, vault_root, args.db_path, repo=repo)
                _try_update_idempotency_state(repo, args.vault, _, sha256_of(source_path))
                batch_results.append({"source_slug": source_slug, "action": "applied",
                                       "manifest": manifest})
            except (OSError, ValueError, KeyError, RuntimeError) as e:
                batch_results.append({"source_slug": source_slug,
                                       "error": type(e).__name__, "message": str(e)})
    finally:
        repo.close()
    return emit({"batch": batch_results})
```

## Steps

1. **Factor `_apply_candidates_to_db`** out of `apply()`:
   - Identify the DB-write block in `apply()` (after candidates loading and sanitize
     preflight through `build_manifest`).
   - Extract into `_apply_candidates_to_db` with the signature above.
   - Add the `BEGIN IMMEDIATE` transaction wrapper inside `_apply_candidates_to_db`.
   - Refactor `apply()` to call it: behavior unchanged (all existing tests still pass).
   - Note: `apply()` still calls `emit()`, `dispatch_to_indexer`, and
     `_try_update_idempotency_state` (not moved into `_apply_candidates_to_db`).

2. **Update `dispatch_to_indexer`** signature to accept optional `repo`:
   `dispatch_to_indexer(manifest, vault_id, vault_root, db_path, repo=None) → dict`
   → calls `index_from_manifest(manifest, vault_id, vault_root, db_path, repo=repo)`.

3. **Implement `_batch_apply(args)`** as designed above.

4. **Tests** in `tests/test_perf_hardening.py`:

   `test_apply_batch_candidates` (AC-015-7) — GREEN:
   ```python
   def test_apply_batch_candidates(…) -> None:
       # Verify make_repo called once for 2-entry batch
       mock_repo = MagicMock()
       mock_repo.upsert_page.return_value = "created"
       …
       with patch("scripts.wiki_skills.wiki_extract_concepts.make_repo",
                  return_value=mock_repo) as mr:
           result = run_apply_batch(…)
       assert mr.call_count == 1
       assert len(result["batch"]) == 2
   ```

   `test_apply_batch_with_ingest` (AC-015-8) — GREEN:
   ```python
   def test_apply_batch_with_ingest(…) -> None:
       # Verify make_repo once; index_from_manifest called N=2 times with shared repo
       with patch("scripts.wiki_skills.wiki_extract_concepts.make_repo",
                  return_value=mock_repo) as mr, \
            patch("scripts.wiki_skills.wiki_extract_concepts.index_from_manifest") as ifm:
           run_apply_batch(…, ingest=True)
       assert mr.call_count == 1
       assert ifm.call_count == 2  # once per source entry
       # Each call passes the shared repo
       for c in ifm.call_args_list:
           assert c.kwargs.get("repo") is mock_repo
   ```

5. `pytest -q` all green. `mypy --strict scripts/` clean.

## Acceptance
- ✅ `test_apply_batch_candidates` GREEN (AC-015-7): `make_repo` called once; 2 batch entries.
- ✅ `test_apply_batch_with_ingest` GREEN (AC-015-8): `make_repo` once; `index_from_manifest`
  called twice (once per source entry), each with the shared repo.
- ✅ `apply()` (single-page) all existing tests pass — `_apply_candidates_to_db` refactor is
  behavior-neutral.
- ✅ `dispatch_to_indexer` backward-compat (existing callers with no `repo` kwarg still work).
- ✅ mypy strict clean.

## Files
- `scripts/wiki_skills/wiki_extract_concepts.py` (factor `_apply_candidates_to_db`, update
  `dispatch_to_indexer`, implement `_batch_apply`)
- `scripts/wiki_skills/_manifest_consumer.py` (if `dispatch_to_indexer` forwards `repo`)
- `tests/test_perf_hardening.py` (tests GREEN + new batch-apply tests)
