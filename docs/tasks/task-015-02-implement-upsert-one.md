# task-015-02 — Implement `upsert_one`; `main()` delegates

**Parent:** TASK 015. **Depends on:** 015-01. **RTM:** R-015-1, AC-015-2.

## Goal
Implement `upsert_one` by extracting the upsert logic from `main()`, then refactor
`main()` to open the repo, call `upsert_one`, call `emit()`, and close.

## Design (locked)

`upsert_one` takes the logic **after argparse** in `main()`:
- `src = Path(args.source).resolve(strict=True)` → receives `src: Path` directly
- `vault_root` → receives `vault_root: Path` directly (pre-resolved by caller)
- `config: dict` → built from `vault_id` + optional `db_path` → passed as `repo`
- The function does all the adapter + normalize + upsert work, returns the envelope dict.
- Does NOT call `emit()`.
- Does NOT open or close a repo (caller is responsible).

`main()` after refactor:
```python
def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    src = Path(args.source).resolve(strict=True)
    # ... vault_root resolution (unchanged) ...
    config: dict[str, str] = {"vault_id": args.vault}
    if args.db_path:
        config["db_path"] = args.db_path
    repo = make_repo(config)
    try:
        result = upsert_one(args.vault, src, vault_root, repo)
        return emit(result)
    finally:
        repo.close()
```

## Steps

1. **Extract `upsert_one` logic** from `main()` in
   `scripts/wiki_skills/wiki_index_upsert.py`:
   - Copy the adapter + normalize + upsert block (lines ~64-118) into `upsert_one`.
   - Replace `args.vault` with `vault_id` parameter.
   - Remove the `make_repo`/`repo.close()` calls (caller owns lifecycle).
   - Replace `return emit({...})` with `return {...}` (return dict, no stdout side-effect).
   - Error returns: replace `return emit({...}, exit_code=N)` with `return {…}` — but
     the caller (`main`) must still `emit` with the right exit code.
     **Cleaner approach**: raise a lightweight `_UpsertError(envelope, exit_code)` exception
     in `upsert_one` on error paths; `main()` catches it and calls `emit(e.envelope, exit_code=e.code)`.
     Or: `upsert_one` always returns `{"action": ..., "_exit_code": 0}` or `{"error":..., "_exit_code": 6}`;
     `main()` pops `_exit_code` and calls `emit(result, exit_code)`.
     **Chosen**: add private `_exit_code` key convention; `main()` pops it.
   - `upsert_one` signature: `(vault_id: str, src: Path, vault_root: Path, repo: Any) → dict[str, Any]`.

2. **Refactor `main()`** to open repo, call `upsert_one`, `emit`, close repo (see Design above).

3. **Tests** in `tests/test_perf_hardening.py`:
   - `test_upsert_one_returns_envelope` → now GREEN (returns a dict with `action`).
   - Add `test_upsert_one_no_argparse`:
     ```python
     from unittest.mock import patch, MagicMock
     from scripts.wiki_skills.wiki_index_upsert import upsert_one, _build_parser

     def test_upsert_one_no_argparse(tmp_path: Path) -> None:
         """upsert_one must NOT invoke argparse."""
         repo = MagicMock()
         repo.upsert_page.return_value = "created"
         repo.replace_refs.return_value = None
         src = tmp_path / "test.md"
         src.write_text("---\ntitle: Test\ntype: concept\n---\nBody.\n")
         (tmp_path / "WIKI_SCHEMA.md").touch()  # vault marker
         with patch("scripts.wiki_skills.wiki_index_upsert._build_parser") as mock_p:
             result = upsert_one("test-vault", src, tmp_path, repo)
         mock_p.assert_not_called()
         assert "action" in result
     ```
   - Add integration: `main(["--vault","v","--source",str(src),"--vault-root",str(tmp)])` still works.

4. `pytest -q` all green. `mypy --strict scripts/` clean.

## Acceptance
- ✅ `test_upsert_one_returns_envelope` GREEN.
- ✅ `test_upsert_one_no_argparse` — `_build_parser` NOT called when using `upsert_one`.
- ✅ Existing `test_wiki_index_upsert.py` tests all pass (main() still works).
- ✅ mypy strict clean.

## Files
- `scripts/wiki_skills/wiki_index_upsert.py` (implement `upsert_one`; refactor `main()`)
- `tests/test_perf_hardening.py` (tests GREEN + new test)
