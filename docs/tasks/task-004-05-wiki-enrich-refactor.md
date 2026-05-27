# Task 004-05: `wiki_enrich.py` primary in-process path + subprocess fallback retained [STUB + LOGIC]

## Meta

- **Bead ID**: `task-004-05-wiki-enrich-refactor`
- **Slug**: `wiki-enrich-refactor`
- **Maps to**: Issue **I-V.5**; RTM rows **R-47**, **R-48** (also enforces R-56 invariants — `--source required=True`, `WikiIngestError` preserved)
- **Depends on**: `task-004-03-programmatic-ingest-api` (imports `ingest`, `IngestError`)
- **Estimated time**: 1 day
- **Priority**: Critical

## Use Case Connection

- **UC-V2**: End-user installs via single command (this bead is the primary-path consumer that no longer requires `wiki-ingest` on PATH).
- **UC-V1**: Operator updates vendored snapshot — the sync workflow ends with this consumer succeeding against the refreshed module.

## Task Goal

Refactor `scripts/wiki_skills/wiki_enrich.py` to use the vendored `ingest()` as its primary path. Implement the path-decision branch from ARCHITECTURE.md §1.5.2:
1. **PRIMARY** (default): `_VENDORED_AVAILABLE and os.environ.get("WIKI_ENRICH_NO_VENDORED") != "1"` → call `_vendored_ingest(...)` in-process. **NO `check_wiki_ingest_version()` call** on this path.
2. **FALLBACK** (subprocess): `WIKI_ENRICH_NO_VENDORED=1` OR vendored import failed → existing `subprocess.run(["wiki-ingest", ...])` flow. `check_wiki_ingest_version()` IS called here.
3. **NEITHER** (vendored ImportError + `wiki-ingest` not on PATH) → emit `{"error": "WIKI_INGEST_UNAVAILABLE", ...}`, exit 6.

R-56 invariants (preserve TASK 003 surface):
- `--source` argparse declaration remains `required=True`. **No mutual-exclusion group introduced** (that's TASK 003's job).
- `index_from_manifest()` and `_validate_manifest()` signatures unchanged.
- `class WikiIngestError(Exception)` preserved (used by the subprocess fallback path).
- All existing `--ingest-arg` passthrough behavior preserved on the subprocess fallback path.

## Stub-First Plan

**Phase 1 — Red→Green on stubs**:
1. At module top of `scripts/wiki_skills/wiki_enrich.py`, add (preserving existing code):
   ```python
   try:
       from scripts.wiki_ingest.commands.ingest import ingest as _vendored_ingest
       from scripts.wiki_ingest.commands.ingest import IngestError as _VendoredIngestError
       _VENDORED_AVAILABLE = True
   except ImportError:
       _vendored_ingest = None  # type: ignore[assignment]
       _VendoredIngestError = None  # type: ignore[assignment,misc]
       _VENDORED_AVAILABLE = False
   ```
2. Add a stub helper that **always raises** so tests can mock it:
   ```python
   def _call_vendored_ingest(source, vault, vault_id, **kwargs) -> dict:
       if not _VENDORED_AVAILABLE:
           raise RuntimeError("task-004-05 phase 1 stub")
       return _vendored_ingest(source=source, vault=vault, vault_id=vault_id, **kwargs)
   ```
3. Phase-1 tests in `tests/test_wiki_enrich.py`:
   - `test_vendored_symbol_imported`: assert `_VENDORED_AVAILABLE is True` (assumes I-V.3 landed).
   - `test_primary_path_called_when_vendored_available`: monkeypatch `_call_vendored_ingest` to return a canned manifest; invoke `main(argv)`; assert mock called once + `subprocess.run` NOT called.

