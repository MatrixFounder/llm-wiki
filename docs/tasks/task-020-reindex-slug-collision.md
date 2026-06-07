# TASK 020: [LIGHT] wiki-reindex — surface intra-project slug collisions

### 0. Meta
- **Task ID:** 020
- **Slug:** `reindex-slug-collision`
- **Mode:** LIGHT (trivial, low-risk hardening — no DDL, no new deps, additive envelope field).
- **Source:** TASK 019 dogfood finding (ARCHITECTURE §11a Q-019-11): on `samples/Demand-generation`,
  `wiki-reindex --full` reported `pages: 53` while the DB held 52 rows — two identically-titled
  lessons (`07 - Домашнее задание` in Module-04 AND Module-06) collided on the
  `(vault_id, slug, project)` PK and the second `upsert_page` SILENTLY overwrote the first.
  `skipped`/`alias_collisions` were empty, so the operator gets **no signal**, and D2a/search
  then under-detect the lost page.

### 1. What's broken
`reindex_full` (and `reindex_delta`) iterate `iter_pages(...)` and call `repo.upsert_page(page)`,
incrementing `pages_count` per **iteration** (discovered file). The `upsert_page` return
(`inserted`/`updated`/`unchanged`) is **discarded**. When two distinct `file_path`s resolve to the
same `(slug, project)`, the second silently UPDATEs (clobbers) the first row — no error, no report.

### 2. The fix (additive, detect + report only)
- In `reindex_full` and `reindex_delta`: track `seen: dict[(slug, project) -> file_path]` over the
  discovered pages. When a SECOND distinct `file_path` maps to an already-seen `(slug, project)`,
  record a `collision` `{slug, project, kept, dropped}` and emit a one-shot `_LOG.warning`.
- Add `collisions: list[...]` to both functions' return dicts and to the `wiki-reindex` CLI envelope
  (sibling of the existing `skipped` / `alias_collisions`).
- **Detect + report ONLY** — do NOT auto-resolve (renaming / re-namespacing slugs is an operator
  decision; the right mitigation is a per-folder `project` / `project_pattern`, as the TASK 019
  dogfood vault does).

### 3. Acceptance
- ✅ A vault with two `.md` resolving to the same `(slug, project)` → `reindex --full` and `--delta`
  both return a non-empty `collisions` list naming both file paths; a WARN is logged.
- ✅ No collision → `collisions: []` (back-compat; existing envelopes gain an empty field).
- ✅ Detection only — the DB still ends with the last-writer row (deterministic, POSIX-sorted);
  behavior otherwise unchanged.
- ✅ Full `pytest` + `mypy --strict scripts/` green; **zero DDL** (`user_version` 5); no new deps.

### 4. Out of scope
- Auto-resolving collisions (namespacing slugs, auto-project). Operator fixes via layout `project`.
- Any change to `upsert_page` PK semantics or the search/D2a read paths.
