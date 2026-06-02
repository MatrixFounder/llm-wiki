# task-017-11 — [LOGIC] implement `check_drift` `trust_mtime` (P-3)

**Parent:** TASK 017. **Depends on:** 017-10 (and benefits from 017-07's `DiscoveredPage.mtime`).
**RTM:** R-017-2c/d, AC-017-3.

## Goal
When `trust_mtime=True` and the stored `last_modified` equals the file's disk mtime, skip the
read + sha256 for that file (it is assumed unchanged). Default (`False`) stays always-hash.

## Design (locked — ARCHITECTURE.md §8.4; D-017-B/C — zero DDL)
`check_drift` SELECT (sqlite_repository.py:604) gains `last_modified`:
```sql
SELECT slug, project, type, file_hash, file_path, frontmatter_json, last_modified
FROM pages WHERE vault_id = ?
```
In the discovery loop (`for f, slug, project in discover_pages(vault_root)` — or the
`DiscoveredPage` form carrying `.mtime` if discover_pages is adapted): when `trust_mtime` and
`db_last_modified` is present, compare to `datetime.fromtimestamp(f.stat().st_mtime)` (or the
walk-carried `disc.mtime` — no extra stat). On match → `continue` (skip read+hash+type, treat
as unchanged). On mismatch (or `trust_mtime=False`) → today's `read_bytes()`+sha256+type path.
`last_modified` is stored as an ISO string by reindex — compare on the parsed value /
normalized form; pick the representation that matches what reindex writes (verify in the bead).

## Steps
1. Add `last_modified` to the SELECT; build the `db_last_modified` lookup.
2. Add the `trust_mtime` short-circuit before `read_bytes()`.
3. GREEN `test_check_drift_mtime_skip` (mtime-match → no hash) +
   `test_check_drift_mtime_change_still_hashed` (touch a file → hashed, drift detected) +
   `test_check_drift_default_detects_preserved_mtime_tamper` (default mode: edit content but
   restore mtime → hash mismatch still caught — integrity invariant).

## Verification
- `pytest -q -k "check_drift or mtime"` GREEN; existing drift tests green; `mypy --strict`
  clean. Manual: `wiki-lint --mtime-skip` on a sample vault is materially faster on a no-op.
