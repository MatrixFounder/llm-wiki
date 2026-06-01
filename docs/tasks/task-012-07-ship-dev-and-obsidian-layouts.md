# Task 012-07: Ship `dev-project.yaml` + `obsidian-personal.yaml` built-ins (R-X1 byte-identity gate)

## Use Case Connection
- UC-31: dev-project `docs/` indexes + is searchable/type-tagged/cross-referenced.
- UC-30: obsidian-personal vault indexes (deep hierarchy, system dirs, Cyrillic, `.base` skip).
- UC-29: the **R-X1 byte-identity gate** — all of 012-01..06 green for Karpathy ⇒ **operator review checkpoint**.

## Task Goal
Author the two remaining built-in layouts end-to-end and prove they index their fixtures
correctly, completing the R-X1 engine. This bead is the R-X1 milestone: after it, byte-identity
holds for Karpathy and the two new layout classes work — pause for operator review before the
KNOWN_ISSUES migration (Phase 4).

## Changes Description

### New Files

#### File: `scripts/wiki_index/layouts/dev-project.yaml` (NEW)
- `slug_strategy: transliterate` (cross-platform-safe default).
- `paths[]`: `docs/tasks/*.md`→task, `docs/plans/*.md`→plan, `docs/adr/*.md`→adr,
  `docs/reviews/*.md`→review, `docs/audit/*.md`→audit, `docs/architectures/*.md`→architecture,
  `docs/product/*.md`→product-doc, `docs/issues/*.md`→known-issue,
  `docs/issues/resolved/*.md`→known-issue+`extra_tags:[resolved]`, top-level `docs/TASK.md`→task,
  `docs/PLAN.md`→plan, `docs/ARCHITECTURE.md`→architecture, `docs/ROADMAP.md`→roadmap,
  `docs/proposals/*.md`→proposal. `project: _vault_` (flat dev-vault).
- `ignore`: `.git/**`, `**/.DS_Store`, `**/__pycache__/**`, `**/.pytest_cache/**`.
- `type_mapping` (tag-route, zero DDL): task/plan→brief; adr/review/audit/architecture/roadmap/
  known-issue/product-doc/proposal→research (+ matching tag).
- `path_type_fallback: {}` (dev types come from `paths[].type`).
- `ref_extraction`: wiki-link + markdown-link(stem) + id-ref
  (`\b(ADR-\d+|R-\d+(?:\.\d+)*|task-\d+(?:-\d+)*|M-\d+|P-\d+|UC-\d+(?:\.\d+)*)\b`).
- `frontmatter_synthesis: {enabled: true}` (dev docs may lack frontmatter — e.g. ROADMAP.md).
- `auto_indexes`: `[{source_type: known-issue, output: docs/KNOWN_ISSUES.md, group_by: category, sort_within_group: [severity, opened_at, id], template: assets/known-issues-ledger.md.tmpl}]` (consumed by PW-H/012-09).

#### File: `scripts/wiki_index/layouts/obsidian-personal.yaml` (NEW)
- Per proposal §11: numbered-folder + `_daily`/`_clippings`/`_inbox` system globs, MOC glob
  (`extra_tags:[moc]`), standalone-root `*.md`→`project:_root_`; `slug_strategy: preserve-unicode`;
  `ignore`: `.obsidian/**`, `.trash/**`, `_templates/**`, `**/*.base`, `**/.DS_Store`;
  `type_mapping`: note/daily-note/clipping→summary; `frontmatter_synthesis: {enabled: true}`;
  wiki-link + markdown-link ref rules.

#### Dir: `tests/fixtures/dev-project-vault/` (NEW)
- A minimal `docs/` (a TASK, an ADR mentioning `ADR-002`, a proposal) + `WIKI_SCHEMA.md`
  (`layout: dev-project`). (obsidian-personal fixture reused from 012-02.)

### Changes in Test Files
#### File: `tests/test_layouts_end_to_end.py` (NEW)
- dev-project fixture: `reindex_full` → adr/task/proposal rows with correct tags;
  `search_pages("ADR-002")` returns the ADR; id-ref `ADR-002` extracted.
- obsidian-personal fixture (from 012-02): all expected pages, correct `project`s, no PK
  collision, `.base`/`.obsidian` excluded, Cyrillic preserved.
- Both built-ins validate against `layout-config.schema.yaml` + pass the ReDoS budget.
- 012-00 golden snapshot green (Karpathy untouched).

## Acceptance Criteria
- ✅ Both built-ins validate + index their fixtures correctly.
- ✅ **R-X1 byte-identity gate:** 012-00 green; `pytest`+`mypy --strict` clean. ⇒ operator review.
- ✅ dev-project `wiki-search "ADR-002"` returns hits (proves UC-31 minus the bootstrap).

## Stub-First
Phase 1: configs present + schema-valid (no fixture indexing yet). Phase 2: fixtures + the
end-to-end indexing assertions.
