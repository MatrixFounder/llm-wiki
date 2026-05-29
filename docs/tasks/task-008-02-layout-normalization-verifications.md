# Task 008-02: layout + normalization — `_verifications` discoverable AND type-mapped

> The load-bearing half of the §D8 spine (Arch M-1 / TASK-007-C-1 lesson):
> `layout.py` alone is **insufficient** — without the `TYPE_MAPPING` addition the
> verdict page is found by `discover_pages` but raises `UnmappedTypeError` and is
> silently skipped on reindex, so R-8.5e (008-03) never runs and UC-26 fails.

## Use Case Connection
- UC-25: Compounding (a verdict page is discoverable + searchable).
- UC-26: Durability round-trip (the page must be **indexed**, not skipped, for the `verifies` ref to round-trip).

## Task Goal
Make `_verifications/` a first-class page-bearing subdir via the **R-X1-forward role-split** (the second `HOST_ONLY_SUBDIRS` member after `_queries`), and map `type=verification` so `normalize_frontmatter` accepts it. This is **R-8.5** and parts 1+2 of the three-part durability spine.

## Changes Description

### Changes in Existing Files

#### File: `scripts/wiki_index/layout.py`
- Add `VERIFICATIONS_SUBDIR: str = "_verifications"` (next to `QUERIES_SUBDIR`).
- Add it to `HOST_ONLY_SUBDIRS` → `HOST_ONLY_SUBDIRS = (QUERIES_SUBDIR, VERIFICATIONS_SUBDIR)`. This flows automatically into `PAGE_SUBDIRS = (*INGEST_SHARED_SUBDIRS, *HOST_ONLY_SUBDIRS)` (so `discover_pages`/drift/render walk it) and into `SCAFFOLD_DIRS` (so `wiki-init --scaffold-new` creates it). **Do not** add a literal `"_verifications"` anywhere else — every caller imports the constant (C-8/NFR-7 chokepoint).

#### File: `scripts/wiki_index/normalization.py`
- `TYPE_MAPPING`: add `"verification": ("verification", None)`.
- `_PATH_TYPE_FALLBACK`: add `VERIFICATIONS_SUBDIR: "verification"` (import the constant from `layout`; defensive type inference for a verdict page missing an explicit `type:`).

### Component Integration
After this bead a hand-authored `_verifications/v.md` (`type: verification`) is discovered by `discover_pages`, normalises without `UnmappedTypeError`, and (given 008-01's schema) would index as `type=verification`. The `verifies:` → `'verifies'` ref read-side is 008-03; this bead only makes the page *indexable*.

## Test Cases

### End-to-end Tests
1. **TC-E2E-01 (discoverable):** a fixture vault with `_verifications/v.md` → `discover_pages` yields it (it is in `PAGE_SUBDIRS`).
2. **TC-E2E-02 (scaffold):** `wiki-init --scaffold-new` creates a `_verifications/` directory (`SCAFFOLD_DIRS` membership).

### Unit Tests
1. **TC-UNIT-01:** `normalize_frontmatter({"type":"verification", ...})` → `db_type == "verification"`, no `UnmappedTypeError`.
2. **TC-UNIT-02:** `_infer_type_from_path("_verifications/x.md")` (or the path-fallback fn) → `"verification"`.
3. **TC-UNIT-03 (chokepoint):** `VERIFICATIONS_SUBDIR == "_verifications"` and `VERIFICATIONS_SUBDIR in HOST_ONLY_SUBDIRS and in PAGE_SUBDIRS`.

### Regression Tests
- `_queries` and the ingest-shared subdirs (`_sources`/`_concepts`/`_entities`) are unchanged; `tests/test_layout_invariants.py` (the vendored byte-equality `INGEST_SHARED_SUBDIRS` test) stays green — `_verifications` joins `HOST_ONLY_SUBDIRS`, not `INGEST_SHARED_SUBDIRS`.
- `TYPE_MAPPING` for existing types unchanged.

## Acceptance Criteria
- [ ] `VERIFICATIONS_SUBDIR` added to `HOST_ONLY_SUBDIRS` (→ `PAGE_SUBDIRS` + `SCAFFOLD_DIRS` membership) with no literal `"_verifications"` outside `layout.py`.
- [ ] `TYPE_MAPPING["verification"] = ("verification", None)` + `_PATH_TYPE_FALLBACK[VERIFICATIONS_SUBDIR] = "verification"`.
- [ ] `discover_pages` finds a `_verifications/` page; `normalize_frontmatter` accepts `type: verification`.
- [ ] `test_layout_invariants.py` + all existing layout/normalization tests green; `mypy --strict` clean.

## Notes
Declarative — no logic; single-pass. Depends on 008-01 (so the indexed `type` is schema-valid). This is the bead the arch-review M-1 flagged as easy to forget; it is intentionally its own atomic, separately-tested unit.
