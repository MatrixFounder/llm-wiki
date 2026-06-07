# Task 019.03: [STUB] `_resummarize.py` surface

## Use Case Connection
- E1, E2, E3.2 (surface for all detectors + the gate)

## Task Goal
Create the SRP module with stubbed signatures so later beads fill logic; stubs are a
**no-op gate** (preserve byte-identity).

## Changes Description
### New Files
- `scripts/wiki_skills/_resummarize.py`:
  - `resolve_policy(path: Path, *, vault_root: Path, vault_config: SyncConfig) -> ResummarizeConfig | None`
    — **stub** returns `vault_config.resummarize`.
  - `summary_exists(path: Path, *, rel: str, vault_root: Path, repo: IndexRepository, vault_id: str, policy: ResummarizeConfig) -> str | None`
    — **stub** returns `None`.
  - `apply_policy(decision: Decision, *, path: Path, rel: str, vault_root: Path, repo: IndexRepository, vault_id: str, policy: ResummarizeConfig | None, force: bool) -> Decision`
    — **stub** returns `decision` unchanged.
- Acyclic imports: `_resummarize` imports `Decision` from `_sync`, `ResummarizeConfig`/
  `SyncConfig` from `sync_config`, `IndexRepository` from `repository`. `_sync` does NOT
  import `_resummarize`.

## Test Cases
### Unit (RED matrix)
1. **TC-03-1:** `apply_policy(ingest-decision, policy=None, force=False)` → unchanged.
2. **TC-03-2:** signatures import + `mypy --strict` resolves (no cycle).
3. **TC-03-3 (RED, xfail until 06):** `mode=if-missing` + a (future) match → expects `skip`.

## Acceptance Criteria
- [ ] Module imports; no import cycle; `mypy --strict` clean.
- [ ] Stub gate is a no-op (bead-00 golden green).

## Notes
Keep `apply_policy` the single entry point `_build_entries` will call.
