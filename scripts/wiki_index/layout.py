"""Vault layout constants — single source of truth for directory/file names.

Consumed by:
- reindex.discover_pages / find_pages_missing_in_index / check_drift (page dirs)
- wiki_init scaffolding (full scaffold dir set)
- wiki_migrate_flat_to_folders (system-file allowlist)
- logfile rotation (log dir)

If the on-disk vault convention ever changes (e.g. renaming `_sources` →
`_pages`), edit ONLY this file. Tests assert that callers import these names
rather than literal-stringing them.
"""

from __future__ import annotations

# Page-bearing subdirectories under a vault root or course directory.
# Walked by discover_pages, drift checks, and CLI render counts.
PAGE_SUBDIRS: tuple[str, ...] = ("_sources", "_concepts", "_entities")

# Top-level course tier directory name (per ADR-002 §D6).
COURSE_TIER_DIR: str = "Lessons"

# Vault-index directory (holds log/ and index.md). One per vault root and
# per course directory.
VAULT_INDEX_DIR: str = "00-Vault-Index"

# Sub-directory of VAULT_INDEX_DIR that holds monthly log.md files.
LOG_SUBDIR: str = "log"

# Full scaffold dir set created by wiki-init --scaffold-new. Superset of
# PAGE_SUBDIRS plus the operational/log layout.
SCAFFOLD_DIRS: tuple[str, ...] = (
    *PAGE_SUBDIRS,
    "_raw",
    "_raw/.locks",
    "_raw/failed",
    VAULT_INDEX_DIR,
    f"{VAULT_INDEX_DIR}/{LOG_SUBDIR}",
)

# System files (always at vault root; never moved by migrations).
SYSTEM_FILES: frozenset[str] = frozenset({
    "WIKI_SCHEMA.md", "CLAUDE.md", "log.md", "index.md",
})

# Sentinel vault_id for cross-vault CLI operations (search/lint/reindex
# without a specific --vault). See ADR-002 §D1.1.
GLOBAL_VAULT_SENTINEL: str = "_global_"
