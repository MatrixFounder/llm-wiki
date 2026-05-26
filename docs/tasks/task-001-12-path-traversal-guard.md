# Task 001-12: Path-traversal guard utility [STUB CREATION]

## Use Case Connection
- UC-02 (manual ingest validates source path)
- All UCs that accept user-supplied paths

## Task Goal
Implement `validate_inside_vault(candidate: Path, vault_root: Path) -> Path` that returns the resolved absolute path if it is strictly inside `vault_root`, otherwise raises `PathTraversalError`. This is a pure utility — wired into adapters in task-001-24 and into `wiki-init --register-existing` in task-001-22.

## Changes Description

### New Files
- `scripts/wiki_index/security.py`:
  - `class PathTraversalError(ValueError): pass`
  - `def validate_inside_vault(candidate: Path, vault_root: Path) -> Path:`
    - Compute `abs_candidate = candidate.resolve(strict=True)` (raises `FileNotFoundError` if path does not exist — caller decides whether to catch).
    - Compute `abs_root = vault_root.resolve(strict=True)`.
    - Use `abs_candidate.is_relative_to(abs_root)` (Python 3.9+); if False → raise `PathTraversalError(f'{candidate} is outside vault root {vault_root}')`.
    - Return `abs_candidate`.
  - `def assert_no_symlink_escape(p: Path) -> None:` — walks `p.parents` and asserts no parent is a symlink targeting outside `p.root`. Stricter check used by sensitive operations (reindex).
- `tests/test_security.py` — comprehensive negative + positive cases.

### Changes in Existing Files
None.

### Component Integration
- Adapters call `validate_inside_vault(source_path, vault_root)` first thing in `fetch()`.
- `wiki-init` calls it on every operator-provided path before any FS or DB mutation.

## Test Cases

### End-to-end Tests
1. **TC-E2E-01**: Valid path inside vault returns resolved path.
   - Input: `vault_root=/tmp/v`, `candidate=/tmp/v/_sources/x.md`.
   - Expected: returns resolved absolute path, no exception.

### Unit Tests
1. **TC-UNIT-01**: `../../etc/passwd` outside vault → `PathTraversalError`.
2. **TC-UNIT-02**: Symlink pointing outside vault rejected by `assert_no_symlink_escape`.
3. **TC-UNIT-03**: Vault root itself accepted (returns same path).
4. **TC-UNIT-04**: `candidate` = nonexistent path → `FileNotFoundError` propagated (caller's responsibility).

### Regression Tests
- N/A.

## Acceptance Criteria
- [ ] Both functions implemented per spec.
- [ ] All TC-UNIT cases pass.
- [ ] `mypy --strict scripts/wiki_index/security.py` passes.
- [ ] Acceptance criterion for R-26 from TASK.md (`{error: "PATH_OUTSIDE_VAULT"}`) is encoded — the adapter wrapping (task-001-24) translates this exception into the JSON envelope.

## Notes
- Uses `Path.is_relative_to` (Python 3.9+). Project minimum is 3.11 per [TASK.md §5.3](../TASK.md).
- `strict=True` on `resolve()` is intentional: prevents TOCTOU races where the candidate path is created/destroyed between resolve and use.
