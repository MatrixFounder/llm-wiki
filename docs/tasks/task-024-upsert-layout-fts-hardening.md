# TASK 024 — `wiki-index-upsert` layout-awareness + FTS full-body + PARA enrich guidance

## 0. Meta

- **Task ID:** 024
- **Slug:** `task-024-upsert-layout-fts-hardening`
- **Mode:** VDD (full) — `/vdd-start-feature`
- **Context:** Findings from the 2026-06-08 FULL end-to-end dogfood of
  `samples/personal-vault-dogfood` (the user's real PARA Obsidian vault clone).
  The dogfood ran the whole pipeline on real data (de-timestamp → summarise →
  file → index → record → idempotent re-scan) and surfaced concrete defects in
  the *write* paths used by the `wiki-sync` executor on an **obsidian-personal**
  (PARA) vault.
- **Predecessor (uncommitted):** the prior same-session batch (informally "TASK
  023") shipped `obsidian-personal` summary `type_mapping`, structured `sources:`
  provenance (`all_cited_sources` object-harvest), and the `transcript_dedup`
  feature. TASK 024 builds on that working tree (all green: 1093 pytest, mypy
  strict). Both batches are still uncommitted — git hygiene handled at merge.
- **Out of scope (explicit):**
  - **pptx → markdown extraction** — the user is reworking it in a separate
    project. TASK 024 does NOT touch the pptx skill or its conversion path.
  - `slides.pptx` 18-byte stub — the user deleted it. No action.
  - 334 orphan-links — expected compounding backlog (resolved by running
    `wiki-extract-concepts`), not a defect.

## 1. Problem Description

On a PARA (`obsidian-personal`) vault, the two layout-aware indexers disagree:

1. **`wiki-index-upsert` is NOT layout-aware (BUG, HIGH).** It indexes a single
   file via `ManualSourceAdapter.fetch` → `derive_slug()` (the pre-TASK-012
   slug/project deriver) and calls `normalize_frontmatter(...)` with **no**
   `type_mapping`/`glob_type` (so it falls back to the module-level karpathy
   `TYPE_MAPPING`). Empirically on the dogfood:
   - it filed pages at project **`_vault_`** instead of the layout-derived PARA
     project (`Learning/Courses`, `Learning/Webinars`, …); and
   - it only "worked" because karpathy `TYPE_MAPPING` happens to contain
     `lesson-summary`/`meeting-summary`/`summary` — it would raise
     `UnmappedTypeError` on `type: note`/`moc`/`daily-note`/`clipping`/
     `webinar-summary` (obsidian-personal-only types that `reindex` maps fine).
   Consequence: the `wiki-sync` workflow Step 4c ("ready note →
   `wiki-index-upsert`") produces rows inconsistent with `reindex`, and a later
   `reindex --full` creates a **duplicate** row for the same file (different
   `project` ⇒ different `(vault_id, slug, project)` PK). The dogfood worked
   around it by using `reindex` (layout-aware) instead of `upsert`.

2. **FTS indexes only the first 1000 chars of the body (MED).** `pages_fts` is
   fed by triggers over `pages.body_excerpt`, and `body_excerpt =
   normalize_body_for_fts(body)[:1000]`. A term that appears only past ~1000
   chars of a long summary is NOT FTS-searchable (dogfood: `"дофамин"`, deep in
   a lecture summary, returned no hit although it is in the page). The 1000-char
   slice is a *display* concern conflated with the *search* corpus.

3. **`wiki-enrich` / vendored `wiki-ingest` is Karpathy-only (LOW, docs).** It
   writes `_sources/_concepts/_entities` at the vault root — wrong for a PARA
   vault (pollutes the tree, requires a two-tier course-root). The PARA-native
   ingest flow is: file the generated summary as a normal note in the right
   folder, then index it via the (now layout-aware) `reindex`/`wiki-index-upsert`.
   The executor workflow (`workflows/wiki-sync.md` Step 4b/4c) and `CLAUDE.md`
   templates currently imply enrich; they must state the PARA path.

## 2. Requirements Traceability Matrix (RTM)

| ID | Requirement | MVP? | Sub-features |
| :-- | :-- | :-- | :-- |
| **R-1** | `wiki-index-upsert` is layout-aware — **byte-parity with `reindex`** for the same file (the full per-page surface `reindex.py:506-538`, not a subset) | ✅ | (a) resolve the vault's layout (`resolve_layout_config`) in the upsert path; (b) derive **both `slug` (via the layout's `slug_strategy`) AND `project`** via the layout — matching `reindex`'s `replace(out, page_slug=disc.slug, project=disc.project)` (`reindex.py:517`), NOT `derive_slug`'s `path.stem`/`_vault_` fallback; (c) thread **all four** into `normalize_frontmatter` — `type_mapping`, `path_type_fallback`, `extra_tags` (from `disc.extra_tags`, into which per-glob `default_tags` flow), `glob_type` (from `disc.raw_type`) — matching `reindex.py:520-526`, so obsidian-personal types map AND karpathy stays byte-identical; (d) derive refs via the layout's `ref_extraction` **and slugify ref targets through `slug_strategy`** (`_apply_slug_strategy`, `reindex.py:538`), not hardcoded `extract_wiki_links`; (e) apply the layout's `frontmatter_synthesis` (`_synthesize_fm`, `reindex.py:518-519`) before `normalize_frontmatter`, so a frontmatter-less obsidian-personal note gets the same synthesized `title`; (f) regression test asserting upsert(file) ⇒ same `(slug, project, type, sorted(tags), title, refs)` as reindex(file) for karpathy AND obsidian-personal, incl. a **Unicode-titled** note and a **frontmatter-less** note |
| **R-2** | FTS searches the FULL normalized body, not just `body_excerpt[:1000]` | ✅ | (a) decouple the FTS search corpus from the 1000-char display excerpt; (b) schema/trigger update so `pages_fts` indexes the full normalized body; (c) decide DDL vs non-DDL (Architecture / OQ-1) incl. `user_version` bump if needed; (d) `body_excerpt` (display/snippet) unchanged; (e) test: a term beyond char 1000 of a page body is found by `wiki-search`; backward-compat for existing DBs (rebuild-on-reindex per ADR-002 §D8) |
| **R-3** | PARA-native ingest guidance (docs only) | ✅ | (a) `workflows/wiki-sync.md` Step 4b (ingest/summary filing): on a non-Karpathy (PARA) layout, file the generated summary as a note in the right folder + index via layout-aware `reindex`/`upsert`, NOT enrich into root `_sources/`; (b) `workflows/wiki-sync.md` Step 4c (ready note): note it is layout-aware after R-1; (c) the Karpathy `_sources`/`wiki-enrich` path is documented as **still valid** for Karpathy/two-tier vaults — the guidance is layout-conditional, not "never enrich"; (d) mirror the layout-conditional note in the `CLAUDE.md` vault template / `README` pointer; no code change |

## 3. Use Cases

### UC-1 — Upsert a PARA note (R-1)
- **Actors:** orchestrator (wiki-sync executor), `wiki-index-upsert` CLI.
- **Preconditions:** vault registered with `layout: obsidian-personal`; a ready
  `.md` exists at `03 - Learning/Courses/<C>/_summary/x.md` with `type: lesson-summary`.
- **Main scenario:** `wiki-index-upsert --source <abs> --vault <id> --vault-root <root>`
  → resolves obsidian-personal layout → derives project `Learning/Courses`, slug
  `x`, db_type `summary` (+ tag `lesson`), refs via layout ref_extraction → upserts.
- **Alternative scenarios:**
  - A1 `type: note`/`moc`/`daily-note`/`clipping`/`webinar-summary` → maps via the
    obsidian-personal `type_mapping` (today: `UnmappedTypeError`). PASS = upserts.
  - A2 karpathy vault, same file → byte-identical to today (no regression).
  - A3 file matches NO layout glob → the layout's OWN catch-all project (for
    obsidian-personal: `_root_`, per `obsidian-personal.yaml:42`), matching
    `reindex`, NOT a hardcoded `_vault_`.
  - A4 unmappable type even under the resolved layout → controlled `UnmappedTypeError`
    + exit 6 (unchanged error contract), never a traceback.
- **Postconditions:** the upserted row equals what `reindex --full` would write
  for that file; a subsequent `reindex --full` produces NO duplicate (same PK).
- **Acceptance criteria (binary):**
  - AC-1.1 For a **Unicode-titled** obsidian-personal file (e.g. `Квартиры.md`),
    `upsert` row `(slug, project, type, sorted(tags))` == `reindex` row — i.e.
    `slug` equals the `slug_strategy`-derived value (`preserve-unicode`), not the
    bare stem.
  - AC-1.2 For ≥1 karpathy fixture, `upsert` output is byte-identical to pre-TASK-024.
  - AC-1.3 `upsert` of a `type: moc`/`note` file on obsidian-personal succeeds
    (no `UnmappedTypeError`).
  - AC-1.4 After `upsert` then `reindex --full`, `SELECT count(*)` for that slug == 1
    (no duplicate from a slug OR project divergence).
  - AC-1.5 refs from `upsert` == refs from `reindex` for the same file (incl.
    `slug_strategy`-slugified ref targets on a non-`identity` layout).
  - AC-1.6 a **frontmatter-less** obsidian-personal note's `title` from `upsert`
    == `reindex` (first-H1 synthesized via `frontmatter_synthesis`).

### UC-2 — Search a long summary's tail (R-2)
- **Actors:** user, `wiki-search`.
- **Preconditions:** a page whose body has a distinctive term only AFTER char 1000.
- **Main scenario:** `wiki-search "<deep-term>"` → returns the page.
- **Alternative scenarios:**
  - A1 term within first 1000 chars → still found (no regression).
  - A2 existing DB built before TASK 024 → after `reindex`, the deep term is found
    (Class A→B rebuild; no silent stale index).
- **Postconditions:** snippet/display still bounded; DB size increase bounded/acceptable.
- **Acceptance criteria (binary):**
  - AC-2.1 A term at char >1000 of a page body is returned by `wiki-search`.
  - AC-2.2 A term within the first 1000 chars is still returned.
  - AC-2.3 `body_excerpt` (display) length contract unchanged.

### UC-3 — PARA ingest guidance (R-3)
- **Actors:** orchestrator reading the workflow / a human operator.
- **Acceptance criteria (binary):**
  - AC-3.1 `workflows/wiki-sync.md` Step 4b/4c explicitly describes the PARA path
    (file note + layout-aware index) and when enrich/`_sources` applies (Karpathy).
  - AC-3.2 No `import anthropic`, no code/schema change for R-3.

## 4. Non-Functional / Invariants
- **Karpathy byte-identity** preserved (golden anchor) for R-1 and R-2.
- **mypy --strict** clean; full pytest green (≥ current 1093 + new tests).
- **No new runtime deps.** `no import anthropic` in any skill (grep-guarded).
- **ADR-002 §D8**: the SQLite index stays Class-B rebuildable from Class-A markdown.

## 5. Open Questions
- **OQ-1 (R-2 shape):** `pages_fts` is an **internal-content** FTS5 table fed by
  triggers over `pages.body_excerpt` (`sql/wiki-index-v2.sql:358-389`), so the
  search corpus currently IS the 1000-char excerpt. Expand it via (A) a dedicated
  FTS-only column carrying the full normalized body + trigger/`body_excerpt`-split
  (DDL → `user_version` 5→6; FTS stores a 2nd full copy of every body), (B) raise
  the `body_excerpt` cap and keep one column (no DDL, larger stored excerpt,
  snippet still bounded — bloats `pages.body_excerpt` for display too), or
  (C) `content=''` **external-content** FTS5 reading the body on demand
  (size-conscious; leans on ADR-002 §D8 Class-B rebuildability). → **Architect to
  decide** (bias: smallest correct change; recent tasks favour zero-DDL but B
  conflates search and display — weigh against A/C).
- **OQ-2 (R-1 blast radius):** `ManualSourceAdapter` is also used by `wiki-query`,
  `wiki-verify-multi` (and `benchmark.py`). Make the **upsert call site**
  layout-aware (resolve layout, override slug/project/type/refs/title) rather than
  changing `derive_slug` globally — OR factor `reindex`'s per-page derivation
  (`reindex.py:506-538`: `iter_pages` → `replace(slug,project)` → `_synthesize_fm`
  → `normalize_frontmatter(all 4)` → ref slugify) into a shared helper both call.
  → **Architect to choose** the seam; must NOT change `wiki-query`/`wiki-verify`
  behaviour. (R-1(c)'s four-arg parity is now a stated requirement, not open —
  confirmed against `reindex.py:520-526`.)
