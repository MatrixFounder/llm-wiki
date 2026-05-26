# Task 001-09: `wiki-reindex` CLI skill scaffold [STUB CREATION]

## Use Case Connection
- UC-05 (bulk migration validates reindex)
- Phase 3a rebuildability invariant

## Task Goal
Create the `wiki-reindex` CLI scaffold supporting `--full`, `--delta`, `--vault <id>`, and `--all-vaults`. Hardcoded JSON response. Real impl in task-001-30 (full) and task-001-31 (delta).

## Changes Description

### New Files
- `scripts/wiki_skills/wiki_reindex.py`:
  - argparse: subcommand `--full | --delta`; `--vault <id>` OR `--all-vaults` (mutually exclusive).
  - Stub output: `{"action": "stub", "skill": "wiki-reindex", "mode": "full|delta", "vaults_processed": 0, "pages_indexed": 0}`.
- `tests/test_wiki_reindex_scaffold.py` — invocation tests for each flag combination.

### Changes in Existing Files
None.

### Component Integration
- Will become the operational entrypoint for the Class A → B rebuildability proof (task-001-34).

## Test Cases

### End-to-end Tests
1. **TC-E2E-01**: `wiki-reindex --full --vault test` exits 0 with stub JSON.
2. **TC-E2E-02**: `wiki-reindex --full --vault x --all-vaults` exits 2 (mutually exclusive).

### Unit Tests
1. **TC-UNIT-01**: `--delta` and `--full` mutually exclusive.

### Regression Tests
- task-001-08 scaffold tests still pass.

## Acceptance Criteria
- [ ] Scaffold invokable, exits 0 on valid args.
- [ ] Mutually-exclusive groups enforced.
- [ ] `tests/test_wiki_reindex_scaffold.py` passes.

## Notes
- The full impl owns the rebuildability invariant — see ADR-002 §D8.
- Delta mode SLO: < 100ms / 100 docs (no changes); see [TASK.md §5.1](../TASK.md).
