# Task 004-07: `tests/test_wiki_enrich.py` — vendored-mock + 3 fallback-path cases [STUB + LOGIC]

## Meta

- **Bead ID**: `task-004-07-test-suite-update`
- **Slug**: `test-suite-update`
- **Maps to**: Issue **I-V.7**; RTM rows **R-51**
- **Depends on**: `task-004-05-wiki-enrich-refactor` (tests target the refactored module surface)
- **Estimated time**: 0.75 day
- **Priority**: Critical (gates I-V.11 regression sweep)

## Use Case Connection

- **UC-V2**: End-user installs via single command — these tests verify the primary path works without `wiki-ingest` on PATH.
- **Cross-cutting**: ensures the fallback path (UC-V2 A2, UC-V2 A1) is exercised by the test suite, not just by smokes.

## Task Goal

Update `tests/test_wiki_enrich.py` to reflect the refactored consumer:
1. Replace existing `subprocess.run` mocks with `unittest.mock.patch("scripts.wiki_skills.wiki_enrich._call_vendored_ingest")` (or `_vendored_ingest` directly) for primary-path tests.
2. Add 3 new test cases covering the fallback decision branches:
   - `WIKI_ENRICH_NO_VENDORED=1` → forces subprocess path.
   - `ImportError` on vendored import + `wiki-ingest` on PATH → subprocess fallback activates.
   - `ImportError` on vendored import + `wiki-ingest` NOT on PATH → `WIKI_INGEST_UNAVAILABLE` error envelope, exit 6.
3. Add a 4th case for content-level failure on the vendored path (`IngestError` → `WIKI_INGEST_FAILED` envelope, exit 6 — no subprocess fallback).

Total new test cases: **≥ 4** (push pytest count from 295 baseline to ≥ 299).

## Stub-First Plan

**Phase 1 — Stub**:
1. Add 4 new test stubs with `pytest.skip("task-004-07 phase 2")` decorators (or `pytest.mark.skip`):
   - `test_in_process_no_subprocess`
   - `test_no_vendored_env_forces_subprocess`
   - `test_import_error_with_binary_falls_back_to_subprocess`
   - `test_import_error_without_binary_emits_unavailable_error`
   - `test_ingest_error_emits_failed_envelope` (bonus 5th)
2. `pytest tests/test_wiki_enrich.py -v` — assert all 4-5 new tests are *collected* (and skipped). Existing tests pass.

**Phase 2 — Logic**:
1. Unskip and implement each test (details below).
2. Update existing subprocess-mocked tests to use `_call_vendored_ingest` mocks where applicable (i.e., where the assertion was "subprocess was called" → now "vendored was called").
3. Ensure all 295+ existing tests still pass after the mock-surface migration.

## Changes Description

### New Files

- None (extends existing `tests/test_wiki_enrich.py`).

### Changes in Existing Files

#### File: `tests/test_wiki_enrich.py`

**New tests:**

