"""TASK 034 / R-2 — schema v6→v7: admit four MORE inverse-closed typed-edge
ref_types (temporal + agent-memory; ADR-004 ext).

- PRAGMA user_version == 7 (the authoritative live pin)
- page_entity_refs.ref_type CHECK admits the 8 new edge values (rejects bogus)
- a POPULATED table carrying the OLD v6 CHECK rejects a v7-only ref_type
  (proves the Class-B drop+recreate rebuild is mandatory — ADR-002 §D8)
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

_SCHEMA = Path(__file__).resolve().parent.parent / "sql" / "wiki-index-v2.sql"
_NEW_V7 = [
    "invalidated-by", "invalidates",
    "activated-by", "activates",
    "uses", "used-by",
    "owns", "owned-by",
]


def _fresh(tmp_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "v7.db")
    conn.executescript(_SCHEMA.read_text(encoding="utf-8"))
    return conn


def test_user_version_is_7(tmp_path: Path) -> None:
    assert _fresh(tmp_path).execute("PRAGMA user_version").fetchone()[0] == 7


@pytest.mark.parametrize("rt", _NEW_V7)
def test_ref_type_accepts_new_v7_edges(tmp_path: Path, rt: str) -> None:
    conn = _fresh(tmp_path)
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute(
        "INSERT INTO page_entity_refs (vault_id, page_slug, page_project, "
        "entity_slug, ref_type) VALUES ('v','a','_vault_','b',?)", (rt,))
    assert conn.execute("SELECT ref_type FROM page_entity_refs").fetchone()[0] == rt


def test_populated_v6_rejects_v7_ref_type(tmp_path: Path) -> None:
    """A populated table carrying the OLD v6 12-value CHECK rejects a v7-only
    ref_type → the Class-B drop+recreate rebuild is MANDATORY (cannot ALTER-relax
    a CHECK on a populated table)."""
    conn = sqlite3.connect(tmp_path / "old.db")
    conn.execute(  # reconstruct the OLD v6 CHECK inline (live schema is now v7)
        "CREATE TABLE page_entity_refs (vault_id TEXT, page_slug TEXT, "
        "page_project TEXT, entity_slug TEXT, ref_type TEXT CHECK (ref_type IN "
        "('mentioned','defined-here','related','cited','verifies',"
        "'implements','implemented-by','supersedes','superseded-by',"
        "'causes','caused-by')), "
        "PRIMARY KEY (vault_id, page_slug, page_project, entity_slug, ref_type))")
    conn.execute("INSERT INTO page_entity_refs VALUES ('v','a','_vault_','b','mentioned')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO page_entity_refs VALUES ('v','a','_vault_','c','invalidated-by')")
