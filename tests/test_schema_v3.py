"""TASK 005-01 — schema v2→v3 migration (entity_aliases PK fix, L-4 closure).

Validates the runtime DDL (`sql/wiki-index-v2.sql`) directly:
- `PRAGMA user_version == 3`
- `entity_aliases` PK is `(vault_id, alias)` — one alias → exactly one entity
  (the collision insert that the OLD `(vault_id, alias, entity_slug)` PK
  permitted is now rejected; this is the RED→GREEN proof of the migration).
- `idx_aliases_entity` added, `idx_aliases_lookup` dropped.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "sql" / "wiki-index-v2.sql"


def _fresh_db(tmp_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "v3.db")
    conn.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))
    return conn


def test_user_version_is_3(tmp_path: Path) -> None:
    conn = _fresh_db(tmp_path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 3


def test_alias_pk_rejects_same_alias_two_slugs(tmp_path: Path) -> None:
    """v3 PK (vault_id, alias) → one alias resolves to exactly one entity.

    The OLD PK (vault_id, alias, entity_slug) would have allowed the second
    insert (different entity_slug); under v3 it is an IntegrityError. L-4 closed.
    """
    conn = _fresh_db(tmp_path)
    conn.execute("PRAGMA foreign_keys = OFF")  # focus on PK, not the entities FK
    conn.execute(
        "INSERT INTO entity_aliases(vault_id, alias, entity_slug, alias_type) "
        "VALUES ('v', 'Hermes', 'hermes-agent', 'spelling_variant')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO entity_aliases(vault_id, alias, entity_slug, alias_type) "
            "VALUES ('v', 'Hermes', 'hermes-bus', 'spelling_variant')"
        )


def test_alias_index_swap(tmp_path: Path) -> None:
    conn = _fresh_db(tmp_path)
    indexes = {
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index'"
        ).fetchall()
    }
    assert "idx_aliases_entity" in indexes
    assert "idx_aliases_lookup" not in indexes


def test_same_alias_different_vault_allowed(tmp_path: Path) -> None:
    """PK is scoped by vault_id — the same alias in two vaults is fine."""
    conn = _fresh_db(tmp_path)
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute(
        "INSERT INTO entity_aliases(vault_id, alias, entity_slug, alias_type) "
        "VALUES ('v1', 'Hermes', 'hermes-agent', 'spelling_variant')"
    )
    conn.execute(
        "INSERT INTO entity_aliases(vault_id, alias, entity_slug, alias_type) "
        "VALUES ('v2', 'Hermes', 'hermes-agent', 'spelling_variant')"
    )  # no error
    n = conn.execute("SELECT COUNT(*) FROM entity_aliases").fetchone()[0]
    assert n == 2
