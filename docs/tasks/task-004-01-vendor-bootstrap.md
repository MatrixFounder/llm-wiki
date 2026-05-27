# Task 004-01: Bootstrap `scripts/wiki_ingest/` package + `VENDORED_FROM.md` skeleton [STUB CREATION]

## Meta

- **Bead ID**: `task-004-01-vendor-bootstrap`
- **Slug**: `vendor-bootstrap`
- **Maps to**: Issue **I-V.1**; RTM rows **R-45**
- **Depends on**: none (entry point of the task)
- **Estimated time**: 0.5 day
- **Priority**: Critical (blocks every other bead in TASK 004)

## Use Case Connection

- **UC-V1**: Operator updates vendored snapshot via sync script (this bead creates the *initial* snapshot the script will later refresh).
- **UC-V2**: End-user installs via single command (this bead lands the directory the in-process import depends on).

## Task Goal

Create the vendored `scripts/wiki_ingest/` directory by copying the Python package from `Universal-skills/skills/wiki-ingest/scripts/wiki_ingest/` (manually via `rsync`/`cp -R` since `sync_wiki_ingest.sh` doesn't exist yet — that's I-V.2). Write a `VENDORED_FROM.md` provenance file recording the source commit SHA, sync timestamp, source path, and per-file SHA256 hashes. Verify `from scripts.wiki_ingest.commands.ingest import execute` succeeds from the repo's `.venv`. This is a **pre-refactor snapshot**: the package still contains the upstream `execute(args)` entry point and no `ingest()` function yet (I-V.3 lands that).

## Stub-First Plan

**Phase 1 — Stub**:
1. Create empty `scripts/wiki_ingest/__init__.py` with just `__version__ = "1.1.0"  # snapshot version`.
2. Create empty `scripts/wiki_ingest/commands/__init__.py`.
3. Write `tests/test_vendored_import.py::test_vendored_import_stub` — asserts `from scripts.wiki_ingest import __version__` succeeds and equals `"1.1.0"`. This test passes on the empty skeleton.

**Phase 2 — Logic**:
1. Manually `rsync -av --exclude=__pycache__ --exclude='*.pyc' ../../Universal-skills/skills/wiki-ingest/scripts/wiki_ingest/ scripts/wiki_ingest/` (or `cp -R` if rsync unavailable).
2. Compute upstream SHA: `(cd ../../Universal-skills && git rev-parse HEAD)` (record output as `source_commit`).
3. Compute per-file SHA256 hashes for every `*.py` in `scripts/wiki_ingest/` (binary read mode; output as `file_hashes` block in `VENDORED_FROM.md`).
4. Write `scripts/wiki_ingest/VENDORED_FROM.md` with the format below (see "New Files" section).
5. Update `tests/test_vendored_import.py::test_vendored_import_stub` → `test_vendored_import` asserting `from scripts.wiki_ingest.commands.ingest import execute` succeeds (the upstream entry point, not yet `ingest`).

## Changes Description

### New Files

- `scripts/wiki_ingest/` (directory; entire upstream package contents minus `__pycache__/`):
  - `__init__.py`, `_classify.py`, `_dispatch.py`, `_frontmatter.py`, `_markdown.py`, `_page_merge.py`, `_safety.py`, `_vault.py`
  - `commands/__init__.py`, `commands/append_log.py`, `commands/classify_folder.py`, `commands/demote.py`, `commands/find.py`, `commands/ingest.py` (still upstream form), `commands/init.py`, `commands/lint.py`, `commands/log_event.py`, `commands/promote.py`, `commands/reindex.py`, `commands/register_summary.py`, `commands/scan.py`, `commands/update_index.py`, `commands/upsert_page.py`
- `scripts/wiki_ingest/VENDORED_FROM.md` — provenance metadata. Format:
  ```markdown
  # Vendored From

  This directory is a snapshot of `Universal-skills/skills/wiki-ingest/scripts/wiki_ingest/`.
  Do **NOT** edit files here directly — fixes must land upstream first, then sync via
  `bash scripts/sync_wiki_ingest.sh`.

  - **source_path**: `Universal-skills/skills/wiki-ingest/scripts/wiki_ingest/`
  - **source_commit**: `<40-char-git-SHA>`  (or `"non-git"` if upstream isn't a git checkout)
  - **synced_at**: `<ISO-8601 timestamp with Z suffix>`

  ## file_hashes

  | path | sha256 |
  |---|---|
  | `__init__.py` | `<64-hex>` |
  | `_classify.py` | `<64-hex>` |
  | ... (one row per committed `*.py` file) |

  ## local_patches

  _(empty until I-V.4 mypy fixups land; each entry will record path + reason + upstream issue link)_
  ```
- `tests/test_vendored_import.py` — single sanity test that the package is importable.

### Changes in Existing Files

- `.gitignore` — verify `__pycache__/` and `*.pyc` are already excluded (project-wide rule, should be no-op).

### Component Integration

- This bead **does not** wire `wiki_enrich.py` to the vendored copy yet — that's I-V.5. After this bead, the vendored directory simply *exists* and is importable.
- The vendored `commands/ingest.py` is still in its upstream form (no `ingest()` function, no `IngestError`). I-V.3 refactors it.

## Files Touched (explicit list)

- `scripts/wiki_ingest/` (new directory, ~22 files copied from upstream)
- `scripts/wiki_ingest/VENDORED_FROM.md` (new)
- `tests/test_vendored_import.py` (new)

## Test Surface

- **New**: `tests/test_vendored_import.py` (1 test: `test_vendored_import_succeeds`)

## Acceptance

- [ ] R-45(a): `scripts/wiki_ingest/__init__.py` exists and is importable from the repo's Python path (`python -c "from scripts.wiki_ingest import __version__"` exits 0).
- [ ] R-45(b): `scripts/wiki_ingest/commands/` subdirectory present with all subcommand modules listed in TASK.md §5.2 (15+ files).
- [ ] R-45(c): No `__pycache__/` present in the committed copy (`git status` shows no `__pycache__` tracked).
- [ ] R-45(d): `scripts/wiki_ingest/VENDORED_FROM.md` exists with `source_commit`, `synced_at`, `source_path`, and `file_hashes` fields populated.
- [ ] R-45(e): `from scripts.wiki_ingest.commands.ingest import execute` succeeds in the repo's `.venv` (note: `ingest` is NOT yet importable — that's I-V.3).
- [ ] `pytest tests/test_vendored_import.py -v` passes (1 test).
- [ ] All previous 295+ tests still pass (no regression from the new directory's presence).

## Rollback

`rm -rf scripts/wiki_ingest/ tests/test_vendored_import.py` and `git checkout .gitignore`. No other repo file is touched, so this bead is fully isolated and trivially reversible.

## Notes

- The `local_patches` block in `VENDORED_FROM.md` will be empty at the end of this bead. I-V.4 (mypy strict) is the first bead expected to add entries.
- File-hash format choice (SHA256, binary mode, no normalization) is fixed here because I-V.2's divergence-check depends on the exact format. Document the hashing convention as a comment in `VENDORED_FROM.md` itself so I-V.2 implementation reads it from one source of truth.
- The Universal-skills repo path is **read-only** in this bead — `git status` in that repo must remain clean (R-57 invariant).
