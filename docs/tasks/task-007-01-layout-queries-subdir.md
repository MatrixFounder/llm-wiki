# Task 007-01: `layout.py` — register the `_queries/` page-bearing subdir

## Use Case Connection
- UC-19: Compounding — a later search finds a prior answer (needs query pages discoverable).
- UC-20: Durability round-trip (query pages must be walked by `discover_pages` to round-trip).

## Task Goal
Make `_queries/` a first-class page-bearing subdirectory so that query pages written by `wiki-query apply` are discovered by `discover_pages` (reindex/drift/render walk it), created by `wiki-init --scaffold-new`, and type-inferred when frontmatter omits `type:`. This is **structural change #1** (RTM R-6.5); it blocks the reindex read-side (007-02) and the apply write target (007-05/06).

## Changes Description

### Changes in Existing Files

#### File: `scripts/wiki_index/layout.py`
- Add a module constant `QUERIES_SUBDIR: str = "_queries"` (next to `SOURCES_SUBDIR`/`CONCEPTS_SUBDIR`/`ENTITIES_SUBDIR`).
- Add `QUERIES_SUBDIR` to the `PAGE_SUBDIRS` tuple (so `discover_pages`, drift checks, and render counts walk it).
- Add `QUERIES_SUBDIR` to `SCAFFOLD_DIRS` (so `wiki-init --scaffold-new` creates `<vault>/_queries/`).

#### File: `scripts/wiki_index/normalization.py`
- Add `QUERIES_SUBDIR: "query"` to `_PATH_TYPE_FALLBACK` (defensive: a `_queries/x.md` page missing an explicit `type:` infers `query`). Import `QUERIES_SUBDIR` from `layout` (do not literal-string it — `layout.py` is the single source of truth).

### Component Integration
`PAGE_SUBDIRS` is consumed by `discover_pages` ([reindex.py:69](../../scripts/wiki_index/reindex.py)); adding `_queries` makes query pages part of the full-reindex walk. `SCAFFOLD_DIRS` is consumed by `wiki-init`. `_PATH_TYPE_FALLBACK` is consumed by `normalize_frontmatter` via `_infer_type_from_path`.

## Test Cases

### Unit Tests
1. **TC-UNIT-01:** `QUERIES_SUBDIR == "_queries"` and `QUERIES_SUBDIR in PAGE_SUBDIRS` and `in SCAFFOLD_DIRS`.
2. **TC-UNIT-02:** `_infer_type_from_path(Path(".../_queries/foo.md")) == "query"`.
3. **TC-UNIT-03:** `normalize_frontmatter({}, source_path=Path(".../_queries/foo.md"))` returns `db_type == "query"` (path-fallback applies when `type:` absent).

### End-to-end Tests
1. **TC-E2E-01:** `discover_pages(vault_root)` over a fixture vault containing `_queries/q.md` yields `(path, "q", "_vault_")` in its output (previously absent). Course-tier `Lessons/<C>/_queries/` is also walked.
2. **TC-E2E-02:** `wiki-init --scaffold-new --vault tmp --vault-root <tmp>` creates a `_queries/` directory.

### Regression Tests
- Run all existing tests from `tests/` — `discover_pages` / scaffold / normalization tests must stay green; adding `_queries` is purely additive (an absent/empty `_queries/` dir yields no pages).

## Acceptance Criteria
- [ ] `QUERIES_SUBDIR` added to `layout.py`; present in `PAGE_SUBDIRS` + `SCAFFOLD_DIRS`.
- [ ] `_PATH_TYPE_FALLBACK["_queries"] == "query"` (importing the constant, not a literal).
- [ ] `discover_pages` walks `_queries/` at both vault and course tiers.
- [ ] `wiki-init --scaffold-new` creates `_queries/`.
- [ ] Full `pytest tests/` green; `mypy --strict scripts/` clean.

## Notes
Single-pass (declarative constants) — no Stub-First two-phase split needed, but the Phase-1 RED test (TC-E2E-01 failing before the constant is added) demonstrates the gap. Zero schema change. This bead is the prerequisite for 007-02's round-trip.
