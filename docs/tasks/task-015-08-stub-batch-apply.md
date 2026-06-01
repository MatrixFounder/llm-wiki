# task-015-08 — Stub `apply --batch-candidates`

**Parent:** TASK 015. **Depends on:** 015-07. **RTM:** R-015-5 (partial).

## Goal
Add the `--batch-candidates <combined.json>` flag to the `apply` subparser (mutex with
`--candidates-file`/`--candidates-stdin`), wire it to a stub, and write the RED test.

## Steps

1. In `scripts/wiki_skills/wiki_extract_concepts.py`, in the `apply` subparser block:
   - The existing `--candidates-file` / `--candidates-stdin` are in a mutually-exclusive
     group `cand_group`. Add `--batch-candidates` to that same group:
     ```python
     cand_group.add_argument(
         "--batch-candidates",
         metavar="COMBINED_JSON",
         type=Path,
         default=None,
         help="Path to a combined batch-candidates JSON file "
              "(mutex with --candidates-file/--candidates-stdin). "
              "Schema: [{source_slug, source_hash, candidates:[…]}, …].",
     )
     ```
   - The group already has `required=True` — adding a third option keeps the mutex intact.

2. Add stub `_batch_apply(args: argparse.Namespace) → int` after `apply()`:
   ```python
   def _batch_apply(args: argparse.Namespace) -> int:
       """Stub for batch apply — implemented in task-015-09."""
       return emit({"batch": []})
   ```

3. In `apply(args)`, at the very top (before any validation):
   ```python
   if args.batch_candidates is not None:
       return _batch_apply(args)
   ```

4. Write RED test in `tests/test_perf_hardening.py`:
   ```python
   def test_apply_batch_candidates(minimal_vault: Path, tmp_path: Path) -> None:
       """apply --batch-candidates over 2 pages emits batch with 2 entries (RED until 015-09)."""
       # combined.json with 2 entries (stubbed candidates — real content in 015-09)
       combined = [
           {"source_slug": "page-a", "source_hash": "a" * 64, "candidates": []},
           {"source_slug": "page-b", "source_hash": "b" * 64, "candidates": []},
       ]
       combined_file = tmp_path / "combined.json"
       combined_file.write_text(json.dumps(combined))
       result = run_apply_batch(minimal_vault, str(combined_file))
       assert "batch" in result
       assert len(result["batch"]) == 2  # RED: stub returns []
   ```

5. RED confirmed. Full suite green (existing tests pass). mypy clean.

## Acceptance
- ✅ `--batch-candidates` accepted by argparse; mutex with `--candidates-file`/`--candidates-stdin`.
- ✅ `_batch_apply` stub callable; returns `{"batch": []}`.
- ✅ `test_apply_batch_candidates` is RED.
- ✅ Existing single-page `apply` tests unaffected.
- ✅ mypy strict clean.

## Files
- `scripts/wiki_skills/wiki_extract_concepts.py` (add `--batch-candidates` to mutex group, stub, route)
- `tests/test_perf_hardening.py` (add RED test + `run_apply_batch` helper)
