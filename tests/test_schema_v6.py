"""TASK 032-00 — schema v5→v6 (R-032-1): admit the inverse-closed typed-edge
ref_types for the event graph (ADR-004 D1).

- PRAGMA user_version == 7 (TASK 034: v6→v7)
- page_entity_refs.ref_type CHECK admits the 6 new edge values (rejects bogus)
- relates_to reuses the existing `related` (NO parallel `relates-to`)
- a POPULATED table carrying the OLD v5 CHECK rejects a v6-only ref_type
  (AC-1.3 — proves the Class-B drop+recreate rebuild is mandatory)
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

_SCHEMA = Path(__file__).resolve().parent.parent / "sql" / "wiki-index-v2.sql"
_NEW = ["implements", "implemented-by", "supersedes", "superseded-by", "causes", "caused-by"]


def _fresh(tmp_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "v6.db")
    conn.executescript(_SCHEMA.read_text(encoding="utf-8"))
    return conn


def test_user_version_is_6(tmp_path: Path) -> None:
    assert _fresh(tmp_path).execute("PRAGMA user_version").fetchone()[0] == 7


@pytest.mark.parametrize("rt", _NEW)
def test_ref_type_accepts_new_edges(tmp_path: Path, rt: str) -> None:
    conn = _fresh(tmp_path)
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute(
        "INSERT INTO page_entity_refs (vault_id, page_slug, page_project, "
        "entity_slug, ref_type) VALUES ('v','a','_vault_','b',?)", (rt,))
    assert conn.execute("SELECT ref_type FROM page_entity_refs").fetchone()[0] == rt


def test_ref_type_rejects_bogus(tmp_path: Path) -> None:
    conn = _fresh(tmp_path)
    conn.execute("PRAGMA foreign_keys = OFF")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO page_entity_refs (vault_id, page_slug, page_project, "
            "entity_slug, ref_type) VALUES ('v','a','_vault_','b','not-a-ref')")


def test_relates_to_reuses_existing_related(tmp_path: Path) -> None:
    """ADR-004 D1: NO parallel `relates-to` value — `relates_to` reuses `related`."""
    conn = _fresh(tmp_path)
    conn.execute("PRAGMA foreign_keys = OFF")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO page_entity_refs (vault_id, page_slug, page_project, "
            "entity_slug, ref_type) VALUES ('v','a','_vault_','b','relates-to')")
    conn.execute(  # but `related` is accepted
        "INSERT INTO page_entity_refs (vault_id, page_slug, page_project, "
        "entity_slug, ref_type) VALUES ('v','a','_vault_','b','related')")


def test_populated_v5_rejects_v6_ref_type(tmp_path: Path) -> None:
    """AC-1.3: a populated table carrying the OLD 5-value CHECK rejects a v6-only
    ref_type. SQLite cannot ALTER-relax a CHECK on a populated table, so a bare
    `wiki-reindex --full` against an un-dropped v5 DB CANNOT pick up the new edge
    kinds → the Class-B drop+recreate rebuild is MANDATORY (ADR-002 §D8 / TASK 008)."""
    conn = sqlite3.connect(tmp_path / "old.db")
    conn.execute(  # reconstruct the OLD v5 CHECK inline (the live schema file is now v6)
        "CREATE TABLE page_entity_refs (vault_id TEXT, page_slug TEXT, "
        "page_project TEXT, entity_slug TEXT, ref_type TEXT CHECK (ref_type IN "
        "('mentioned','defined-here','related','cited','verifies')), "
        "PRIMARY KEY (vault_id, page_slug, page_project, entity_slug, ref_type))")
    conn.execute("INSERT INTO page_entity_refs VALUES ('v','a','_vault_','b','mentioned')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO page_entity_refs VALUES ('v','a','_vault_','c','implements')")
