---
id: DF-029-1
type: known-issue
status: fixed
opened_at: 2026-06-12
resolved_at: 2026-06-12
category: logic
severity: SEV-2
slug: df-029-1-reindex-delta-misses-mtime-preserved-rename
---

# wiki-reindex --delta misses an mtime-preserved rename → orphans its inbound links

- **Symptom**: after an app-side (or `mv`) **rename/move** of a note, `wiki-reindex
  --delta` left the renamed file **absent from the index** (`missing-in-db`) and its
  inbound wikilinks reported as `orphan-link`. Reproduced live on the obsidian-cli dogfood
  (TASK 029 / bead 029-06, 2026-06-12).
- **Root cause**: a rename/move **preserves the file's mtime**; `reindex_delta`'s gate
  selected only files newer than the last-indexed cutoff, so the renamed file (old mtime,
  new path) was skipped while its link-rewritten neighbours were indexed.
- **RESOLVED (TASK 030 / R-030-1, bead 030-01)**: `reindex_delta` is **rename-aware** —
  any on-disk path absent from the vault's `pages.file_path` set is ingested REGARDLESS
  of mtime (zero extra I/O: the membership set derives from the TASK-021 coalesced read).
  A path-only move with unchanged content gets a targeted `file_path` refresh on the
  upsert's "unchanged" short-circuit, so the SECOND delta is a true no-op (AC-1.9
  convergence). The fix covers the whole stale-mtime new-path class: app/`mv` renames,
  `cp -p`, archive extraction, sync-client imports, and the fresh-vault first delta
  (Q-030-3). New additive envelope field `new_path_ingested: [rel,…]`
  (+ `new_path_ingested_total` in `--all-vaults`). Per-file `sqlite3.Error` isolation
  (a stale row holding the destination path no longer aborts the run). E2e regression
  test = the 029-06 live repro (`tests/test_task030_delta_rename.py`).
- **Named residuals (out of the predicate's reach, on record)**:
  - **A5 — swap/rotation/overwrite renames**: every on-disk path remains present in
    `pages.file_path` → not detected; rows go content-stale. NOT a regression vs the
    pre-030 behavior; `wiki-lint`'s always-hash drift check detects it; remedy =
    `wiki-reindex --full`.
  - **A9 — persistent duplicate-key copy** (a retained `cp -p` copy sharing
    `(slug, project)` with its original): oscillates — one re-ingest + one
    `slug_collisions` WARN per delta. Pre-030 this state was silently stable-wrong;
    post-030 it is noisily wrong (TASK-020 detection-only posture). Remedy: remove or
    rename the copy, or split keys via a per-folder `project`.
  - `entities.file_path` registration rows still refresh on `--full` only
    (pre-existing boundary, pinned by test).
- **Operator guidance (updated)**: `wiki-reindex --delta` now suffices for rename/move
  to a previously-unindexed path; `--full` remains the universal fallback and the
  swap-class (A5) remedy. The obsidian-cli skill's coherence rule reflects this.
