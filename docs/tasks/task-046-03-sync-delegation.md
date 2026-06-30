# Task 046-03 (P2) — wiki-sync delegates to wiki-import

Beads: B10 (stub) · B11 (R-8, plan delegation) · B12 (R-9, retire inline distil). Stub-First.
**Depends on** P1 (delegation passes `--kind`/`--concepts`) + P1b (conversion in `prepare`).

## Goal
`wiki-sync` stops doing its own summarise/enrich/extract/convert. `scan` emits a per-source
**delegation** to `wiki-import`; the `workflows/wiki-sync.md` executor runs `wiki-import`
prepare→REASON→apply per item. `upsert` (ready note → `wiki-index-upsert`) and `skip` unchanged.

## Context (files to edit)
- `scripts/wiki_skills/wiki_sync.py` — the `scan` plan builder (entry construction for
  `ingest`/`convert+ingest`).
- `workflows/wiki-sync.md` — Step 4 (4a convert + 4b ingest → replace with delegation; keep 4c/4d).
- New test: `tests/test_sync_delegation.py`. Reference: existing `tests/test_wiki_sync_*.py`.

## Steps
1. **B10** — create test file with 2 `@pytest.mark.skip` stubs.
2. **B11 (R-8)** — for `ingest`/`convert+ingest` entries, add
   `entry["delegate"] = {"tool":"wiki-import","kind":<resolved>,"diagrams":<bool>,
   "concepts":<bool>,"folder":<zone-folder + target_subdir>}`. `kind`/`diagrams`/`concepts`
   come from the effective `summarize` config (P3); until P3 lands, default
   `kind=<detected>`, `diagrams=false`, `concepts=true` (back-compat). The `convert+ingest`
   action collapses to `ingest`+`delegate` (conversion now lives in `wiki-import prepare`).
3. **B12 (R-9)** — rewrite `workflows/wiki-sync.md` Step 4: per delegated entry run
   `wiki-import prepare … && <REASON> && wiki-import apply …` with the entry's delegate flags;
   keep H-6 fencing inside the REASON step; keep Step 4c (`upsert`) + 4d (`record`). Remove the
   inline `summarizing-meetings`/`wiki-enrich`/`wiki-extract-concepts` steps and the
   `converter`/`normalize` plan fields from delegated entries.

## Test Cases
- **TC-UNIT-01 (B11/R-8)** `test_sync_scan_delegates_to_import`: a zone with a `.vtt` drop →
  plan entry has `delegate.tool == "wiki-import"` and `delegate.concepts == True` (default).
- **TC-UNIT-02 (B12/R-9)** `test_sync_plan_no_inline_distil`: a delegated entry omits
  `converter`/`normalize` (conversion moved to `prepare`).

## Verification
`pytest tests/test_sync_delegation.py tests/test_wiki_sync_*.py -v` green.
`mypy --strict scripts/` clean. `wiki-sync scan <zone> --dry-run` prints delegation per entry.
Idempotency unchanged: a recorded file is still `is_unchanged`.

## Acceptance
- [ ] plan emits `delegate` for source entries; `upsert`/`skip` unchanged.
- [ ] recipe no longer references inline summarise/enrich/extract for ingest.
- [ ] existing wiki-sync tests green (classification, idempotency, resummarize).
