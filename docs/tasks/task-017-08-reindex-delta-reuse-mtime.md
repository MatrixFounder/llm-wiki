# task-017-08 — [LOGIC] `reindex_delta` reuses `DiscoveredPage.mtime` (P-2)

**Parent:** TASK 017. **Depends on:** 017-07. **RTM:** R-017-3, AC-017-4.

## Goal
Drop the redundant second `path.stat()` in the delta no-op path — one stat per file.

## Design (locked — ARCHITECTURE.md §3.5)
`scripts/wiki_index/reindex.py` `reindex_delta`, current lines 296-303:
```python
for disc in paths_on_disk:
    path = disc.path
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime)   # <- second stat (remove)
    except OSError as e:
        skipped.append({"path": str(path), "error": f"stat: {e}"})
        continue
    if mtime <= cutoff:
        continue
```
Replace with:
```python
    if disc.mtime is not None:
        mtime = datetime.fromtimestamp(disc.mtime)
    else:                                   # defensive fallback for non-iter_pages callers
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime)
        except OSError as e:
            skipped.append({"path": str(path), "error": f"stat: {e}"}); continue
    if mtime <= cutoff:
        continue
```
`paths_on_disk = iter_pages(...)` (line 292) already carries mtime after 017-07.

## Steps
1. Swap to `disc.mtime` with the stat fallback.
2. GREEN `test_reindex_delta_single_stat_per_file`: monkeypatch/spy `Path.stat` (or
   `os.stat`) during a no-op delta on a small vault → assert ≤ 1 stat per discovered file
   (the walk's), zero extra in the loop.

## Verification
- `pytest -q -k "reindex_delta"` GREEN; existing reindex tests green; `mypy --strict` clean.
