# Task 003-10: `build_manifest` — wiki-ingest v1.1-compatible manifest emission

## Meta

- **Bead ID**: `task-003-10-manifest-builder`
- **Slug**: `manifest-builder`
- **Maps to**: Issue **I-7.10**; RTM row **R-35**.
- **Depends on**: task-003-01 (helper stub exists), task-003-08 (refs upserted before manifest built so the log_event reflects the work done).
- **Estimated time**: 0.5 day
- **Priority**: Critical (the deliverable shape; consumed by `validate_manifest` + `index_from_manifest`)

## Use Case Connection

- **UC-08 step 11**: "Builds manifest; emits JSON to stdout."
- **UC-08 (main with `--ingest`) step 11′**: "Builds manifest dict (held in memory, not emitted to stdout yet)."

## Task Goal

Replace the `NotImplementedError` stub in `wiki_extract_concepts.py::build_manifest(vault_id, source_slug, source_hash, create_list, mention_list, log_event, vault_root) -> dict` with the v1.1-compatible manifest structure per R-35:

```python
{
    "status": "ok",
    "vault_id": vault_id,
    "source": {
        "slug": source_slug,
        "hash": source_hash,
    },
    "written": [
        # one entry per create_list item
        {
            "kind": "concept",
            "path": "_concepts/<slug>.md",  # vault-relative
            "action": "created",  # or "unchanged" if file pre-existed (003-06 skip path)
            "slug": "<slug>",
        },
        # ...
    ],
    "mentioned": [
        # one entry per mention_list item AND per create_list item that was a slug match
        {
            "slug": "<slug>",
            "action": "mentioned",  # or "confirmed" / "created" / "updated" — from 003-07b return
        },
        # ...
    ],
    "log_event": {
        "event_type": "ingest",
        "subject": "<source-page-title>",
        "details": {"extraction_summary": {...}},
    },
    "extraction_summary": {
        "create_count": len(create_list),
        "mention_count": len(mention_list),
        "model": "claude-sonnet-4-6",
    },
}
```

## Stub-First Plan

**Phase 1 — Red test on stub**:

1. Add to `tests/test_wiki_extract_concepts.py`:
   - `test_build_manifest_minimal_shape` (Phase 1):
     - Call `build_manifest("vid","src","hash",[],[],{"event_type":"ingest","subject":"S"}, Path("/v"))`.
     - On stub: `NotImplementedError`. After Phase 2: returns dict with `status="ok"`, `vault_id="vid"`, `written=[]`, `mentioned=[]`.
   - `test_build_manifest_includes_create_items` (Phase 2):
     - `create_list = [{"slug":"foo","name":"Foo","action":"create"}, ...]`.
     - Assert `manifest["written"]` has 2 items with `kind="concept"`, `path="_concepts/foo.md"`, etc.
   - `test_build_manifest_includes_mention_items` (Phase 2):
     - `mention_list = [{"slug":"bar","name":"Bar","action":"mention"}]`.
     - Assert `manifest["mentioned"]` has 1 item with `slug="bar"`.
   - `test_build_manifest_passes_validate_manifest` (Phase 2 — CRITICAL):
     - Build a non-trivial manifest with create+mention items.
     - Call `validate_manifest(manifest, vault_id, vault_root)` from `_manifest_consumer`.
     - Assert no exception (proves the manifest the skill produces is contract-valid — R-35(h)).
2. Run pytest — Red.

**Phase 2 — Logic**:

1. Replace the body:
   ```python
   def build_manifest(
       vault_id: str,
       source_slug: str,
       source_hash: str,
       create_list: list[dict[str, Any]],
       mention_list: list[dict[str, Any]],
       log_event: dict[str, Any],
       vault_root: Path,
   ) -> dict[str, Any]:
       """Assemble the v1.1-compatible manifest.

       Caller is responsible for setting per-item action fields on candidates
       (003-05 sets 'create'/'mention'; 003-06 sets 'unchanged' when file
       pre-existed; 003-07b returns 'created'/'updated'/'confirmed').

       Validated against _manifest_consumer.validate_manifest before emit.
       """
       written: list[dict[str, Any]] = []
       for cand in create_list:
           page_action = cand.get("file_write_action", "created")  # 'created' or 'unchanged'
           written.append({
               "kind": "concept",
               "path": f"_concepts/{cand['slug']}.md",
               "action": page_action,
               "slug": cand["slug"],
           })
       mentioned: list[dict[str, Any]] = []
       for cand in mention_list + create_list:
           mentioned.append({
               "slug": cand["slug"],
               "action": cand.get("entity_action", cand["action"]),  # 'mentioned'/'confirmed'/...
           })
       return {
           "status": "ok",
           "vault_id": vault_id,
           "source": {"slug": source_slug, "hash": source_hash},
           "written": written,
           "mentioned": mentioned,
           "log_event": log_event,
           "extraction_summary": {
               "create_count": len(create_list),
               "mention_count": len(mention_list),
           },
       }
   ```
