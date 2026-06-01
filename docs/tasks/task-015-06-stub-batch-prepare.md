# task-015-06 — Stub `prepare --batch`

**Parent:** TASK 015. **Depends on:** 015-05. **RTM:** R-015-4 (partial).

## Goal
Add the `--batch <slugs.json>` flag to the `prepare` subparser (mutex with
`--source-page`), wire it to a stub `_batch_prepare` function, and write the RED test.

## Steps

1. In `scripts/wiki_skills/wiki_extract_concepts.py`, in the `prepare` subparser block:
   - Change `--source-page` from `required=True` to a mutually-exclusive group:
     ```python
     src_group = pp.add_mutually_exclusive_group(required=True)
     src_group.add_argument(
         "--source-page",
         help="Source page slug or relative path within vault (mutex with --batch)",
     )
     src_group.add_argument(
         "--batch",
         metavar="SLUGS_JSON",
         help="Path to a JSON file containing a list of source-page slugs "
              "(mutex with --source-page). One batch prepare invocation; "
              "known_concepts loaded once.",
     )
     ```
   - Keep all other existing `prepare` args unchanged.

2. Add stub `_batch_prepare(args: argparse.Namespace) → int` after `prepare()`:
   ```python
   def _batch_prepare(args: argparse.Namespace) -> int:
       """Stub for batch prepare — implemented in task-015-07."""
       return emit({"batch": []})
   ```

3. In `prepare(args)`, at the very top (before the `vault_root` resolution):
   ```python
   if args.batch:
       return _batch_prepare(args)
   ```

4. Write RED test in `tests/test_perf_hardening.py`:
   ```python
   def test_prepare_batch_multi_page(minimal_vault: Path, tmp_path: Path) -> None:
       """prepare --batch over 3 slugs emits batch with 3 entries (RED until 015-07)."""
       slugs_file = tmp_path / "slugs.json"
       slugs_file.write_text('["page-a", "page-b", "page-c"]')
       result = run_prepare_batch(minimal_vault, str(slugs_file))
       assert "batch" in result
       assert len(result["batch"]) == 3  # RED: stub returns []
   ```

5. `pytest tests/test_perf_hardening.py::test_prepare_batch_multi_page -x` → FAILS (stub
   returns `{"batch": []}`). RED confirmed.
6. Full suite green (existing tests pass). mypy clean.

## Acceptance
- ✅ `--batch` accepted by argparse; `--source-page` and `--batch` are mutex (argparse error
   if both given).
- ✅ `_batch_prepare` is callable; returns `{"batch": []}` stub.
- ✅ `test_prepare_batch_multi_page` is RED.
- ✅ Existing `prepare --source-page` tests unaffected.
- ✅ mypy strict clean.

## Files
- `scripts/wiki_skills/wiki_extract_concepts.py` (mutex group, stub `_batch_prepare`, route)
- `tests/test_perf_hardening.py` (add RED test + `run_prepare_batch` helper)
