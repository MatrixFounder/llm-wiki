---
id: DF-046-2
type: known-issue
status: open
opened_at: 2026-06-30
category: class-b-integrity
slug: df-046-2-wiki-sync-can-upsert-a-nested-raw-capture
---

# wiki-sync can `upsert` a nested `_raw/` capture (Class-B drift if the 4d marker is skipped)

- **Symptom**: After a delegated import, `wiki-import` writes its raw capture at
  `<topic>/_raw/<slug>.md` (or `<topic>/<target_subdir>/_raw/<slug>.md`). On the NEXT
  `wiki-sync scan`, that nested capture is classified **`upsert`** (ready-note) and would be
  `wiki-index-upsert`-ed — but the layout `ignore: **/_raw/**` means `wiki-reindex --full` will
  NOT reproduce it → a Class-B (rebuildable-cache) drift: an index row reindex can't rebuild.
  Found by the TASK 046 P3 dogfood (real vault, `_summary/_raw/<slug>.md`).
- **Root cause**: `wiki-sync`'s walk INGESTS `_raw/` but `in_raw` is computed as
  `rel == "_raw" or rel.startswith("_raw/")` (`scripts/wiki_skills/_sync.py`) — only a
  VAULT-ROOT `_raw/` is `in_raw`. A NESTED `<x>/_raw/*.md` is NOT `in_raw`, so it falls through
  to the content rules → a `.md` with a `source:` frontmatter (the capture) maps to a `note`/
  ready-summary → `upsert`. (A vault-root `_raw/*.md` instead short-circuits to `ingest` → the P2
  re-ingest-loop variant.) Either way wiki-sync's `_raw` handling diverges from reindex's
  `**/_raw/**` ignore at depth.
- **Current mitigation (TASK 046 P2/P3 — in-flow)**: the `wiki-sync` recipe Step 4d records a
  `source_state` commit-marker for BOTH the original source AND wiki-import's capture
  (`prepare.raw_path`), so the next scan marks the capture `is_unchanged` → the executor no-ops it.
  This fully prevents the drift **when the recipe is followed**; the residual is executor-dependence
  (a run that skips the capture-marker re-ingests/upserts it).
- **Fix (separate task — deterministic hardening)**: align `wiki-sync`'s `_raw` handling with the
  reindex `**/_raw/**` ignore at ANY depth — make `in_raw` match a `/_raw/` segment anywhere (so a
  nested capture is `ingest`, never `upsert`, and the 4d marker covers it consistently), OR skip a
  `_raw/*.md` that carries a `source:`-only frontmatter (the wiki-import-capture signature). This is
  a `_sync.py` classifier change → its own focused change + review (test-suite blast radius).
- **Scope**: residual hardening; **out of scope** for TASK 046 (the in-flow recipe marker is the
  shipped mechanism). Related: the P2 re-ingest-loop fix (the vault-root variant) and
  `_delegate_folder` `_RAW_DIR_NAMES` (strips `_raw`/`.staging`/`_transcripts` so captures file in
  the topic folder, not inside a raw tree).
