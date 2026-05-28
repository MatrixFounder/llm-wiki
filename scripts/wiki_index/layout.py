"""Vault layout constants — single source of truth for directory/file names.

Consumed by every skill that touches vault filesystem paths or that writes
the `pages.project` column. If the on-disk vault convention ever changes
(e.g. renaming `_sources` → `_pages`, or `WIKI_SCHEMA.md` →
`WIKI_SCHEMA.yaml`), edit ONLY this file. Tests assert that callers
import these names rather than literal-stringing them.

Future plan (see ROADMAP.md): vault-level layout customisation will move
into a per-vault `WIKI_SCHEMA.md` (or `.yaml`) config so different
vault flavours (Karpathy / dev-project / obsidian-personal per R-X1)
can override these defaults without recompiling. Until then, all
callers should depend on these module-level constants; that gives the
future migration a single chokepoint to swap from constant-loaded to
schema-loaded values.
"""

from __future__ import annotations

# Page-bearing subdirectory NAMES (sit under a vault root or course root).
# Named individually so callers can be self-documenting; PAGE_SUBDIRS
# below preserves the tuple form for code that iterates them.
SOURCES_SUBDIR: str = "_sources"
CONCEPTS_SUBDIR: str = "_concepts"
ENTITIES_SUBDIR: str = "_entities"
RAW_SUBDIR: str = "_raw"

# Page-bearing subdirectories under a vault root or course directory.
# Walked by discover_pages, drift checks, and CLI render counts.
PAGE_SUBDIRS: tuple[str, ...] = (
    SOURCES_SUBDIR, CONCEPTS_SUBDIR, ENTITIES_SUBDIR,
)

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
    RAW_SUBDIR,
    f"{RAW_SUBDIR}/.locks",
    f"{RAW_SUBDIR}/failed",
    VAULT_INDEX_DIR,
    f"{VAULT_INDEX_DIR}/{LOG_SUBDIR}",
)

# Per-vault schema marker file. Presence at the vault root (or at a
# `Lessons/<Course>/` root) is how config-discovery identifies a vault.
SCHEMA_FILE: str = "WIKI_SCHEMA.md"

# System files (always at vault root; never moved by migrations).
SYSTEM_FILES: frozenset[str] = frozenset({
    SCHEMA_FILE, "CLAUDE.md", "log.md", "index.md",
})

# Sentinel value for `pages.project` when a page lives at the vault root
# (vault-tier), i.e. NOT inside any `Lessons/<Course>/`. Course-tier
# pages carry the slugified course-directory name instead. The DEFAULT
# clause on `pages.project` in the schema also uses this literal —
# changing it requires a schema migration.
VAULT_TIER_PROJECT: str = "_vault_"

# Sentinel `vault_id` for cross-vault CLI operations (search/lint/reindex
# without a specific --vault). See ADR-002 §D1.1. Distinct from
# VAULT_TIER_PROJECT (different column, different semantics).
GLOBAL_VAULT_SENTINEL: str = "_global_"