```python
def test_in_process_no_subprocess(monkeypatch, tmp_path):
    """R-47(a): primary path does NOT call subprocess.run."""
    # Setup minimal vault + source
    # ...
    canned_manifest = {"status": "ok", "written": [...], ...}
    monkeypatch.setattr(
        "scripts.wiki_skills.wiki_enrich._call_vendored_ingest",
        lambda **kw: canned_manifest,
    )
    subprocess_mock = MagicMock()
    monkeypatch.setattr("scripts.wiki_skills.wiki_enrich.subprocess.run", subprocess_mock)
    exit_code = wiki_enrich.main(["--vault", VID, "--vault-root", str(vault), "--source", str(src)])
    assert exit_code == 0
    assert subprocess_mock.call_count == 0  # CRITICAL R-47(a) assertion

def test_no_vendored_env_forces_subprocess(monkeypatch, tmp_path):
    """R-48(a): WIKI_ENRICH_NO_VENDORED=1 routes to subprocess."""
    monkeypatch.setenv("WIKI_ENRICH_NO_VENDORED", "1")
    monkeypatch.setattr("scripts.wiki_skills.wiki_enrich.shutil.which", lambda _: "/fake/bin/wiki-ingest")
    vendored_mock = MagicMock()
    monkeypatch.setattr("scripts.wiki_skills.wiki_enrich._call_vendored_ingest", vendored_mock)
    subprocess_mock = MagicMock(return_value=MagicMock(returncode=0, stdout=json.dumps(canned_manifest)))
    monkeypatch.setattr("scripts.wiki_skills.wiki_enrich.subprocess.run", subprocess_mock)
    monkeypatch.setattr("scripts.wiki_skills.wiki_enrich.check_wiki_ingest_version", MagicMock())
    exit_code = wiki_enrich.main([...])
    assert exit_code == 0
    assert vendored_mock.call_count == 0
    assert subprocess_mock.call_count == 1

def test_import_error_with_binary_falls_back_to_subprocess(monkeypatch, tmp_path):
    """R-48(b): ImportError + wiki-ingest on PATH → subprocess silently used."""
    monkeypatch.setattr("scripts.wiki_skills.wiki_enrich._VENDORED_AVAILABLE", False)
    monkeypatch.setattr("scripts.wiki_skills.wiki_enrich.shutil.which", lambda _: "/fake/bin/wiki-ingest")
    subprocess_mock = MagicMock(return_value=MagicMock(returncode=0, stdout=json.dumps(canned_manifest)))
    monkeypatch.setattr("scripts.wiki_skills.wiki_enrich.subprocess.run", subprocess_mock)
    monkeypatch.setattr("scripts.wiki_skills.wiki_enrich.check_wiki_ingest_version", MagicMock())
    exit_code = wiki_enrich.main([...])
    assert exit_code == 0
    assert subprocess_mock.call_count == 1

def test_import_error_without_binary_emits_unavailable_error(monkeypatch, capsys, tmp_path):
    """R-48(c): ImportError + wiki-ingest absent → WIKI_INGEST_UNAVAILABLE, exit 6."""
    monkeypatch.setattr("scripts.wiki_skills.wiki_enrich._VENDORED_AVAILABLE", False)
    monkeypatch.setattr("scripts.wiki_skills.wiki_enrich.shutil.which", lambda _: None)
    exit_code = wiki_enrich.main([...])
    assert exit_code == 6
    out = json.loads(capsys.readouterr().out)
    assert out["error"] == "WIKI_INGEST_UNAVAILABLE"

def test_ingest_error_emits_failed_envelope(monkeypatch, capsys, tmp_path):
    """UC-V2 A1: vendored IngestError → WIKI_INGEST_FAILED, exit 6, NO subprocess fallback."""
    from scripts.wiki_ingest.commands.ingest import IngestError
    def _raise(**kw):
        raise IngestError("not a summary", code="SOURCE_NEEDS_SUMMARIZATION", phase=None)
    monkeypatch.setattr("scripts.wiki_skills.wiki_enrich._call_vendored_ingest", _raise)
    subprocess_mock = MagicMock()
    monkeypatch.setattr("scripts.wiki_skills.wiki_enrich.subprocess.run", subprocess_mock)
    exit_code = wiki_enrich.main([...])
    assert exit_code == 6
    out = json.loads(capsys.readouterr().out)
    assert out["error"] == "WIKI_INGEST_FAILED"
    assert out["code"] == "SOURCE_NEEDS_SUMMARIZATION"
    assert subprocess_mock.call_count == 0  # CRITICAL: no fallback on content-level failure
```

**Existing tests — migrated:**
- Tests that previously mocked `subprocess.run` to simulate a wiki-ingest happy path now mock `_call_vendored_ingest` instead. Assertions about "vault_id is forwarded", "manifest is validated", etc., are preserved.
- Tests that specifically exercise the subprocess path (e.g., `--ingest-arg` passthrough, `check_wiki_ingest_version` failure) continue to mock `subprocess.run` BUT must also set `WIKI_ENRICH_NO_VENDORED=1` or `_VENDORED_AVAILABLE=False` so the subprocess path is actually taken.

