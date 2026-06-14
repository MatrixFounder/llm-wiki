# 031-02 — per-type templates + cybos reference doc

**Owns:** AC-4.1 + AC-5.1. **Dep:** 031-01 (type names). **Detail:** PLAN.md §2.

## Scope
Ship per-type authoring templates as committed config-data + a reference doc — config-driven, nothing in Python.

## Files
- `templates/page-types/{decision,requirement,risk,incident,hypothesis,fact,event}.md` (7 NEW) — canonical frontmatter (`type`, `title`, `tags`, `created`/`date`) + **reserved INERT Phase-2 edge keys** (`implements`/`supersedes`/`superseded_by`/`caused_by`/`relates_to`, commented or empty) + an example body.
- `docs/layouts/cybos.md` (NEW) — per-type → (db_type, tag) table; one authoring example each; the F10 filtering note (`--types <db_type>` + FTS, NOT `--where tag=`); the per-project `<vault>/.wiki/layout.yaml` `type_mapping` UNION override recipe; reserved-edge-keys / Phase-2 (ROADMAP R-13) note.

## Stub-First
`test_page_type_templates_valid`: each template parses as frontmatter; its `type:` ∈ cybos `type_mapping`; reserved edge keys present-but-inert.

## Verify
`mypy --strict` (no code); templates copy-reindex cleanly under the 031-04 fixture.
