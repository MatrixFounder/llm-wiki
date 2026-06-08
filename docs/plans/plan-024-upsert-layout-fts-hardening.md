# PLAN 024 — `wiki-index-upsert` layout-awareness + FTS full-body + PARA docs

- **Task:** `task-024-upsert-layout-fts-hardening` (see `docs/TASK.md`, `docs/ARCHITECTURE.md` Q-024-1/2/3)
- **Strategy:** Stub-First (RED tests → GREEN impl). It is a **refactor + 2 small changes + docs**,
  so the "stub" is the parity-test contract that fails for `upsert` today.
- **Invariants every bead must hold:** Karpathy byte-identity (golden anchor); `validate_inside_vault`
  preserved (lives in `adapter.fetch`); `no import anthropic`; zero DDL (`user_version` 5); mypy --strict;
  full pytest green. Per the architecture-review: the shared helper serves **THREE** derivation sites
  (`reindex_full`, `reindex_delta`, `upsert_one`) and `upsert_one` has a **fourth** indirect caller
  (`_manifest_consumer.index_from_manifest` — the `wiki-enrich` path) that becomes layout-aware too.

## Bead 024-01 — RED: byte-parity + FTS contract tests
**Goal:** encode the acceptance contract; all new asserts RED (upsert not yet layout-aware; FTS capped).
- New `tests/test_upsert_layout_parity.py`:
  - helper `_index_both(tmp_path, layout, files)` builds a vault, runs `reindex_full` into DB-A and
    `upsert_one` (per file) into DB-B, returns both pages.
  - `test_parity_obsidian_personal_unicode_slug` — a Cyrillic-titled note (`Квартиры.md`): assert
    DB-B `(slug, project, type, sorted(tags))` == DB-A; assert slug == preserve-unicode value (`квартиры`),
    NOT `_vault_`/bare-stem (AC-1.1).
  - `test_parity_obsidian_personal_frontmatterless_title` — a note with only `# H1\nbody`: assert
    `title` from upsert == reindex (H1-synth via `frontmatter_synthesis`) (AC-1.6).
  - `test_parity_obsidian_personal_moc_note_types` — `type: moc` and `type: note`: upsert succeeds,
    db_type == reindex (no `UnmappedTypeError`) (AC-1.3).
  - `test_parity_refs_slugified` — a body `[[Title Case]]` link under obsidian-personal
    (preserve-unicode): upsert refs == reindex refs incl. slugified target (AC-1.5).
  - `test_upsert_then_reindex_no_duplicate` — upsert a file, then `reindex_full`; `SELECT count(*)`
    for that slug == 1 (AC-1.4).
  - `test_parity_karpathy_byte_identical` — karpathy fixture: upsert page tuple == reindex == today's
    values (AC-1.2 anchor).
  - `test_upsert_unmappable_type_exit6` — a `type:` not in the resolved layout's `type_mapping` →
    `UnmappedTypeError` envelope + exit 6, no traceback (UC-1/A4 — error contract survives the rewire).
  - `test_fts_indexes_full_body` — a page whose distinctive term sits at char >1000 of the body:
    `repo.search_pages("<deep-term>")` returns it (AC-2.1); a term <1000 still returned (AC-2.2) — RED.
  - `test_fts_full_body_after_reindex_rebuild` — a DB whose page was indexed under the OLD 1000-cap
    (simulate by storing a truncated `body_excerpt`), then `reindex_full` → the deep term is now found
    (UC-2/A2 — Class-A→B rebuild repopulates the full-body corpus, ADR-002 §D8).
- **DoD:** new tests fail for the right reasons (project `_vault_`, capped FTS); existing suite untouched.

## Bead 024-02 — GREEN R-1: single-file derivation + shared helper + 3-site rewire
- **(a) single-file `DiscoveredPage` derivation.** Factor `iter_pages`' per-entry logic
  (`scripts/wiki_index/layout_config.py:624-677`) into `derive_discovered_page(rel_or_path,
  vault_root, config) -> DiscoveredPage | None` — iterate `config.paths` and take the FIRST entry
  whose glob matches via the **`PurePosixPath(rel).full_match(entry.glob)` predicate** already used by
  `derive_project_for_path` (`layout_config.py:693-694`) — NOT `vault_root.glob` (single-file, not a
  walk) — then `_derive_project` + `slug_strategy` + per-glob `default_tags`/`extra_tags` + `raw_type`.
  **Thread `operator_supplied=config.paths_operator_supplied` into `_derive_project`** (TASK 017
  ReDoS-deadline seam — must not be dropped). `iter_pages` is refactored to call it per surviving path
  (behaviour-preserving — existing `test_layout_config.py` glob-order tests are the guard).
