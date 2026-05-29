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
QUERIES_SUBDIR: str = "_queries"
VERIFICATIONS_SUBDIR: str = "_verifications"
RAW_SUBDIR: str = "_raw"

# Subdirs shared with the vendored wiki-ingest file-synthesis layer
# (`scripts/wiki_ingest/_vault.DEFAULT_SUBDIRS`). The vendored ingest module
# produces ONLY these page kinds (source / concept / entity). These MUST stay
# byte-identical to the vendored copy — §7.4 Vendoring Policy (upstream-first
# on any rename); `tests/test_layout_invariants.py` guards the equality.
INGEST_SHARED_SUBDIRS: tuple[str, ...] = (
    SOURCES_SUBDIR, CONCEPTS_SUBDIR, ENTITIES_SUBDIR,
)

# Host-only page-bearing subdirs the wiki-ingest synthesis layer does NOT
# produce. `_queries` (TASK 007 / R-6): RAG answer pages written by
# `wiki-query`. `_verifications` (TASK 008 / R-8): multi-critic verdict pages
# written by `wiki-verify-multi`. The vendored ingest snapshot legitimately
# knows nothing about these (they are not raw-source synthesis output), so they
# are NOT part of the INGEST_SHARED_SUBDIRS contract.
#
# Forward note (ROADMAP R-X1 "universalise layout engine"): the shared-vs-
# host-only split modelled here is the seam R-X1 will fold into the per-vault
# layout config (`karpathy.yaml` / `dev-project.yaml` / ...). Until then this
# is the explicit chokepoint; new host-only page subdirs join this tuple
# (`_verifications` is the second member, proving the seam generalises).
HOST_ONLY_SUBDIRS: tuple[str, ...] = (
    QUERIES_SUBDIR,
    VERIFICATIONS_SUBDIR,
)

# All page-bearing subdirectories under a vault root or course directory —
# the host superset = wiki-ingest-shared subdirs + host-only subdirs.
# Walked by discover_pages, drift checks, and CLI render counts.
PAGE_SUBDIRS: tuple[str, ...] = (
    *INGEST_SHARED_SUBDIRS, *HOST_ONLY_SUBDIRS,
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
