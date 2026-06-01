---
name: WIKI_SCHEMA
vault_id: obsidian-llm-wiki
schema_version: "2.0"
language: en
layout: dev-project
description: "obsidian-llm-wiki dev-vault — its own docs/ (TASKs, ADRs, plans, reviews, proposals, per-file KNOWN_ISSUES) indexed via the R-X2 dev-project layout. vault_root = this docs/ directory (R-X1/R-X2)."
---

# obsidian-llm-wiki — dev-vault declaration

This `docs/` tree is a **dev-project** wiki vault (TASK 012 / R-X2-A). The
config-driven layout engine indexes its `tasks/`, `adr/`, `plans/`, `reviews/`,
`audit/`, `architectures/`, `proposals/`, and per-issue `issues/*.md` as
first-class, type-tagged, cross-referenced pages, and renders `KNOWN_ISSUES.md`
as a Class-B auto-generated ledger from the Class-A `issues/*.md` files
(ADR-002 §D8 "rebuildable markdown" sub-case).

`vault_root` = this `docs/` directory; the layout grammar lives in the built-in
`scripts/wiki_index/layouts/dev-project.yaml` (globs are docs/-root-relative).
The repo root deliberately carries **no** vault marker ("repo is not a vault").