- **(b) shared per-file helper.** Add `derive_indexed_page(adapter, item, config) -> (page, refs,
  db_type)` (new private fn in `reindex.py`, or `scripts/wiki_index/_page_builder.py` if cleaner):
  `out = adapter.fetch(item)` [KEEPS `validate_inside_vault`] → `disc = derive_discovered_page(item.source_path, item.vault_root, config)`
  → `out = replace(out, page_slug=disc.slug, project=disc.project)` → `fm = _synthesize_fm(...)`
  → `normalize_frontmatter(fm, type_mapping, path_type_fallback, extra_tags=disc.extra_tags, glob_type=disc.raw_type)`
  → `page = _build_page(...)` → `refs = _body_refs(slug_strategy) + _frontmatter_refs(...)`.
  Accepts a `cite_skipped` list param (callers pass their own; `upsert_one` passes `[]`).
- **(c) rewire 3 sites to the helper:** `reindex_full` (`reindex.py:506-549`) and `reindex_delta`
  (`reindex.py:368-394`) replace their inline blocks with the helper call (byte-identical — guarded by
  existing reindex tests + golden anchor); `wiki_index_upsert.upsert_one` (`wiki_index_upsert.py:49-114`)
  resolves `config = resolve_layout_config(vault_root)` and calls the helper instead of the bare
  `normalize_frontmatter` + `derive_slug` path. Preserve upsert's exact JSON envelope + exit codes
  (`UnmappedTypeError`/`BodyNormalizationError` → exit 6 unchanged).
- **Ordered rewire (bound the blast radius):** rewire `reindex_full` → run `tests/test_wiki_reindex_full.py`
  + `test_layout_config.py` GREEN → rewire `reindex_delta` → run `test_wiki_reindex_delta.py` GREEN →
  rewire `upsert_one` → run `test_pages_upsert.py` + 024-01 GREEN. A site is not "done" until its suite is green.
- **DoD:** 024-01 R-1 tests GREEN; existing reindex/upsert/query/verify/manifest tests GREEN; mypy strict.

## Bead 024-03 — GREEN R-2: FTS full body
- In `_build_page` (`reindex.py`) drop the `[:1000]` slice → `body_excerpt=normalize_body_for_fts(out.body_text)`
  (now the single write site, since upsert routes through `_build_page` after 024-02). Remove the
  now-dead `normalized_body[:1000]` in `wiki_index_upsert.py` (replaced by the helper).
- Update docstrings: `models.py` (`body_excerpt` — fix the stale "First 500 chars" → "full normalized
  body; FTS search corpus; display bounded via snippet()") and `base.py:74`.
- **DoD:** `test_fts_indexes_full_body` GREEN; snippet display still bounded (no test asserts
  `len(body_excerpt)<=1000` — confirmed); existing FTS/search tests GREEN.

## Bead 024-04 — R-3 docs + manifest regression
- `workflows/wiki-sync.md` Step 4b: on a non-Karpathy layout, file the summary as a note + index via
  layout-aware `reindex`/`wiki-index-upsert`, NOT enrich into root `_sources/`; Step 4c: note upsert is
  layout-aware post-R-1; keep the Karpathy `_sources`/`wiki-enrich` path documented as still valid
  (layout-conditional). Mirror a one-liner in the `CLAUDE.md` vault template pointer.
- Add `test_manifest_upsert_karpathy_byte_identical` (arch-review C-1): `index_from_manifest` on a
  karpathy manifest yields the same rows post-R-1 (the 4th `upsert_one` caller stays byte-identical).
- **DoD:** docs updated; manifest regression GREEN; `no import anthropic` (grep).

## Bead 024-05 — Verify + harden
- Full `pytest tests/` + `mypy --strict scripts/` green.
- `/vdd-multi` (logic/security/performance critics) on the diff; fix convergent findings.
- Dogfood re-confirm on `samples/personal-vault-dogfood`: `upsert_one` of an obsidian-personal summary
  now files at the layout project (not `_vault_`) and a `reindex --full` makes no duplicate; `wiki-search "дофамин"`
  (the previously-missed deep term) now hits.
- **DoD:** all green; CLAUDE.md status pointer updated; session-state persisted.

## Risk / sequencing
- R-1 (024-02) is the refactor with the most blast radius (reindex hot path). Lead with the RED parity
  tests (024-01) + run the FULL reindex suite after each rewire site. R-2 (024-03) depends on R-1
  routing upsert through `_build_page`. R-3 (024-04) is independent (docs + 1 test).
