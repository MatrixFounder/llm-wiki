"""TASK 008-01 — schema v4→v5 (R-8.9): admit the verification page type,
the `verifies` ref-type, and the `verify` log event for `wiki-verify-multi`.

Validates the runtime DDL (`sql/wiki-index-v2.sql`) directly:
- PRAGMA user_version == 7 (TASK 032: v5→v6; TASK 034: v6→v7)
- pages.type CHECK admits 'verification' (rejects bogus)
- page_entity_refs.ref_type CHECK admits 'verifies' (rejects bogus)
- log_events.event_type CHECK admits 'verify'
- index_meta view includes type='verification' rows (catalog parity with 'query')
- pages_fts triggers index a verification page (no type filter → FTS-searchable)
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

_SCHEMA = Path(__file__).resolve().parent.parent / "sql" / "wiki-index-v2.sql"


def _fresh(tmp_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "v5.db")
    conn.executescript(_SCHEMA.read_text(encoding="utf-8"))
    return conn


def _insert_page(conn: sqlite3.Connection, slug: str, ptype: str) -> None:
    conn.execute(
        "INSERT INTO pages (vault_id, slug, project, type, title, file_path, "
        "last_modified, file_hash, frontmatter_json) "
        "VALUES ('v', ?, '_vault_', ?, ?, ?, '2026-05-29', 'h', '{}')",
        (slug, ptype, slug, f"_verifications/{slug}.md"),
    )


def test_user_version_is_5(tmp_path: Path) -> None:
    assert _fresh(tmp_path).execute("PRAGMA user_version").fetchone()[0] == 7


def test_pages_type_accepts_verification(tmp_path: Path) -> None:
    conn = _fresh(tmp_path)
    _insert_page(conn, "v-q1", "verification")  # must NOT raise
    assert conn.execute(
        "SELECT type FROM pages WHERE slug='v-q1'").fetchone()[0] == "verification"


def test_pages_type_rejects_bogus(tmp_path: Path) -> None:
    conn = _fresh(tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        _insert_page(conn, "x", "not-a-real-type")


def test_ref_type_accepts_verifies(tmp_path: Path) -> None:
    conn = _fresh(tmp_path)
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute(
        "INSERT INTO page_entity_refs (vault_id, page_slug, page_project, "
        "entity_slug, ref_type) VALUES ('v', 'v-q1', '_vault_', 'q1', 'verifies')")
    assert conn.execute(
        "SELECT ref_type FROM page_entity_refs").fetchone()[0] == "verifies"


def test_ref_type_rejects_bogus(tmp_path: Path) -> None:
    conn = _fresh(tmp_path)
    conn.execute("PRAGMA foreign_keys = OFF")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO page_entity_refs (vault_id, page_slug, page_project, "
            "entity_slug, ref_type) VALUES ('v', 'a', '_vault_', 'b', 'not-a-ref')")


def test_event_type_accepts_verify(tmp_path: Path) -> None:
    conn = _fresh(tmp_path)
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute(
        "INSERT INTO log_events (vault_id, event_ts, event_type, "
        "pages_created_json, pages_touched_json, details_json) "
        "VALUES ('v', '2026-05-29T10:30:00+00:00', 'verify', '[]', '[]', '{}')")
    assert conn.execute(
        "SELECT event_type FROM log_events").fetchone()[0] == "verify"


def test_index_meta_includes_verification(tmp_path: Path) -> None:
    conn = _fresh(tmp_path)
    _insert_page(conn, "v-q1", "verification")
    kinds = {r[0] for r in conn.execute(
        "SELECT kind FROM index_meta WHERE slug='v-q1'").fetchall()}
    assert "verification" in kinds  # catalog parity with 'query'


def test_verification_page_is_fts_searchable(tmp_path: Path) -> None:
    """The pages_fts triggers index every row regardless of type — so a
    verification page is FTS-searchable the moment the CHECK admits it."""
    conn = _fresh(tmp_path)
    conn.execute(
        "INSERT INTO pages (vault_id, slug, project, type, title, file_path, "
        "last_modified, file_hash, frontmatter_json, body_excerpt) "
        "VALUES ('v', 'v-q1', '_vault_', 'verification', 'Verdict for q1', "
        "'_verifications/v-q1.md', '2026-05-29', 'h', '{}', 'hermes routing audit')")
    hits = conn.execute(
        "SELECT slug FROM pages_fts WHERE pages_fts MATCH 'hermes'").fetchall()
    assert ("v-q1",) in hits
