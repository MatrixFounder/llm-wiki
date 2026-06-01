---
id: R-X1-REF-SLUGIFY
type: known-issue
status: fixed
opened_at: 2026-06-01
category: logic
severity: SEV-2
slug: r-x1-ref-target-not-slugified
---

# wiki-link ref targets are not run through `slug_strategy` → links to existing pages flagged orphan under non-identity slug layouts

> **RESOLVED 2026-06-01 (TASK 014, fix-option 1).** `reindex._body_refs` now runs
> each extracted ref target through the layout's `slug_strategy`
> (`_apply_slug_strategy`) before persisting it as `entity_slug`, so a
> `[[Title Case]]` / `[[Идеи]]` link resolves to its target page's slug by
> construction. `identity` (karpathy) is a verbatim no-op → byte-identity
> preserved (golden anchor green). Verified: the obsidian-personal dogfood vault's
> `[[Идеи]]` orphan dropped to 0; layout-matrix test
> `tests/test_ref_slugify_resolution.py` locks identity/transliterate/
> preserve-unicode/ascii-only. `cited`/`verifies` refs (explicit frontmatter slugs)
> are untouched.

- **Symptom**: In a vault whose layout uses a non-`identity` `slug_strategy`
  (`preserve-unicode` for `obsidian-personal`, `transliterate` for `dev-project`),
  a wikilink whose text is not already in slugified form does **not** resolve to
  its (existing) target page. `wiki-lint` reports it as a **false-positive
  `orphan-link`**, and the link is invisible to alias/graph resolution. Example
  (dogfood, obsidian-personal): page `02 - Areas/Идеи.md` indexes with slug `идеи`
  (preserve-unicode lowercases); a `[[Идеи]]` wikilink in another note stores the
  target verbatim as `Идеи` and is flagged orphan, while a `[[идеи]]` (already
  slug-form) resolves. Obsidian links are normally Title-/display-cased and may
  contain spaces (`[[draft idea]]` → slug `draft-idea`), so in practice **most**
  intra-vault links in these layouts fail to resolve.
- **Root cause**: ref extraction (`scripts/wiki_source/parsing.py::extract_refs`)
  stores the raw wikilink target; neither extraction nor resolution applies the
  page's `slug_strategy`. Page slugs ARE slugified (lowercase + separator +
  unicode-preserve/transliterate), so the two sides only match when the link text
  is coincidentally already slug-form. `karpathy` escapes this because its
  `slug_strategy: identity` keeps the verbatim stem, so verbatim link text matches
  verbatim slugs — which is why the bug was invisible until the `dev-project` /
  `obsidian-personal` layouts (TASK 012) shipped non-identity strategies.
- **Affected components**: `scripts/wiki_source/parsing.py` (`extract_refs` /
  `derive_slug` / `_apply_slug_strategy`), `scripts/wiki_index/reindex.py` (where
  refs are persisted), `scripts/wiki_index/sqlite_repository.py::find_orphan_links`
  (the resolution join). Affects 2 of 3 built-in layouts (`dev-project`,
  `obsidian-personal`); contributes to this repo's own dev-vault orphan-link noise.
- **Scope / impact**: correctness — breaks the link graph (orphan detection,
  alias-aware resolution, any future `wiki-graph`) for non-identity layouts. Not a
  data-loss bug (pages + raw refs are intact); the defect is in *matching*.
- **Fix options (deferred — pick when a non-identity-layout vault is in real use)**:
  1. **Slugify the ref target at extraction time** using the layout's
     `slug_strategy` (store the normalized target in `page_entity_refs.entity_slug`),
     so it matches the page-slug derivation by construction. Cleanest; mirrors how
     page slugs are derived. Must use the SAME strategy the target page used.
  2. **Normalize both sides at resolution time** — slugify the target in the
     `find_orphan_links` / `resolve_entity` joins. Avoids a reindex-format change
     but pushes slugify into every query.
  Option 1 preferred (normalize once, on the write path). Mind: a bare link
  `[[Идеи]]` can't know the *target's* project, so resolution stays project-agnostic
  on slug (today's behaviour); the collision case (same slug, two projects) is a
  pre-existing ambiguity orthogonal to this fix.
- **Workaround (today)**: author intra-vault wikilinks in already-slugified form
  (lowercase, hyphen-separated) in `dev-project`/`obsidian-personal` vaults; or use
  the `karpathy` layout (identity slugs) where verbatim links resolve. `wiki-lint`
  orphan-link counts for these layouts are inflated by this bug — treat with
  caution until fixed.
- **Prevention**: a layout-matrix link-resolution test (assert `[[Title Case]]`
  resolves to its slug under each `slug_strategy`) would have caught this; add it
  with the fix.
