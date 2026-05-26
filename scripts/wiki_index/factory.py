"""Factory: sole public entry point to the DAL.

Skill code MUST go through `make_repo(config)` — never construct
`SQLiteRepository(...)` directly. This is what lets us swap backends
(Postgres future, Epic 8) and what hosts the cross-cutting validations:

  - ADR-002 §D1.1 vault_id REQUIRED check (wired in task-001-20)
  - R-03 iCloud-rejection (wired in task-001-14)
  - Backend selection from config (currently SQLite-only; opt-in Postgres later)

Phase 3a stub: ignores `config`, returns a `SQLiteRepository` pointing at a
hardcoded `/tmp/wiki-stub.db` so downstream skill code compiles. Real
config-driven instantiation is task-001-20.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any

from scripts.wiki_index.repository import IndexRepository
from scripts.wiki_index.sqlite_repository import SQLiteRepository

# M-6 fix: pinned regex (no heuristics). Matches both `iCloud~md~obsidian` and
# `com~apple~CloudDocs` containers — Apple's two canonical iCloud path prefixes
# under `Mobile Documents/`.
_ICLOUD_RE = re.compile(r"/Mobile Documents/(iCloud~|com~apple~)")


class ICloudRejectionError(RuntimeError):
    """Raised when an attempted DB path lies inside an iCloud-managed directory.

    iCloud byte-syncs binary files, which corrupts SQLite WAL/shm pairs across
    devices (see docs/SQLITE-VS-POSTGRES.md §5). The factory MUST refuse to
    open a DB at such a path. Real detection arrives in task-001-14; this
    class shape is final.
    """


def _is_icloud_path(p: Path) -> bool:
    """True iff `p` (after resolution) lies inside an iCloud-managed
    `Mobile Documents/` container. M-6 fix: pinned regex avoids drift from
    "looks iCloud-y" heuristics. iCloud byte-syncs binary files, which
    corrupts SQLite WAL/shm pairs across devices — see SQLITE-VS-POSTGRES.md §5."""
    return bool(_ICLOUD_RE.search(str(p.resolve(strict=False))))


def _resolve_db_path(vault_id: str, platform: str | None = None) -> Path:
    """Platform-default location for the global multi-vault DB.

    Per ADR-002 §D1: ONE `global.db` serves all vaults via vault_id
    partitioning. `vault_id` is accepted for forward-compat (future per-vault
    opt-out flag) but currently ignored — same `global.db` is returned
    regardless. Parent directory is created if missing.
    """
    _ = vault_id  # accepted for forward-compat; same global.db for all
    if platform is None:
        platform = sys.platform
    if platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / "wiki-index" / "global.db"
    elif platform == "linux":
        path = Path.home() / ".local" / "share" / "wiki-index" / "global.db"
    elif platform == "win32":
        appdata = os.environ.get("APPDATA")
        if not appdata:
            raise RuntimeError("APPDATA env var not set on Windows")
        path = Path(appdata) / "wiki-index" / "global.db"
    else:
        raise RuntimeError(f"Unsupported platform: {platform}")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def validate_db_path(p: Path) -> None:
    """Raise `ICloudRejectionError` if `p` lies inside an iCloud container.

    Hosts the cross-cutting R-03 guard: SQLite must never live in iCloud
    because WAL/shm pairs corrupt across multi-device sync.
    """
    if _is_icloud_path(p):
        raise ICloudRejectionError(
            f"DB path {p} is inside an iCloud container — iCloud byte-syncs "
            f"binary files which corrupts SQLite WAL/shm pairs across devices. "
            f"Use --db-path <custom> to override with a non-iCloud location."
        )


_VAULT_ID_RE = re.compile(r"^[a-z][a-z0-9-]{1,30}[a-z0-9]$")


class ConfigValidationError(ValueError):
    """ADR-002 §D1.1 fail-fast on vault_id at factory level.

    Second line of defense (first: config_loader JSON Schema; third: SQLite
    CHECK constraint)."""


def _validate_vault_id(vault_id: Any) -> str:
    if not vault_id or not isinstance(vault_id, str):
        raise ConfigValidationError(
            "vault_id REQUIRED (ADR-002 §D1.1 — no hash fallback)"
        )
    v: str = vault_id
    if v == "_global_":
        return v
    if not _VAULT_ID_RE.match(v):
        raise ConfigValidationError(
            f"vault_id={v!r} does not match ^[a-z][a-z0-9-]{{1,30}}[a-z0-9]$"
        )
    if "--" in v:
        raise ConfigValidationError(f"vault_id={v!r} contains double hyphen")
    return v


def apply_schema_if_missing(db_path: Path) -> None:
    """Apply v2 DDL if `db_path` is absent or zero-bytes. Idempotent."""
    if db_path.exists() and db_path.stat().st_size > 0:
        return
    schema_path = (
        Path(__file__).resolve().parent.parent.parent / "sql" / "wiki-index-v2.sql"
    )
    db_path.parent.mkdir(parents=True, exist_ok=True)
    import sqlite3 as _sqlite3
    conn = _sqlite3.connect(db_path)
    try:
        conn.executescript(schema_path.read_text(encoding="utf-8"))
    finally:
        conn.close()


def make_repo(config: dict[str, Any]) -> IndexRepository:
    """Construct and return a ready repository for the given config.

    Steps (ADR-002 §D1.1 + R-03):
      1. Validate `config['vault_id']` — REQUIRED + format check.
      2. Resolve `db_path` from `config.get('db_path')` override or platform
         default via `_resolve_db_path`.
      3. Reject iCloud paths via `validate_db_path`.
      4. Apply schema if DB file doesn't exist.
      5. Return `SQLiteRepository(db_path)` (connection deferred to first
         method call).
    """
    vault_id = _validate_vault_id(config.get("vault_id"))
    db_path_override = config.get("db_path")
    if db_path_override is not None:
        db_path = Path(db_path_override)
    else:
        db_path = _resolve_db_path(vault_id, sys.platform)
    # iCloud rejection BEFORE any filesystem mutation
    validate_db_path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    apply_schema_if_missing(db_path)
    return SQLiteRepository(db_path)