**Phase 2 — Logic**:
1. Refactor `main(argv)` to implement the path-decision branch. Pseudocode:
   ```python
   use_vendored = _VENDORED_AVAILABLE and os.environ.get("WIKI_ENRICH_NO_VENDORED") != "1"
   if use_vendored:
       try:
           manifest = _call_vendored_ingest(
               source=Path(args.source),
               vault=vault_root,
               vault_id=args.vault,
               source_hash=None,
               known_concepts=None,
               dry_run=False,
               timeout_seconds=args.timeout_seconds,
               quiet=True,
           )
       except _VendoredIngestError as e:
           # Emit structured error and exit 6 — DO NOT fall back to subprocess
           # (IngestError is a content-level failure, not a transport failure)
           print(json.dumps({"error": "WIKI_INGEST_FAILED", "code": e.code, "phase": e.phase, "written_so_far": e.written_so_far}))
           return 6
   else:
       # Existing subprocess path (preserved verbatim modulo guard)
       if shutil.which(args.wiki_ingest_bin) is None:
           print(json.dumps({"error": "WIKI_INGEST_UNAVAILABLE", "hint": "Install wiki-ingest or unset WIKI_ENRICH_NO_VENDORED"}))
           return 6
       check_wiki_ingest_version(args.wiki_ingest_bin)
       # ... existing subprocess.run + _validate_manifest path ...
   # Common tail (both paths converge here):
   _validate_manifest(manifest, args.vault, vault_root)
   summary = index_from_manifest(manifest, args.vault, ...)
   print(json.dumps({"action": "enriched", "vault_id": args.vault, "ingest": manifest, "index": summary}))
   return 0
   ```
2. Phase-2 tests (added in I-V.7, not here — this bead just makes them passable).

## Changes Description

### New Files

- None.

### Changes in Existing Files

#### File: `scripts/wiki_skills/wiki_enrich.py`

**Module-level additions:**
- Lazy-import block for `_vendored_ingest`, `_VendoredIngestError`, `_VENDORED_AVAILABLE` (Phase 1).
- Helper `_call_vendored_ingest(source, vault, vault_id, **kwargs) -> dict` — wraps the vendored function for ease of mocking.

**`main(argv: list[str] | None = None) -> int` — refactored:**
- After argparse, compute `use_vendored = _VENDORED_AVAILABLE and os.environ.get("WIKI_ENRICH_NO_VENDORED") != "1"`.
- Branch: vendored path / subprocess fallback path / unavailable error.
- On the vendored path:
  - Call `_call_vendored_ingest(...)`.
  - On `_VendoredIngestError`: emit `WIKI_INGEST_FAILED` envelope, exit 6.
  - **DO NOT** call `check_wiki_ingest_version()` on this path (R-47(b)).
- On the subprocess path:
  - If `shutil.which(args.wiki_ingest_bin) is None`: emit `WIKI_INGEST_UNAVAILABLE`, exit 6.
  - Otherwise: existing flow (`check_wiki_ingest_version` → `subprocess.run` → `WikiIngestError` handling).
- Both paths converge on `_validate_manifest()` + `index_from_manifest()` + JSON envelope emit.

**Invariants preserved (R-56):**
- `p.add_argument("--source", required=True, ...)` at line 259 — **UNCHANGED**. Acceptance bullet greps for this exact string.
- `class WikiIngestError(Exception)` at line 46 — **UNCHANGED** (subprocess path still uses it).
- `_validate_manifest(manifest, expected_vault_id, vault_root)` signature — **UNCHANGED**.
- `index_from_manifest(manifest, vault_id, ...)` signature — **UNCHANGED**.

### Component Integration

- This bead is the **glue point** between the vendored module (I-V.1, I-V.3) and the existing indexing pipeline (`_validate_manifest`, `index_from_manifest`, `IndexRepository`).
- The vendored `ingest()` returns a dict matching the v1.1 manifest schema — `_validate_manifest()` operates on it unchanged.
- The output envelope `{"action": "enriched", "vault_id": ..., "ingest": ..., "index": ...}` is **byte-identical** on both paths (R-47(d)).

## Files Touched (explicit list)

