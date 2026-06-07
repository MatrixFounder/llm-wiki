# Task 019.04: [LOGIC] per-folder cascade resolver (Option A)

## Use Case Connection
- UC-4 · E3.2, E3.3, E3.4 · AC-5, AC-10

## Task Goal
Implement `resolve_policy`: per scanned file, merge the vault-global `resummarize` with
any per-folder `<dir>/.wiki/sync.yaml` overrides, **deepest-wins**, deterministically.

## Changes Description
#### File: `scripts/wiki_skills/_resummarize.py`
- `resolve_policy(path, *, vault_root, vault_config)`:
  1. ancestor chain = `[vault_root, …, path.parent]` (vault_root first = base).
  2. for each dir, obtain its `resummarize` dict via a **per-dir-memoized** call to
     `load_sync_config(dir)` (reuses size-cap + anchor-ban + symlink-refuse + schema —
     hardening for free; `.wiki/` is pruned from the content walk so it is read only here).
  3. `config_loader.deep_merge` the dicts in order (deeper overrides shallower; dicts
     merge, scalars replace → partial override allowed).
  4. build + return the merged `ResummarizeConfig | None`.
- Memo cache keyed by resolved dir path (per-run dict), so N files in one dir resolve once
  (perf + AC-10 determinism / order-independence).

## Test Cases
### Unit
1. **TC-04-1 (AC-5):** vault global `mode:if-missing`; `Module-01/.wiki/sync.yaml`
   `mode:always` → a file under `Module-01` resolves `always`; a sibling elsewhere → `if-missing`.
2. **TC-04-2:** partial override — folder sets only `mode`, inherits global `detect`.
3. **TC-04-3 (AC-10):** resolution independent of file order; memo hit count == #dirs.
4. **TC-04-4:** divergent regex — `Module-NN` `group_key '^(\d+)'` vs `Lessons`
   `group_key '^(\d{8})'` both resolve correctly.
5. **TC-04-5 (security):** a symlinked `<dir>/.wiki/sync.yaml` → `SyncConfigError` (refused).

## Acceptance Criteria
- [ ] Deepest-wins deep-merge; per-dir memoization; hardening reused.
- [ ] `mypy --strict` clean; regression green.

## Notes
`deep_merge` lives in `scripts/wiki_index/config_loader.py:155` (dicts merge, scalars/lists replace).
