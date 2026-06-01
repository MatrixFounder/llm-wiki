---
id: L-9
type: known-issue
status: open
opened_at: 2026-05-29
category: logic
severity: LOW
slug: l-9-entity-resolution-minor-logic-ux-nits-deferred
---

# entity-resolution minor logic/UX nits (deferred)

- **F11** `wiki-confirm` single-mode frontmatter + DB writes are not transactional; a DB-write failure after the frontmatter write leaves them divergent. **Recoverable by design** (Class A is canonical → `wiki-reindex --full` reconciles); no rollback added. Affected: `scripts/wiki_skills/wiki_confirm.py`.
- **F12a** `wiki-merge --dry-run` `aliases_absorbed` over-counts (does not subtract surfaces already on `into` or third-entity collisions that the real merge skips). Cosmetic preview drift. Affected: `scripts/wiki_skills/wiki_merge.py`.
- **F12b** `lint._scan_frontmatter_alias_collisions` swallows unparseable-frontmatter (`except Exception: continue`) → a malformed entity page with a colliding alias is silently skipped. Consider surfacing parse failures as their own lint issue.
- **F12c** the correlated `mentions_count` UPDATE is hand-copied in 4 places (reindex Step 3, `recompute_mentions`, `auto_promote_candidates`, `merge_entities`); extract one private helper so a future index change can't silently desync them. Maintainability, not a bug.
- **F12d** `wiki-merge` sanitizes redirect surfaces (`sanitize_alias_surface`) on the Class A frontmatter egress (F4) but `merge_entities` step 3 inserts the raw `from_slug`/`from_name` into `entity_aliases` (Class B). After a merge the two layers could hold differently-spelled aliases; harmless (slugs/names are ingest-constrained, and `wiki-reindex --full` re-derives Class B from Class A) but worth a consistency pass. Affected: `scripts/wiki_index/sqlite_repository.py::merge_entities`.
- **F3-residual (security contract note)**: `resolve_entity_file`'s `is_symlink()` refuse + `validate_inside_vault(strict=True)` close the leaf-symlink read/unlink vector and the static escape. A **parent-component symlink + sub-millisecond TOCTOU race** remains (same class as D-1's documented "no kernel-mediated walk" limit) — **accepted under the single-user-local threat model only**. If these CLIs are ever wrapped in an MCP server / web shim / multi-tenant context, this residual must be re-evaluated (FD-based `O_NOFOLLOW` mediated walk) before exposure.
- **Fix plan**: batch into a future entity-resolution polish bead; none block ship (all recoverable / cosmetic / maintainability / accepted-in-scope).

---
