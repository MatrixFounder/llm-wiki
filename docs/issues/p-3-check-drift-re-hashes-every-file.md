---
id: P-3
type: known-issue
status: open
opened_at: 2026-05-26
category: performance
slug: p-3-check-drift-re-hashes-every-file
---

# check_drift re-hashes every file

- **Symptom**: `SQLiteRepository.check_drift` reads + sha256-hashes every page on disk, plus `yaml.safe_load` on each frontmatter for type-mismatch detection. At 10k pages → wiki-lint 30 s SLO at risk.
- **Root cause**: No mtime/size short-circuit; PyYAML safe_load is slow.
- **Affected components**: `scripts/wiki_index/sqlite_repository.py:check_drift`.
- **Fix plan**: Compare `os.stat().st_mtime + st_size` against stored `last_modified` first; only re-hash on mismatch. Replace PyYAML with regex fast-path for `^type:\s*(\S+)`. Stream hashing via `hashlib.file_digest`.