- `scripts/wiki_skills/wiki_enrich.py` (modified — refactor `main()` + add module-level vendored-import block)

## Test Surface

- **Phase-1 tests in this bead** (added to `tests/test_wiki_enrich.py`):
  - `test_vendored_symbol_imported`
  - `test_primary_path_called_when_vendored_available`
- **Phase-2 tests in I-V.7** (`task-004-07-test-suite-update.md`):
  - `test_in_process_no_subprocess`
  - `test_no_vendored_env_forces_subprocess`
  - `test_import_error_with_binary_falls_back_to_subprocess`
  - `test_import_error_without_binary_emits_unavailable_error`
  - `test_ingest_error_emits_failed_envelope` (vendored path content-level failure)
- **Regression**: all existing `tests/test_wiki_enrich.py` tests must continue to pass after subprocess mocks are kept in place for the fallback-path tests.

## Acceptance

- [ ] R-47(a): On `--source` invocation with vendored module importable and `WIKI_ENRICH_NO_VENDORED` unset, `subprocess.run(["wiki-ingest", ...])` is NOT called (verified by mock).
- [ ] R-47(b): `check_wiki_ingest_version()` is NOT called on the in-process path (verified by mock).
- [ ] R-47(c): Manifest dict returned by vendored `ingest()` is consumed by existing `_validate_manifest()` and `index_from_manifest()` without modification to those functions.
- [ ] R-47(d): Output JSON envelope `{"action":"enriched", ...}` is structurally identical to the existing subprocess-based output (verified by golden-file or schema test).
- [ ] R-48(a): `WIKI_ENRICH_NO_VENDORED=1` forces the subprocess path (verified by mock).
- [ ] R-48(b): When vendored import raises `ImportError` AND `wiki-ingest` is on PATH, subprocess fallback activates silently.
- [ ] R-48(c): When vendored import raises `ImportError` AND `wiki-ingest` is NOT on PATH, `WIKI_INGEST_UNAVAILABLE` envelope emitted, exit 6.
- [ ] R-48(d): `check_wiki_ingest_version()` IS called on the subprocess path (verified).
- [ ] R-56(a) invariant: `grep -n 'required=True' scripts/wiki_skills/wiki_enrich.py` shows `--source` flag still has `required=True`. **No mutual-exclusion group introduced**.
- [ ] R-56(c) invariant: `class WikiIngestError(Exception)` still present and used by the subprocess fallback path.
- [ ] Phase-1 tests `test_vendored_symbol_imported`, `test_primary_path_called_when_vendored_available` pass.
- [ ] All existing 295+ tests still pass (subprocess-path tests now exercise the fallback branch — adjusted in I-V.7 but should still pass against this bead's refactor).

## Rollback

`git checkout scripts/wiki_skills/wiki_enrich.py tests/test_wiki_enrich.py`. The pre-refactor wiki_enrich.py returns. The vendored module remains in place (I-V.1) but no consumer wires to it.

## Notes

- **R-56 enforcement** is the most fragile invariant in this bead. The refactor is large and it's tempting to "tidy" the argparse declarations. **Do not.** The `--source required=True` line stays exactly as written. Acceptance bullet explicitly greps for it.
- **`IngestError` is NOT silently fallback-able**: a vendored `IngestError` is a *content-level* failure (e.g., source frontmatter type mismatch). Falling back to subprocess in that case would just produce the same content-level failure with a worse user experience. Per Decision-14 + UC-V2 A1, this bead emits `WIKI_INGEST_FAILED` and exits 6 — no subprocess attempt.
- The `WIKI_ENRICH_NO_VENDORED` env var is read **once at `main()` entry** (not at module import) so unit tests can `monkeypatch.setenv` reliably.
- `shutil.which(args.wiki_ingest_bin)` is mocked in tests via `monkeypatch.setattr("scripts.wiki_skills.wiki_enrich.shutil.which", lambda _: None)` — never rely on the real CI PATH (Risk R-3 mitigation).
