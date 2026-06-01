# Task 012-06: PW-F — frontmatter synthesis (title fallback chain)

## Use Case Connection
- UC-29: Karpathy type-less file STILL raises `UnmappedTypeError` (synthesis off — byte-identical).
- UC-30: an Obsidian note with NO frontmatter indexes (title = first H1 ∥ filename stem).

## Task Goal
When a file has no YAML frontmatter and the layout's `frontmatter_synthesis.enabled` is true,
synthesise a minimal `{type: <path-inferred>, title: <H1 ∥ stem>}` so frontmatter-less Obsidian
notes index without the operator editing every file (PW-F). Karpathy keeps `enabled: false`.

## Changes Description

### Changes in Existing Files

#### File: `scripts/wiki_source/parsing.py`
- Add `synthesize_frontmatter(fm: dict, body: str, path: Path, synthesis: dict, *, inferred_type: str | None) -> dict`:
  - if `fm` is non-empty OR `synthesis.get("enabled")` is false → return `fm` unchanged;
  - else build `{"type": inferred_type, "title": <first H1 in body> or <path.stem>}` per
    `title_source: first_h1` → `fallback_title: filename_stem`.
- A small `_first_h1(body) -> str | None` helper (`^#\s+(.+)$`, first match).
- **Do NOT** synthesise inside `parse_frontmatter` (kept generic); apply `synthesize_frontmatter`
  in the reindex normalize path where the `LayoutConfig` + path-inferred type are available.

#### File: `scripts/wiki_index/reindex.py`
- In the page-rebuild: after `parse_frontmatter`, if the frontmatter is empty, call
  `synthesize_frontmatter(...)` with `config.frontmatter_synthesis` + the path-inferred type
  (from the matched `PathEntry.type` / `path_type_fallback`) before `normalize_frontmatter`.

### Changes in Test Files
#### File: `tests/test_frontmatter_synthesis.py` (NEW)
- Karpathy (`enabled: false`): a `_concepts/x.md` with NO frontmatter → reindex still raises
  `UnmappedTypeError` (today's contract; 012-00 green).
- obsidian-personal (`enabled: true`): a note with `# My Heading` + no frontmatter → indexed,
  `title == "My Heading"`, type = path-inferred (`note`).
- A note with no H1 and no frontmatter → `title == <filename stem>`.

## Acceptance Criteria
- ✅ Karpathy type-less behaviour unchanged (`UnmappedTypeError`); 012-00 green.
- ✅ obsidian-personal frontmatter-less notes index with H1∥stem title.
- ✅ `mypy --strict` clean; full suite green.

## Stub-First
Phase 1: `synthesize_frontmatter` returns `fm` unchanged (no-op) → karpathy path identical.
Phase 2: the H1∥stem synthesis + wiring + the obsidian tests (RED against the no-op stub).
