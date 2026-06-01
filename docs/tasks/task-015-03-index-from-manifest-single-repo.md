# task-015-03 — `index_from_manifest` single-repo + `upsert_one`

**Parent:** TASK 015. **Depends on:** 015-02. **RTM:** R-015-2, AC-015-1.

## Goal
Refactor `_manifest_consumer.index_from_manifest` to:
1. Accept an optional `repo` parameter (caller-owned lifecycle when provided).
2. Replace the `main(argv)` per-entry call with `upsert_one(…, repo_to_use)`.
3. Use the same `repo_to_use` for `append_log_event`.
Result: at most one `make_repo` call per `index_from_manifest` invocation (when `repo=None`).

## Design (locked — ARCHITECTURE.md functional-architecture §wiki-enrich)

New signature:
```python
def index_from_manifest(
    manifest: dict[str, Any],
    vault_id: str,
    vault_root: Path,
    db_path: str | None = None,
    repo: Any = None,          # NEW — optional caller-owned connection
) -> dict[str, Any]:
```

Internal logic:
```python
_owns_repo = repo is None
if _owns_repo:
    repo_to_use = make_repo({"vault_id": vault_id, **({"db_path": db_path} if db_path else {})})
else:
    repo_to_use = repo
try:
    # ... upsert loop: call upsert_one(vault_id, abs_path, vault_root, repo_to_use) ...
    # ... append_log_event on repo_to_use ...
finally:
    if _owns_repo:
        repo_to_use.close()
```

The `upsert_one` call replaces the entire `argv` build + `io.StringIO` capture + `redirect_stdout`
+ `main(argv)` + `json.loads` block (lines 115-159 of the current file). `upsert_one` returns a
dict directly; no stdout capture needed.

**Envelope handling:** `upsert_one` returns `{"action": ..., "_exit_code": 0}` on success or
`{"error": ..., "_exit_code": N}` on failure (per 015-02 design). The manifest-consumer loop
checks `result.get("_exit_code", 0) != 0 or "error" in result` to classify into `failed[]`
vs `upserted[]`. The `_exit_code` key is stripped before appending to `failed[].envelope`.

**Error handling contract (preserve from current code):**
- `OSError`, `ValueError`, `KeyError`, `RuntimeError` from `upsert_one` → still caught,
  appended to `failed[]`. Programming errors must still propagate.
- `BAD_UPSERT_OUTPUT` path (json decode error) is no longer reachable (we get a dict, not JSON
  text) — remove or make it unreachable via a defensive `else` branch.

## Steps

1. **Add `repo` parameter** to `index_from_manifest` in
   `scripts/wiki_skills/_manifest_consumer.py`.

2. **Ownership logic**: `_owns_repo = repo is None`; open `make_repo` only when True;
   `finally` block closes only when `_owns_repo`.

3. **Replace the per-entry block** (lines ~115-159): remove `argv` build, `io.StringIO`,
   `redirect_stdout`, `main(argv)`, `json.loads`. Replace with:
   ```python
   try:
       result = upsert_one(vault_id, abs_path, vault_root, repo_to_use)
   except (OSError, ValueError, KeyError, RuntimeError) as e:
       failed.append({"path": rel, "envelope": {"error": type(e).__name__, "message": str(e)}})
       continue
   exit_code = result.pop("_exit_code", 0)
   if exit_code != 0 or "error" in result:
       failed.append({"path": rel, "envelope": result})
   else:
       upserted.append({"path": rel, "action": result.get("action", "?")})
   ```

4. **Move the `append_log_event` block** (lines ~161-188) to use `repo_to_use`; remove the
   local `make_repo` / `repo.close()` inside it (they're now handled by the outer ownership
   block).

5. **Remove the lazy import** `from scripts.wiki_skills.wiki_index_upsert import main as upsert_main`
   (line 93); replace with `from scripts.wiki_skills.wiki_index_upsert import upsert_one`.

6. **Update the module docstring** to reflect the new `upsert_one`-based approach.

7. **Test** `test_index_from_manifest_single_connection` in `tests/test_perf_hardening.py`:
   ```python
   from unittest.mock import patch, MagicMock, call
   from scripts.wiki_skills._manifest_consumer import index_from_manifest

   def test_index_from_manifest_single_connection(minimal_vault: Path) -> None:
       """make_repo called exactly once when repo=None (AC-015-1)."""
       manifest = _build_manifest("minimal-test", minimal_vault, ["_sources/alpha.md"])
       mock_repo = MagicMock()
       mock_repo.upsert_page.return_value = "created"
       mock_repo.replace_refs.return_value = None
       mock_repo.append_log_event.return_value = 1
       with patch("scripts.wiki_skills._manifest_consumer.make_repo", return_value=mock_repo) as mr:
           index_from_manifest(manifest, "minimal-test", minimal_vault)
       assert mr.call_count == 1
   ```

8. Run `pytest -q` full suite green. `mypy --strict scripts/` clean.

## Acceptance
- ✅ `test_index_from_manifest_single_connection` GREEN (AC-015-1): `make_repo` called once.
- ✅ `test_upsert_one_no_argparse` still GREEN (AC-015-2): no argparse in upsert path.
- ✅ `tests/test_manifest_consumer.py` all pass (backward-compat: callers omit `repo`).
- ✅ `tests/test_wiki_enrich.py` all pass (uses `index_from_manifest` without `repo`).
- ✅ mypy strict clean.

## Files
- `scripts/wiki_skills/_manifest_consumer.py` (add `repo` param, use `upsert_one`, remove `main(argv)`)
- `tests/test_perf_hardening.py` (add `test_index_from_manifest_single_connection`)
