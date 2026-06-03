# task-018-13 — [LOGIC] `wiki-sync scan` plan-emit

**Parent:** TASK 018. **Depends on:** 018-02, 018-04, 018-06..09, 018-11, 018-12. **RTM:** E3.1/E3.3, AC-1, AC-10, AC-13.

## Goal
Turn `scan` into the real deterministic planner: walk → classify → idempotency → strict plan JSON.

## Steps
1. Load `SyncConfig` (`.wiki/sync.yaml` or defaults; zone from CLI arg). Resolve the vault layout.
2. `iter_sync_candidates(zone, …)` → for each candidate: `classify_file(...)`; for non-`skip`,
   `source_hash = sha256(file bytes)` (the **original binary** for `convert+ingest`);
   `is_unchanged = (get_source_state(vault_id,'sync',rel,'source_hash') == source_hash)`.
3. Build the plan entry (`path` vault-relative, `action`, `reason`, `converter`, `staged_target`,
   `normalize`, `source_hash`, `is_unchanged`); **sort `entries[]` by vault-relative POSIX path**
   (determinism); compute `summary{}` action counts. `--dry-run` → a human report listing every
   skip + reason + counts (writes nothing).
4. GREEN: `test_scan_plan_matrix` (entries match the classify matrix); `test_scan_deterministic`
   (two scans byte-identical, AC-10); `test_scan_dry_run_writes_nothing` (vault+DB unchanged,
   AC-6 shared); `test_scan_reports_skips` (every skip listed, AC-13); `test_scan_is_unchanged`
   (after a `set_source_state('sync',…)`, the matching entry is `is_unchanged:true`).

## Verification
- `pytest -q -k scan` GREEN; full suite + `mypy --strict` clean.
