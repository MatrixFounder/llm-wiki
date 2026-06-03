# task-018-11 — [LOGIC] own bounded walk

**Parent:** TASK 018. **Depends on:** 018-10, 018-04 (config). **RTM:** E3.1e, EC-1/ID-5, SEC-A6, W-2.

## Goal
Discover heterogeneous zone files cheaply and safely; the only-`.md`-in-exclude-zone read rule.

## Design (locked)
Mirror `iter_pages`' discipline (free string/glob filters → **one `stat()` per surviving
candidate** → case-folded extension prune *before* any read) but over the wiki-sync extension
set. Honest read-cost (W-2): scan still reads file bytes later (in 13) to hash — bounded because
zones are scoped + binaries skipped pre-read.

## Steps
1. Walk `zone` recursively; for each entry: cheap string filters first; **exclude**
   `_raw/.staging/**`, `_raw/.locks`, `_raw/failed`, and `config.exclude` globs.
   `exclude:`-matched **non-`.md`** are pruned immediately; `exclude:`-matched **`.md`** are
   still yielded (so `#wiki/keep` can rescue them) with `in_exclude_zone=True`.
2. One `stat()` per surviving candidate (derive is-file + `mtime`); set `in_raw` from the `_raw/`
   prefix (excluding `.staging/`). Refuse symlinked dirs AND target files (`O_NOFOLLOW` posture).
3. GREEN: `test_walk_discovers_heterogeneous`; `test_walk_excludes_staging` (a
   `_raw/.staging/x-docx.md` is NOT yielded); `test_walk_one_stat_per_file` (stat-count spy);
   `test_walk_reads_md_in_exclude_zone` (a `.md` under an `exclude:` zone IS yielded).

## Verification
- `pytest -q -k walk` GREEN; `mypy --strict` clean.
