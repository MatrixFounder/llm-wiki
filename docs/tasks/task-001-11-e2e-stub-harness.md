# Task 001-11: E2E test harness — asserts stubs return hardcoded values [STUB CREATION]

## Use Case Connection
- All UCs (validation that the stub chain end-to-end returns documented hardcoded outputs)

## Task Goal
Write a single E2E test module that walks the full CLI chain on the `minimal_vault` fixture and asserts each scaffold returns its documented hardcoded JSON. The harness is updated in Stage 2 (after task-001-25, task-001-28, etc.) to assert real values instead.

## Changes Description

### New Files
- `tests/test_e2e_stage1_stubs.py`:
  - `def test_full_pipeline_stub_chain(minimal_vault: Path) -> None:` — runs each skill in sequence via `subprocess.run`, parses JSON, asserts `action == 'stub'`.
  - `def test_make_repo_returns_stub(repo_factory) -> None:` — instantiates a repo and asserts `register_vault(...)` raises `NotImplementedError` with expected message.
  - `def test_manual_adapter_returns_stub(minimal_vault: Path) -> None:` — calls `ManualSourceAdapter().fetch(...)` and asserts hardcoded output.
- `tests/.AGENTS.md` — add note: "E2E harness is the Stage 1 → Stage 2 progression contract — when implementing a method, also update the corresponding assertion here."

### Changes in Existing Files
- Update `tests/conftest.py` (from task-001-10) if needed to expose helper for running skills as subprocess.

### Component Integration
- This is the gate test for Stage 1 completion. After all six scaffolds + adapter stub return their hardcoded outputs and these assertions pass, Stage 1 is "Green" per Stub-First methodology.

## Test Cases

### End-to-end Tests
1. **TC-E2E-01**: All six scaffold CLIs return `{"action": "stub", ...}` on minimal-vault.
2. **TC-E2E-02**: `SQLiteRepository.register_vault(...)` raises `NotImplementedError` with task-id hint in message.
3. **TC-E2E-03**: `ManualSourceAdapter().fetch(...)` returns documented hardcoded `SourceOutput` (slug `'stub-page'`, hash `'0'*64`).

### Unit Tests
N/A (this task IS the E2E layer).

### Regression Tests
- All TC-* from tasks 001-01 through 001-10 still pass.

## Acceptance Criteria
- [ ] `pytest tests/test_e2e_stage1_stubs.py -v` exits 0.
- [ ] All three E2E test cases pass.
- [ ] Each assertion message includes the task-ID that will replace it with real-value assertions.

## Notes
- This file is **modified, not deleted** when transitioning to Stage 2. Each stub assertion is replaced by a real assertion in the relevant Stage 2 task.
- Per `skill-tdd-stub-first` §2.4: "Update E2E test to assert real behavior" — that work is captured in tasks 001-15 through 001-32.
