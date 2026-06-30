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
1. **B10** — RED tests in `tests/test_sync_delegation.py`.
2. **B11 (R-8)** — for `ingest`/`convert+ingest` entries, add (in `_build_entries`)
   `entry["delegate"] = {"tool":"wiki-import","source":<rel>,"folder":<topic>,"kind":<k>,
   "diagrams":<bool>,"concepts":<bool>}` + the `_delegate_folder` helper (topic = the source's
   folder, or its parent when under `_raw/`/`.staging/`). `kind`/`diagrams`/`concepts` default
   here (`auto`/`false`/`true` — back-compat) and are populated from the per-folder `summarize`
   config in P3. **Additive (as shipped):** the classifier's `converter`/`normalize`/`staged_target`
   stay in the entry as the **detected-format hint** (wiki-import `prepare` re-detects + converts) —
   dropping them would break ~24 existing classifier/plan assertions for no gain. `upsert`/`skip`
   entries carry NO `delegate`.
3. **B12 (R-9)** — rewrite `workflows/wiki-sync.md` Step 4a/4b into ONE "distil = delegate to
   wiki-import" step: per delegated entry run `wiki-import prepare → REASON → apply` with the
   delegate flags (`--kind`, `--diagrams` iff `delegate.diagrams`, `--no-concepts` iff not
   `delegate.concepts`); conversion is wiki-import `prepare`'s job (no inline convert/de-timestamp);
   keep 4c (`upsert`) + 4d (`record` the original source hash = the D1 idempotency marker). Remove
   the inline `summarizing-meetings`/`wiki-enrich`/`wiki-extract-concepts` steps.

## Test Cases (shipped)
- **TC-UNIT-01 (B11/R-8)** `test_sync_scan_delegates_to_import`: a `.vtt` under `_raw/` →
  `delegate.tool == "wiki-import"`, `concepts == True`, `kind == "auto"`, `folder == "courses"`.
- **TC-UNIT-02 (R-9)** `test_sync_plan_delegates_not_inline`: EVERY ingest/convert+ingest entry
  carries a wiki-import `delegate` (executor delegates, never inlines); `upsert`/`skip` carry none.
- **TC-UNIT-03** `test_delegate_folder_resolution`: `_delegate_folder` strips `_raw`/`.staging`.

## Verification
`pytest tests/test_sync_delegation.py tests/test_wiki_sync_*.py -v` green.
`mypy --strict scripts/` clean. `wiki-sync scan <zone> --dry-run` prints delegation per entry.
Idempotency unchanged: a recorded file is still `is_unchanged`.

## Acceptance
- [ ] plan emits `delegate` for source entries; `upsert`/`skip` unchanged.
- [ ] recipe no longer references inline summarise/enrich/extract for ingest.
- [ ] existing wiki-sync tests green (classification, idempotency, resummarize).
