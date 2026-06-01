# Task 012-02: PW-B/J/K/M — config-driven discover_pages + iter_pages engine

## Use Case Connection
- UC-29: byte-identical Karpathy (012-00 stays green).
- UC-30: obsidian-personal vault (deep hierarchy, system dirs, `.base` exclusion, project derivation).
- UC-34: project_pattern/template error policy (A3).

## Task Goal
Replace the hardcoded two-tier walk with a **config-driven `iter_pages`** engine
(PW-B), add `ignore[]` (PW-K) + `file_extensions` (PW-M) + `project` derivation
(PW-J), and **converge the un-converged walk** (architecture-review C1). The highest-risk
bead — run under `skill-tdd-strict` with 012-00 as the tripwire.

## Changes Description

### Changes in Existing Files

#### File: `scripts/wiki_index/layout_config.py`
- `iter_pages(vault_root: Path, config: LayoutConfig) -> list[tuple[Path, str, str]]`:
  - For each `PathEntry` in declared order, `Path(vault_root).glob(entry.glob)`; **first
    match wins** (a file matched by an earlier entry is not re-emitted).
  - **PW-K:** skip anything matching `config.ignore[]` (recursive `**` via a `fnmatch`-on-
    relative-POSIX matcher), evaluated BEFORE `paths[]`. **Also skip `layout.py::SYSTEM_FILES`
    and every `config.auto_indexes[].output`** (architecture-review m1 — no schema/config
    scoop, no render→ingest feedback loop).
  - **PW-M:** only files whose suffix ∈ `config.file_extensions`.
  - **PW-J:** derive `project` = `entry.project` literal, or from `entry.project_pattern`
    (compiled regex) match on the vault-relative POSIX path + `string.Template(entry.project_template).substitute(...)`,
    optionally slugified per `entry.project_slug_strategy`. Error policy:
    regex-compile-fail (caught at 012-01 schema-load where possible, else here) → `LayoutConfigError`/exit-6;
    glob matches but pattern misses → `logger.warning("[unmatched-pattern] %s", rel)` +
    `project = "_unmatched_"`; template references a group the pattern didn't produce →
    `LayoutConfigError`/exit-6.
  - Slug derivation is delegated to 012-05's `slug_strategy`; **for this bead use `identity`
    (path.stem)** so karpathy stays byte-identical (012-05 generalises it).
  - **Stable canonical sort by vault-relative POSIX path** before return (NFR-5).

#### File: `scripts/wiki_index/reindex.py`
- Rewrite `discover_pages(vault_root)` (65-88) to: load the vault's `root_config`
  (via `config_loader`) + `load_layout_config`, then `return iter_pages(vault_root, config)`.
  **Signature unchanged** (callers — `reindex_full`, `reindex_delta`, `check_drift` —
  untouched). Cache the config per `vault_root`.

#### File: `scripts/wiki_index/sqlite_repository.py`  ← architecture-review C1
- `find_pages_missing_in_index` (526-549): **delete the inline `PAGE_SUBDIRS`+`Lessons/`
  walk**; route through `discover_pages(vault_root)`; compare membership on
  **`(slug, project)`** against the DB's `(slug, project)` set — **not bare `f.stem`**
  (fixes the latent slug-only course-tier false-negative). `check_drift` already delegates;
  leave it.

### New Test Fixture

#### Dir: `tests/fixtures/obsidian-personal-vault/` (NEW)
- A Cyrillic note (`02 - Personal Home/Квартиры.md`); 3 same-named files under different
  `<area>/<sub>/` (`02 - Personal Home/Household/intake.md`, `02 - Personal Home/Purchases/intake.md`,
  `03 - Work/Z/intake.md`); an `_inbox/draft.md`; an `.obsidian/workspace.json`; an ignored
  `01 - Inbox (base).base`; a `.DS_Store`. (Bodies minimal; this fixture also feeds 012-05/06/07.)
- A throwaway `obsidian-personal` `.wiki/layout.yaml` OR rely on the built-in shipped in 012-07;
  for 012-02 a minimal inline config in the test is acceptable to exercise `iter_pages` directly.

### Changes in Test Files

#### File: `tests/test_discover_pages_engine.py` (NEW)
- `test_discover_pages_is_path_sorted`: output is sorted by relative POSIX path (C-5 pin).
- `test_ignore_skips_obsidian_and_base`: `.obsidian/` + `.base` + `.DS_Store` not emitted.
- `test_file_extensions_allowlist`: a `.canvas` file not emitted.
- `test_project_pattern_deep_hierarchy`: the 3 `intake.md` files → 3 distinct `project`s,
  **no PK collision** on `reindex_full`.
- `test_project_pattern_miss_warns_and_unmatched`: a file matching the glob but not the
  pattern → `project == "_unmatched_"` + a logged warning.
- `test_system_files_and_autoindex_output_excluded`: a root `WIKI_SCHEMA.md`/`README.md`
  and an `auto_indexes[].output` target are not emitted (m1).
- `test_find_pages_missing_uses_slug_project`: a course-tier page sharing a stem with a
  vault-tier page is **not** falsely reported present (C1 regression).
- **012-00 golden snapshot must stay green.**

## Acceptance Criteria
- ✅ 012-00 byte-identity snapshot green (karpathy via `iter_pages`).
- ✅ obsidian-personal fixture: 3 same-named files → 3 projects, no PK collision; `.base`/`.obsidian`/`.DS_Store` excluded.
- ✅ `find_pages_missing_in_index` compares on `(slug, project)`; the C1 regression test passes.
- ✅ project_pattern miss → `_unmatched_` + warning; output stably sorted.
- ✅ `mypy --strict` clean.

## Stub-First (`skill-tdd-strict`)
Phase 1: `iter_pages` returns the same result as the current hardcoded walk for karpathy
(route-through, behaviour unchanged) → 012-00 green. Phase 2: add ignore/ext/project_pattern/
sort + the obsidian fixture tests + the C1 convergence (each RED-first against the stub).
