"""TASK 006-01 — schema v3→v4 hygiene invariants (still hold under v5).

Validates the runtime DDL (`sql/wiki-index-v2.sql`) directly. NOTE: the live
`user_version` advanced to 5 in TASK 008 (R-8.9); the authoritative version pin
lives in `test_schema_v5.py`. The v4-era invariants below persist unchanged:
- PRAGMA user_version == 6 (bumped: TASK 008 v5, TASK 032 v6)
- idx_pages_vault_tags dropped (P-5)
- log_events.event_date is a STORED generated column == substr(event_ts,1,10) (L-2)
- pages.type CHECK has no 'log' value (L-5 — already absent; guard)
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

_SCHEMA = Path(__file__).resolve().parent.parent / "sql" / "wiki-index-v2.sql"


def _fresh(tmp_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "v4.db")
    conn.executescript(_SCHEMA.read_text(encoding="utf-8"))
    return conn


def test_user_version_is_4(tmp_path: Path) -> None:
    # TASK 008 / R-8.9 bumped the live schema to v5; the v4-era hygiene
    # invariants below (idx drop, generated event_date, no 'log' type) still hold.
    assert _fresh(tmp_path).execute("PRAGMA user_version").fetchone()[0] == 6


def test_idx_pages_vault_tags_dropped(tmp_path: Path) -> None:
    idx = {r[0] for r in _fresh(tmp_path).execute(
        "SELECT name FROM sqlite_master WHERE type='index'").fetchall()}
    assert "idx_pages_vault_tags" not in idx          # P-5
    assert "idx_log_vault_date" in idx                # still indexes the generated col


def test_event_date_is_generated(tmp_path: Path) -> None:
    """L-2: event_date is computed from event_ts; the inserter must NOT supply it."""
    conn = _fresh(tmp_path)
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute(
        "INSERT INTO log_events (vault_id, event_ts, event_type, "
        "pages_created_json, pages_touched_json, details_json) "
        "VALUES ('v', '2026-05-29T10:30:00+00:00', 'reindex', '[]', '[]', '{}')")
    assert conn.execute("SELECT event_date FROM log_events").fetchone()[0] == "2026-05-29"


def test_event_date_rejects_explicit_insert(tmp_path: Path) -> None:
    """Inserting a value for the generated column is an error (proves it's generated)."""
    conn = _fresh(tmp_path)
    conn.execute("PRAGMA foreign_keys = OFF")
    with pytest.raises(sqlite3.Error):  # "cannot INSERT into generated column" (OperationalError)
        conn.execute(
            "INSERT INTO log_events (vault_id, event_ts, event_date, event_type, "
            "pages_created_json, pages_touched_json, details_json) "
            "VALUES ('v', '2026-05-29T10:30:00+00:00', '2020-01-01', 'reindex', '[]', '[]', '{}')")


def test_pages_type_has_no_log_value(tmp_path: Path) -> None:
    """L-5 (already-resolved guard): the dead 'log' page type stays rejected."""
    conn = _fresh(tmp_path)
    conn.execute("PRAGMA foreign_keys = OFF")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO pages (vault_id, slug, project, type, title, file_path, "
            "last_modified) VALUES ('v','x','_vault_','log','X','x.md','2026-05-29')")