2. Caller in `main()` annotates each candidate with `file_write_action` (from 003-06's return — "created" or "unchanged") and `entity_action` (from 003-07b's return — "created"/"updated"/"confirmed").
3. Wire emit logic: when `--ingest` is False, emit manifest JSON to stdout and return 0. When `--ingest` is True, return the dict to be combined with the index summary (003-11).
4. Unskip Phase-2 tests; run pytest — Green.

## Changes Description

### New Files

- None.

### Changes in Existing Files

#### File: `scripts/wiki_skills/wiki_extract_concepts.py`

- Replace `build_manifest` stub body with the assembly logic.
- Wire `main()` to emit JSON to stdout when `--ingest` is False:
  ```python
  manifest = build_manifest(...)
  if not args.ingest:
      print(json.dumps(manifest, indent=2))
      return 0
  # else continue to dispatch (003-11)
  ```

#### File: `tests/test_wiki_extract_concepts.py`

- Add 4 unit tests.

### Component Integration

- Output (manifest dict) consumed by:
  - stdout emit when `--ingest` is False.
  - `dispatch_to_indexer` (003-11) when `--ingest` is True.
- Manifest MUST pass `validate_manifest` (live import from `_manifest_consumer`) — R-35(h). This is the structural contract gate.

## Files Touched (explicit list)

- `scripts/wiki_skills/wiki_extract_concepts.py` (modified — 1 stub replacement + `main()` emit wiring)
- `tests/test_wiki_extract_concepts.py` (modified — add 4 tests)

## Test Surface

- **New**: 4 unit tests:
  - `test_build_manifest_minimal_shape`
  - `test_build_manifest_includes_create_items`
  - `test_build_manifest_includes_mention_items`
  - `test_build_manifest_passes_validate_manifest` (the critical contract test)

## Acceptance Criteria

- [ ] **R-35(a)**: `status="ok"` on success path.
- [ ] **R-35(b)**: `vault_id` field matches caller's `--vault`.
- [ ] **R-35(c)**: `written[]` array; one entry per `create` item with `kind="concept"`, `path="_concepts/<slug>.md"`, `action="created"`; existing-file skips → `action="unchanged"`.
- [ ] **R-35(d)**: `source` object with `slug` and `hash`.
- [ ] **R-35(e)**: `log_event` object with `event_type="ingest"`, `subject=<source-title>`.
- [ ] **R-35(f)**: manifest emitted to stdout as JSON when `--ingest` is NOT set.
- [ ] **R-35(g)**: no manifest emitted on failure — only error envelope (handled by `main()` exception handlers from 003-04, 003-11).
- [ ] **R-35(h) CRITICAL**: built manifest passes `validate_manifest(...)` from `_manifest_consumer` (verified by `test_build_manifest_passes_validate_manifest`).
- [ ] All 4 unit tests pass.
- [ ] `mypy --strict` clean.
- [ ] Full sweep `pytest tests/ -q` still green.

## Verification

```bash
pytest tests/test_wiki_extract_concepts.py -v -k "build_manifest"
pytest tests/ -q
mypy --strict scripts/wiki_skills/wiki_extract_concepts.py
```

## Rollback

Revert `build_manifest` to stub; remove the 4 tests. 003-11 (dispatch) cannot proceed until restored.

## Notes

- The `extraction_summary` field is non-canonical (not in the v1.1 contract) but useful for operator visibility — kept inside the manifest for now. `validate_manifest` is permissive about extra fields per Phase 3a behavior (verify: `_validate_manifest` does field-presence checks, not "extra-fields rejected" — read the function body in `_manifest_consumer.py` to confirm).
- The dual-action confusion (file action vs. entity action) is the trickiest part. Recommendation: name the candidate dict fields clearly — `file_write_action` for 003-06's output, `entity_action` for 003-07b's output. Pre-populate them before passing to `build_manifest`.
- The `mentioned[]` array intentionally includes BOTH `create_list` and `mention_list` items — every extracted candidate gets a mention regardless of whether a new page was created (R-38 entity-refs invariant).
- `log_event` is built in `main()` (not here) — typical shape `{"event_type":"ingest","subject":<title>,"vault_id":<vid>,"details":{...}}`. The manifest just passes it through.
