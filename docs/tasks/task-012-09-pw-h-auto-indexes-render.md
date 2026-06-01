# Task 012-09: PW-H — `auto_indexes[]` render engine + render-trigger contract

> **`skill-tdd-strict`** (the rebuildability invariant is the §D8 keystone for the migration).
> Depends on 012-08 (ADR acceptance pin).

## Use Case Connection
- UC-32: `wiki-index-render --auto-indexes` regenerates `docs/KNOWN_ISSUES.md` from per-issue files.

## Task Goal
Extend `wiki-index-render` to render `config.auto_indexes[]` targets (PW-H): an aggregated,
grouped/sorted markdown projection that is a **pure deterministic function of the Class-A
per-issue files**, byte-identical on re-render modulo a single `GENERATED-AT` header line.

## Changes Description

### Changes in Existing Files

#### File: `scripts/wiki_index/rendering.py`
- `render_auto_index(repo, vault_id, auto_index, issues) -> str`: gather the source-type
  pages (e.g. `known-issue`), `group_by` (category), `sort_within_group` with a **stable
  total order ending in a final `id` tiebreaker** (architecture-review M2 — equal
  `(severity, opened_at)` never reorders across machines/clones); render via a small
  dependency-free Python renderer + an optional `assets/<name>.md.tmpl` (`string.Template`)
  for the shell. Preserve `BEGIN-CUSTOM` blocks (reuse `extract_custom_sections`).
- Body is a pure function of Class-A content; the ONLY volatile line is the
  `<!-- GENERATED-AT: <iso8601> by wiki-index-render --auto-indexes -->` header.
- `output` path is `validate_inside_vault`-checked before the atomic write
  (architecture-review m3); written via `atomic_write` / `atomic_write_text`.
- Store `sha256(header-stripped body)` in `<vault>/.wiki/state.json` (keyed by `output`).

#### File: `scripts/wiki_skills/wiki_index_render.py`
- Add `--auto-indexes` flag → after the normal `index.md` render, walk `config.auto_indexes[]`
  and render each `output`. `wiki-reindex --full/--delta` invoke this at the end.

#### File: the upsert path (`scripts/wiki_skills/wiki_index_upsert.py` / `_manifest_consumer`)
- **Render-trigger contract:** at the end of an upsert batch that creates OR deletes a page
  whose **tag-route type** is `known-issue` (predicate on the tag/frontmatter marker, NOT a
  `pages.type` value — zero-DDL), fire the `auto_indexes[]` render for the affected output.

### New Files
#### File: `scripts/wiki_index/assets/known-issues-ledger.md.tmpl` (NEW)
- `string.Template` shell for the rendered ledger (header + grouped sections placeholder).

### Changes in Test Files
#### File: `tests/test_auto_indexes_render.py` (NEW, tdd-strict)
- Build a vault with 3 `docs/issues/*.md` (2 categories, a severity tie); render; assert the
  output groups by category + sorts by `[severity, opened_at, id]` deterministically.
- **Rebuildability:** delete the output, re-render → byte-identical **modulo the GENERATED-AT
  line**; the `.wiki/state.json` sha256 matches.
- Tie-break determinism: two issues equal on `(severity, opened_at)` render in `id` order
  regardless of filesystem glob order (shuffle input → identical output).
- `BEGIN-CUSTOM` blocks preserved across re-render.
- `output: ../escape.md` → `PathTraversalError`/refused.
- Render-trigger: an upsert creating a `known-issue` page re-renders the ledger.

## Acceptance Criteria
- ✅ Ledger render is pure + byte-identical on re-render (modulo GENERATED-AT); sha256 pinned.
- ✅ Stable total order with `id` tiebreaker; `BEGIN-CUSTOM` preserved; output path-guarded.
- ✅ Render-trigger fires on `known-issue` create/delete. `mypy --strict` clean; suite green.

## Stub-First (`skill-tdd-strict`)
Phase 1: `render_auto_index` returns header-only; tests RED for grouping/sort/rebuildability.
Phase 2: full renderer + state.json + trigger + path-guard, each edge RED-first.
