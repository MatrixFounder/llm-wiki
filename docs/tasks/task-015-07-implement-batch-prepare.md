# task-015-07 — Implement batch prepare

**Parent:** TASK 015. **Depends on:** 015-06. **RTM:** R-015-4, AC-015-5, AC-015-6.

## Goal
Implement `_batch_prepare(args)`: read the slugs JSON file, load `known_concepts` once,
run single-slug recon for each slug with per-entry error isolation, emit the batch envelope.

## Design (locked — ARCHITECTURE.md functional-architecture §Concept Extractor batch prepare)

```
_batch_prepare(args):
  1. Read + bounded-parse the slugs file (anywhere on fs; not vault-contained)
  2. Validate: must be a non-empty list of strings
  3. Open one repo
  4. Load known_concepts once (respecting args.known_concepts_format)
  5. For each slug in slugs:
       call _recon_single(slug, args.vault_root, args.vault, repo) -> entry dict | error dict
  6. Close repo
  7. emit({"batch": entries})
```

Factor out `_recon_single(source_page_arg, vault_root, vault_id, repo) → dict`:
- Contains the per-slug logic from `prepare()`: `_resolve_source_inside_sources`,
  `_read_file_bounded`, `sha256`, `check_idempotency`, missing-concept-files drift sweep.
- Returns a result dict on success or `{"source_slug": s, "error": "…", "message": "…"}` on
  failure (SOURCE_NOT_FOUND, SOURCE_TOO_LARGE, etc.).
- Known_concepts is NOT loaded inside `_recon_single` — it's passed in as a parameter.

Updated signature: `_recon_single(source_page_arg, vault_root, vault_id, repo, known_out)`.

Security model for slugs file:
- File may be anywhere (not `validate_inside_vault`).
- Read via `_read_file_bounded(path, _MAX_SOURCE_BODY_BYTES)` to prevent OOM.
- JSON parsed; must be `list[str]` (non-empty); invalid type → `INVALID_BATCH_FILE` exit 2.
- Each slug validated by `_resolve_source_inside_sources` (vault-containment enforced on
  resolved source paths, not the slugs file).

## Steps

1. **Factor `_recon_single` out of `prepare()`** in
   `scripts/wiki_skills/wiki_extract_concepts.py`:
   - Extract: `_path_is_absolute` check, `_resolve_source_inside_sources`, `_read_file_bounded`,
     `sha256`, `check_idempotency`, `missing_concept_files` sweep.
   - Add `known_out` parameter (pre-loaded known concepts list).
   - Return dict: success `{"source_slug":…,"source_path":…,"source_hash":…,"is_unchanged":…,
     "known_concepts":known_out,"missing_concept_files":[…]}` or error
     `{"source_slug":…,"error":…,"message":…}`.
   - `prepare(args)` calls `_recon_single` and `emit`s the single-entry result.

2. **Implement `_batch_prepare(args)`**:
   ```python
   def _batch_prepare(args: argparse.Namespace) -> int:
       batch_path = Path(args.batch)
       try:
           raw = _read_file_bounded(batch_path, _MAX_SOURCE_BODY_BYTES)
       except (OSError, _FileTooLargeError) as e:
           return emit({"error": "INVALID_BATCH_FILE", "reason": str(e)}, exit_code=2)
       try:
           slugs = json.loads(raw.decode("utf-8"))
       except json.JSONDecodeError:
           return emit({"error": "INVALID_BATCH_FILE", "reason": "not valid JSON"}, exit_code=2)
       if not isinstance(slugs, list) or not slugs or not all(isinstance(s, str) for s in slugs):
           return emit({"error": "INVALID_BATCH_FILE",
                        "reason": "must be a non-empty JSON array of strings"}, exit_code=2)
       vault_root = args.vault_root.resolve(strict=True)
       repo = make_repo({"vault_id": args.vault, **({"db_path": args.db_path} if args.db_path else {})})
       try:
           known = load_known_entities(repo, args.vault)
           slugs_only = getattr(args, "known_concepts_format", "full") == "slugs-only"
           known_out: list[Any] = [e["slug"] for e in known] if slugs_only else known
           entries = []
           for slug in slugs:
               entry = _recon_single(slug, vault_root, args.vault, repo, known_out)
               entries.append(entry)
       finally:
           repo.close()
       return emit({"batch": entries})
   ```

3. **Tests** in `tests/test_perf_hardening.py`:
   - `test_prepare_batch_multi_page` → GREEN: 3 valid slugs → 3 success entries.
   - `test_prepare_batch_partial_failure` (AC-015-6): 2 valid + 1 invalid slug → 3 entries
     (2 success + 1 with `error` key), exit 0.
   - `test_prepare_batch_known_concepts_once`: monkeypatch `load_known_entities`; run
     3-slug batch; assert call count == 1.
   - `test_prepare_batch_malformed_file`: JSON array of ints → `INVALID_BATCH_FILE`.

4. `pytest -q` all green. `mypy --strict scripts/` clean.

## Acceptance
- ✅ `test_prepare_batch_multi_page` GREEN (AC-015-5): batch has 3 entries, each with
  `source_slug` + `source_hash`.
- ✅ `test_prepare_batch_partial_failure` GREEN (AC-015-6): 2 success + 1 error, exit 0.
- ✅ `known_concepts` loaded once per batch (not per slug).
- ✅ `--known-concepts-format slugs-only` applies to batch envelope entries.
- ✅ Existing single-page `prepare` tests still pass.
- ✅ mypy strict clean.

## Files
- `scripts/wiki_skills/wiki_extract_concepts.py` (factor `_recon_single`, implement `_batch_prepare`)
- `tests/test_perf_hardening.py` (tests GREEN + new batch tests)