### Component Integration

- This bead establishes the **test contract** the I-V.11 regression sweep will gate on (R-51 acceptance bullets + Smoke 6).
- Mock surface uses module-attribute patching (`monkeypatch.setattr("scripts.wiki_skills.wiki_enrich._call_vendored_ingest", ...)`) — never `unittest.mock.patch` as a context manager around the call (which is brittle to import order).

## Files Touched (explicit list)

- `tests/test_wiki_enrich.py` (modified — add ≥ 4 new tests + migrate existing subprocess mocks for primary-path tests)

## Test Surface

- **New tests**: ≥ 4 (5 if `test_ingest_error_emits_failed_envelope` counts):
  - `test_in_process_no_subprocess` (R-47(a))
  - `test_no_vendored_env_forces_subprocess` (R-48(a))
  - `test_import_error_with_binary_falls_back_to_subprocess` (R-48(b))
  - `test_import_error_without_binary_emits_unavailable_error` (R-48(c))
  - `test_ingest_error_emits_failed_envelope` (UC-V2 A1)
- **Migrated tests** (count varies — existing test file has ~30 tests; estimate ~10 of them need mock-surface migration).

## Acceptance

- [ ] R-51(a): `tests/test_wiki_enrich.py` uses `monkeypatch.setattr("scripts.wiki_skills.wiki_enrich._call_vendored_ingest", ...)` for primary-path tests (not subprocess mocks).
- [ ] R-51(b): `test_no_vendored_env_forces_subprocess` passes — assert subprocess called, vendored NOT called.
- [ ] R-51(c): `test_import_error_with_binary_falls_back_to_subprocess` passes.
- [ ] R-51(d): `test_import_error_without_binary_emits_unavailable_error` passes — exit 6, envelope has `error: "WIKI_INGEST_UNAVAILABLE"`.
- [ ] R-51(e): All existing 295+ tests continue to pass (no regression from mock-surface migration).
- [ ] Total pytest count is **≥ 299** (baseline 295 + ≥ 4 new tests).
- [ ] Risk R-3 mitigation: every test mocks `shutil.which` and `subprocess.run` at the module level — none rely on the real CI PATH state.

## Rollback

`git checkout tests/test_wiki_enrich.py`. The test suite returns to its pre-bead state. If I-V.11 still passes (i.e., subprocess-mock paths exercise the fallback branch coincidentally), this rollback is safe but lossy (no coverage of primary path). More likely: rolling back this bead and keeping I-V.5 leaves several tests failing, which is the intended Red state.

## Notes

- **`unittest.mock.patch` vs `monkeypatch.setattr`**: prefer `monkeypatch.setattr` (pytest-native, automatic cleanup, no import-order pitfalls). The TASK.md text mentions `unittest.mock.patch` but `monkeypatch` is the idiomatic pytest approach in this codebase (check existing tests for the convention).
- The test fixtures already exist from Phase 3a (`tests/conftest.py` minimal-vault). Reuse them; do not duplicate fixture setup.
- The 5th test (`test_ingest_error_emits_failed_envelope`) is **strongly recommended** even though it's not explicitly listed in R-51 acceptance bullets — it validates UC-V2 A1 + the "IngestError ≠ fallback to subprocess" semantic from Decision-14.
- **Mock the module attribute, not the imported symbol**: `monkeypatch.setattr("scripts.wiki_skills.wiki_enrich._call_vendored_ingest", ...)` works; `monkeypatch.setattr("scripts.wiki_ingest.commands.ingest.ingest", ...)` does NOT (Python's import binding semantics — the name in `wiki_enrich.py`'s module namespace was bound at import time).
