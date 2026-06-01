# task-015-04 — Stub `--known-concepts-format` flag

**Parent:** TASK 015. **Depends on:** 015-03. **RTM:** R-015-3 (partial).

## Goal
Add the `--known-concepts-format {full,slugs-only}` flag to the `prepare` subparser
with a stub body (ignores the flag), and write the RED test.

## Steps

1. In `scripts/wiki_skills/wiki_extract_concepts.py`, find the `prepare` subparser
   block (`pp = sub.add_parser("prepare", …)`):
   - Add after the existing `--db-path` argument:
     ```python
     pp.add_argument(
         "--known-concepts-format",
         choices=["full", "slugs-only"],
         default="full",
         dest="known_concepts_format",
         help="Format of the known_concepts field: 'full' (default) = [{slug,name,type,aliases},…];"
              " 'slugs-only' = [slug,…]. Use slugs-only to reduce payload size at scale.",
     )
     ```
   - The `apply` subparser does NOT get this flag.

2. In `prepare(args)`, the `args.known_concepts_format` attribute now exists but is
   **ignored** (stub): `known` is still emitted as the full list regardless.

3. Write RED test in `tests/test_perf_hardening.py`:
   ```python
   def test_prepare_slugs_only_format(minimal_vault: Path, tmp_path: Path) -> None:
       """prepare --known-concepts-format slugs-only emits a list of strings (RED until 015-05)."""
       # Requires at least one entity in the vault to test the slugs-only path.
       # ... set up a minimal vault with one entity in DB ...
       result = run_prepare(minimal_vault, "--known-concepts-format", "slugs-only")
       known = result["known_concepts"]
       assert isinstance(known, list)
       # Stub: known is still a list of dicts, so this FAILS (RED)
       assert all(isinstance(item, str) for item in known), "slugs-only should emit strings, not dicts"
   ```
   Confirm RED: `pytest tests/test_perf_hardening.py::test_prepare_slugs_only_format -x` fails.

4. `pytest -q` full suite: existing tests green; new test RED (expected). mypy clean.

## Acceptance
- ✅ `--known-concepts-format` flag accepted by argparse without error.
- ✅ `prepare` with `--known-concepts-format full` behaves identically to no flag.
- ✅ `test_prepare_slugs_only_format` is RED (stub emits full dicts, not strings).
- ✅ mypy strict clean.

## Files
- `scripts/wiki_skills/wiki_extract_concepts.py` (add flag to `prepare` subparser)
- `tests/test_perf_hardening.py` (add RED test + `run_prepare` helper)
