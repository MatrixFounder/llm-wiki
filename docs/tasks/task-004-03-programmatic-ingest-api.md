# Task 004-03: Programmatic `ingest()` + `IngestError` extraction [STUB-FIRST CANONICAL]

## Meta

- **Bead ID**: `task-004-03-programmatic-ingest-api`
- **Slug**: `programmatic-ingest-api`
- **Maps to**: Issue **I-V.3**; RTM rows **R-46** (and R-57 indirectly — preserves `execute()` CLI surface)
- **Depends on**: `task-004-01-vendor-bootstrap` (file must exist before refactor)
- **Estimated time**: 1 day
- **Priority**: Critical (blocks I-V.4 and I-V.5)

## Use Case Connection

- **UC-V2**: End-user installs via single command (this bead lands the in-process API the primary path will call).

## Task Goal

Extract a programmatic `ingest(source, vault, vault_id, source_hash, known_concepts, dry_run, timeout_seconds, quiet) -> dict` function from the vendored `scripts/wiki_ingest/commands/ingest.py::execute(args)`. Define a public `IngestError` exception class carrying `code`, `phase`, `written_so_far`, `child_exit_code` attributes. Refactor `execute(args)` to call `ingest()` internally and convert `IngestError` to `_safety.die()` so the CLI surface (R-57, Smoke 4) remains intact. **No `sys.exit()` calls in the `ingest()` call graph** — failure modes raise `IngestError`.

This is the **canonical stub-first bead** for TASK 004 per the operator briefing. The signature lands in Phase 1 with a `NotImplementedError` body and tests assert the stub raises predictably; Phase 2 fills in the logic.

## Stub-First Plan

**Phase 1 — Red→Green on stub**:
1. Add at the top of `scripts/wiki_ingest/commands/ingest.py` (above the existing `execute()`):
   ```python
   class IngestError(Exception):
       def __init__(
           self,
           message: str,
           code: str,
           phase: str | None = None,
           written_so_far: list[dict] | None = None,
           child_exit_code: int = 0,
       ) -> None:
           super().__init__(message)
           self.code = code
           self.phase = phase
           self.written_so_far = written_so_far or []
           self.child_exit_code = child_exit_code

   def ingest(
       source: "Path",
       vault: "Path",
       vault_id: str | None = None,
       source_hash: str | None = None,
       known_concepts: list[dict] | None = None,
       dry_run: bool = False,
       timeout_seconds: int = 600,
       quiet: bool = True,
   ) -> dict:
       raise NotImplementedError("task-004-03 phase 1 stub")
   ```
2. Write `tests/test_vendored_ingest_api.py`:
   - `test_ingest_importable`: `from scripts.wiki_ingest.commands.ingest import ingest, IngestError` succeeds.
   - `test_ingest_stub_raises_not_implemented`: calling `ingest(source=Path("/x"), vault=Path("/y"))` raises `NotImplementedError`.
   - `test_ingest_error_attributes`: `IngestError("msg", code="X", phase="upsert", written_so_far=[{"path":"a"}], child_exit_code=3)` has all four attrs accessible and `str(err) == "msg"`.
3. Run pytest — these 3 tests pass; `execute()` is **untouched** at this stage (no regression on Smoke 4).

**Phase 2 — Logic**:
1. Refactor the body of upstream `execute(args)` into the `ingest(...)` function:
   - Replace every `_safety.die(message, code=X)` (or equivalent) with `raise IngestError(message, code=X, phase=..., written_so_far=...)`.
   - Replace `argparse.Namespace.<attr>` accesses with the explicit keyword arguments.
   - Preserve the existing pipeline composition: `register-summary → upsert-page × N → update-index → append-log → log-event` via `_dispatch.dispatch()`.
   - Return the v1.1 manifest dict directly (NOT serialized to JSON — that's `execute()`'s job).
2. Rewrite `execute(args)` to be a thin wrapper:
   ```python
   def execute(args: argparse.Namespace) -> int:
       try:
           manifest = ingest(
               source=Path(args.source),
               vault=Path(args.vault),
               vault_id=getattr(args, "vault_id", None),
               source_hash=getattr(args, "source_hash", None),
               known_concepts=_load_known_concepts(args),
               dry_run=getattr(args, "dry_run", False),
               timeout_seconds=getattr(args, "timeout_seconds", 600),
               quiet=getattr(args, "quiet", False),
           )
       except IngestError as e:
           _safety.die(str(e), code=e.code, phase=e.phase, written_so_far=e.written_so_far)
       _emit(manifest, output_format=getattr(args, "output_format", "json"))
       return 0
   ```
3. Update `tests/test_vendored_ingest_api.py` Phase-2 tests:
   - `test_ingest_returns_manifest_on_success`: minimal happy-path with a fixture summary file → `ingest(...)` returns a dict with `status="ok"`, `written` is a list.
   - `test_ingest_raises_on_source_not_summary`: source with `type: note` → `IngestError` with `code="SOURCE_NEEDS_SUMMARIZATION"`.
   - `test_execute_wraps_ingest_for_cli`: invoke `execute()` with an argparse Namespace; assert `_safety.die` is called when `ingest()` raises (mock `_safety.die`).

