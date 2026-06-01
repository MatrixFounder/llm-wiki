---
id: DF-2
type: known-issue
status: by-design
opened_at: 2026-05-29
category: dogfood
slug: df-2-entity-resolution-clis-leave-transient-page-level-class-b-drift
---

# entity-resolution CLIs leave transient page-level Class B drift

- **Symptom**: after `wiki-confirm`/`wiki-alias`/`wiki-merge` (which edit Class A frontmatter), `wiki-lint` reports `hash-mismatch` (the edited entity page's `pages.file_hash` is stale) and, after a merge, `missing-on-disk` (the deleted `from` concept page's `pages` row lingers).
- **Root cause**: the entity-resolution CLIs mutate Class A + mirror **entity/alias** Class B state, but do not re-index the **page** row (file_hash/body). By design — page-level Class B is reconciled by reindex (ADR-002 §D8 Class A canonical).
- **Affected components**: `wiki_confirm.py`, `wiki_alias.py`, `wiki_merge.py` (all entity-resolution mutators).
- **Resolution**: not a bug — `wiki-reindex --full` (verified) and `--delta` heal it to **0 lint issues**. Operator workflow: run `wiki-reindex --delta` after a batch of entity-resolution edits (the `MERGE_MIRROR_FAILED` envelope already advises this). A future polish could have the CLIs fire a targeted `wiki-index-upsert`/`delete_page` so lint stays clean between reindexes.
