# 032-01 — `_edge_refs` forward extraction

**Owns:** AC-2.1/2.2. **Dep:** 032-00. **Detail:** PLAN.md §2 / ADR-004 D2/D3.

## Scope
Extract the authored edge keys into `page_entity_refs` (FORWARD only; M-1 intact — unioned into the page's single `replace_refs`).

## Files
- `scripts/wiki_index/reindex.py` — NEW `_edge_refs(updated_fm, vault_id, page_slug, page_project, skipped)`: per the key→ref_type map (`implements`→`implements`, `implemented_by`→`implemented-by`, `supersedes`→`supersedes`, `superseded_by`→`superseded-by`, `causes`→`causes`, `caused_by`→`caused-by`, `relates_to`→`related`), list+scalar, target `[[wikilink]]`/slug resolved via `slug_strategy`+alias (same path as `_body_refs`); de-dup `(entity_slug, ref_type)`; report-and-skip malformed (no value echo). Called **always-on** in `_frontmatter_refs` (`:197`), NOT db_type-gated.

## Stub-First (RED → GREEN)
Pin the key→ref_type map; `decision` page with `implements: [[req-x]]` + scalar `caused_by: inc-y` → 2 forward refs (resolved slugs); directly-authored `superseded_by:` → `superseded-by`. **Karpathy anchor green** (no edge keys → `[]`).

## Verify
`mypy --strict`; `test_karpathy_byte_identity.py` green.
