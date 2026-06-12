---
id: DF-029-1
type: known-issue
status: mitigated
opened_at: 2026-06-12
category: logic
severity: SEV-2
slug: df-029-1-reindex-delta-misses-mtime-preserved-rename
---

# wiki-reindex --delta misses an mtime-preserved rename → orphans its inbound links

- **Symptom**: after an app-side (or `mv`) **rename/move** of a note, `wiki-reindex
  --delta` leaves the renamed file **absent from the index** (`missing-in-db`) and its
  inbound wikilinks reported as `orphan-link`. Reproduced live on the obsidian-cli dogfood
  (TASK 029 / bead 029-06, 2026-06-12): `obsidian rename` of `cli-dogfood-target.md`
  (2 inbound `[[…]]`) → `wiki-reindex --delta` → `wiki-lint`: **orphan-link: 2,
  missing-in-db: 1** (baseline was 0).
- **Root cause**: a rename/move **preserves the file's mtime**. `reindex_delta` selects
  files whose mtime is newer than the last-indexed cutoff, so the renamed file (old mtime,
  new path) is **skipped**, while its link-rewritten neighbours (fresh mtime) are indexed —
  leaving their now-rewritten `[[new-name]]` links pointing at a page with no row.
  Measured: renamed file mtime `1781276569` < neighbours `1781276641`.
- **Mitigation (shipped, skill-level, zero-code)**: the `obsidian-cli` skill's coherence
  protocol + recipe + eval E-07 prescribe **`wiki-reindex --full`** for rename/move (proven
  → 0 orphans), with `touch "<new path>" && wiki-reindex --delta` documented as the cheaper
  equivalent (also proven → 0 orphans). `delete` is unaffected (the missing path is
  detected). Content edits (`append`/`property:set`/…) bump mtime, so `--delta` + upsert
  stay correct for them.
- **Residual / future code fix (out of TASK 029 scope — zero-code task)**: make
  `reindex_delta` rename-aware so a plain `--delta` suffices — e.g. detect a path present
  on disk but absent from the index (new path) regardless of mtime, or track inode/
  content-hash. Until then the skill's `--full`-for-rename guidance is the correct
  operator-facing answer. Trigger for the code fix: a large vault where `--full` on every
  rename is too costly.
