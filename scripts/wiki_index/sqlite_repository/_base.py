"""Connection/base layer of the SQLite DAL package (TASK 056).

Owns everything every domain mixin needs: the lazy sqlite3 connection +
PRAGMA block, the context-manager lifecycle, the runtime DDL path, the two
DAL exception classes, and the genuinely cross-domain stateless helper
`_in_clause` (used by `_search` and `_events`).

`SQLiteRepositoryBase` is ABSTRACT — it inherits `IndexRepository` so that
public cross-mixin calls (e.g. `check_drift → get_vault`) type-check against
the ABC, and it is never instantiated directly; only the composite
`SQLiteRepository` in `__init__.py` is.

dialect: SQLite-only — the PRAGMA block (WAL / synchronous / foreign_keys /
temp_store / mmap_size) and the `user_version`-bearing DDL in `_SCHEMA_PATH`
have no portable equivalent; a future `postgres_repository/` base owns a
psycopg pool + `SET`-style session config instead.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from types import TracebackType
from typing import Self

from scripts.wiki_index.repository import IndexRepository

_SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "sql"
    / "wiki-index-v2.sql"
)
"""Runtime DDL — apply via `apply_schema()` or external `sqlite3 db < ...`."""


class VaultRegistrationError(RuntimeError):
    """Raised on vault PK collision (duplicate vault_id) or UNIQUE violation
    (duplicate root_path). Wraps the underlying sqlite3.IntegrityError with a
    user-facing message."""


class AliasCollisionError(RuntimeError):
    """Raised by `add_alias` when the surface already resolves to a *different*
    entity (the hard `(vault_id, alias)` PK, TASK 005 / R-5.1). Carries the
    conflicting canonical slug so the CLI can name it in the error envelope —
    the slug is a safe kebab identifier, NOT the operator-supplied surface (so
    the CWE-117/209 never-echo-content invariant holds)."""

    def __init__(self, conflicting_slug: str) -> None:
        super().__init__(f"alias already resolves to entity {conflicting_slug!r}")
        self.conflicting_slug = conflicting_slug


class SQLiteRepositoryBase(IndexRepository):
    """Abstract root of the SQLite DAL: connection state + lifecycle.

    Domain mixins inherit this (directly, or transitively via a declared
    dependency edge) and reach the DB exclusively through `self._connect()`.
    """

    def __init__(self, db_path: Path) -> None:
        """Store the db_path. Does NOT open a connection — deferred to the
        first method that needs one via `_connect()` (lazy)."""
        self.db_path: Path = db_path
        self._conn: sqlite3.Connection | None = None

    # =========================================================================
    # Connection management (task-001-15)
    # =========================================================================

    def _connect(self) -> sqlite3.Connection:
        """Lazy-open the SQLite connection and apply pragmas. Idempotent."""
        if self._conn is not None:
            return self._conn
        conn = sqlite3.connect(self.db_path, isolation_level=None)
        # Apply pragmas documented in sql/wiki-index-v2.sql §0
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA temp_store = MEMORY")
        conn.execute("PRAGMA mmap_size = 268435456")
        conn.row_factory = sqlite3.Row
        self._conn = conn
        return conn

    def close(self) -> None:
        """Close the underlying connection if open. Idempotent."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> Self:
        self._connect()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

    def apply_schema(self) -> None:
        """Apply the v2 DDL to the underlying DB. Idempotent (uses CREATE
        TABLE IF NOT EXISTS in the DDL). Intended for fresh-init flows + tests."""
        conn = self._connect()
        with open(_SCHEMA_PATH, "r", encoding="utf-8") as f:
            conn.executescript(f.read())

    # =========================================================================
    # Shared helpers (cross-domain, stateless)
    # =========================================================================

    @staticmethod
    def _in_clause(column: str, values: list[str]) -> tuple[str, list[str]]:
        """Safe IN-clause string with `?` placeholders. Returns
        `(sql_fragment, params_list)`. Avoids SQL injection from joins."""
        placeholders = ",".join("?" * len(values))
        return f"{column} IN ({placeholders})", list(values)