## Changes Description

### New Files

- `tests/test_vendored_ingest_api.py` — Phase-1 stub tests + Phase-2 logic tests (~6 tests total).

### Changes in Existing Files

#### File: `scripts/wiki_ingest/commands/ingest.py` (the vendored copy)

**New top-level symbols:**
- `class IngestError(Exception)` — signature per Phase-1 stub above. Public API.
- `def ingest(source, vault, vault_id, source_hash, known_concepts, dry_run, timeout_seconds, quiet) -> dict` — pipeline body migrated from `execute()`. Public API.

**Modified:**
- `def execute(args: argparse.Namespace) -> int` — now a thin wrapper that calls `ingest()` and converts `IngestError` to `_safety.die()`. Behavior on the CLI path is byte-identical to upstream.

#### File: `scripts/wiki_ingest/VENDORED_FROM.md`

- Add a `local_patches` entry:
  ```markdown
  - **commands/ingest.py** (lines: top + `execute()` body): TASK 004 / I-V.3 — extracted programmatic `ingest()` + `IngestError`; `execute()` now wraps `ingest()`. Sync script must preserve this divergence (`--accept-local-divergence` required when re-syncing until the change is pushed upstream).
  ```

### Component Integration

- This bead is the foundation for I-V.5. After Phase 2, `from scripts.wiki_ingest.commands.ingest import ingest, IngestError` is the documented in-process entry point.
- The standalone CLI surface (`python -m scripts.wiki_ingest.commands.ingest --source X --vault Y --output-format json`) MUST continue to exit 0 on the happy path (Smoke 4, R-57). The Phase-2 test `test_execute_wraps_ingest_for_cli` plus the I-V.11 Smoke 4 verifies this.

## Files Touched (explicit list)

- `scripts/wiki_ingest/commands/ingest.py` (modified — refactor)
- `scripts/wiki_ingest/VENDORED_FROM.md` (modified — add `local_patches` entry)
- `tests/test_vendored_ingest_api.py` (new)

## Test Surface

- **New**: `tests/test_vendored_ingest_api.py`:
  - Phase-1: `test_ingest_importable`, `test_ingest_stub_raises_not_implemented`, `test_ingest_error_attributes`.
  - Phase-2: `test_ingest_returns_manifest_on_success`, `test_ingest_raises_on_source_not_summary` (asserts `code="SOURCE_NEEDS_SUMMARIZATION"`), `test_execute_wraps_ingest_for_cli`.
- **Touched (regression)**: existing tests for `wiki-ingest` upstream pipeline (if any are imported by this repo's test suite) must continue to pass.

## Acceptance

- [ ] R-46(a): `scripts/wiki_ingest/commands/ingest.py` exports a top-level `ingest(source, vault, ...)` function matching Decision-13 signature (8 parameters incl. `quiet`).
- [ ] R-46(b): `ingest()` returns a `dict` matching the v1.1 manifest schema on success.
- [ ] R-46(c): `ingest()` raises `IngestError` on all failure modes — `grep -rn "sys.exit\|_safety.die" scripts/wiki_ingest/commands/ingest.py` reports zero matches inside the `ingest()` function body (only `execute()` may call `_safety.die`).
- [ ] R-46(d): `IngestError` carries `code: str`, `phase: str | None`, `written_so_far: list[dict]`, `child_exit_code: int` attributes (verified by `test_ingest_error_attributes`).
- [ ] R-46(e): `execute(args)` continues to work by calling `ingest()` internally and converting `IngestError` to `_safety.die()` (verified by `test_execute_wraps_ingest_for_cli` + Smoke 4).
- [ ] All 6 tests in `tests/test_vendored_ingest_api.py` pass.
- [ ] All previous 295+ tests still pass.

## Rollback

`git checkout scripts/wiki_ingest/commands/ingest.py scripts/wiki_ingest/VENDORED_FROM.md && rm tests/test_vendored_ingest_api.py`. Because the upstream `execute()` body is restored verbatim, the CLI path returns to its pre-refactor state. I-V.5 will then fail because the `ingest` symbol disappears — but I-V.5 hasn't shipped yet, so no consumer breakage.

## Notes

- `known_concepts` is **decorative for v1.1** (upstream `execute()` is summary-passthrough; LLM synthesis is not in the current path). The parameter exists for interface symmetry so TASK 003's `wiki-extract-concepts` consumer does not need a breaking change later (per TASK.md §5.3 notes).
- `timeout_seconds` is also decorative in-process (no subprocess to bound). Retained for interface symmetry with the subprocess fallback path.
- The function is **synchronous** — no `async def`. Pipeline is filesystem I/O + in-process dispatches.
- `IngestError.written_so_far` should be populated by every `_dispatch.dispatch()` call site so partial-success state is surfaced (callers can decide whether to surface "partial" vs "failed").
- Type hints in the signature MUST use modern syntax (`str | None`, `list[dict]`) — Python 3.14 minimum per project policy. I-V.4 will validate this under `mypy --strict`.
