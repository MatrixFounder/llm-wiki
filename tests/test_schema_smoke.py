"""
Smoke test for sql/wiki-index-v2.sql (task-001-01).

Validates that the runtime DDL applies cleanly to a fresh SQLite database and
that the architectural invariants encoded in the schema (PRAGMA user_version,
vault_id CHECK constraint, FTS5 trigger sync, M-6 dead-index suppression) hold.

Covers TC-E2E-01, TC-E2E-02, TC-UNIT-01, TC-UNIT-02, TC-UNIT-03 from task-001-01.

Deviation from task spec: TC-UNIT-01 in the planner output mentions
`entities_fts` table — this is a planner hallucination (the schema has only
`pages_fts`). The test checks only the tables that actually exist per
docs/SCHEMA-v2.sql §11.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

SCHEMA_PATH = Path(__file__).parent.parent / "sql" / "wiki-index-v2.sql"


@pytest.fixture
def db(tmp_path):
    """Fresh SQLite DB with the v2 schema applied + standard pragmas.

    Returns the open connection. Caller is responsible for closing — pytest
    handles teardown via tmp_path cleanup, but the connection itself should be
    closed by the test (or rely on garbage collection at scope exit).
    """
    db_path = tmp_path / "wiki-test.db"
    conn = sqlite3.connect(db_path)
    # PRAGMAs that schema header documents (set at connection time, not in DDL)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_PATH.read_text())
    yield conn
    conn.close()


# =============================================================================
# TC-E2E-01 — schema applies cleanly and required pragmas/user_version match
# =============================================================================


def test_e2e_01_schema_applies_and_pragmas(db):
    """Schema applies; ≥10 tables, ≥1 view; WAL + foreign_keys + user_version=7."""
    n_tables = db.execute(
        "SELECT count(*) FROM sqlite_master WHERE type='table'"
    ).fetchone()[0]
    n_views = db.execute(
        "SELECT count(*) FROM sqlite_master WHERE type='view'"
    ).fetchone()[0]

    assert n_tables >= 10, f"expected ≥10 user tables, got {n_tables}"
    assert n_views >= 1, f"expected ≥1 view, got {n_views}"

    assert db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    # M-5 fix — must be set unconditionally by the DDL (§13.2).
    # v3 (TASK 005 / R-5.4): entity_aliases PK swap → 3.
    # v4 (TASK 006): drop idx_pages_vault_tags + event_date GENERATED → 4.
    # v5 (TASK 008 / R-8.9): verification type + verifies ref + verify event → 5.
    # v6 (TASK 032): event-graph typed edges → 6. v7 (TASK 034): temporal + agent-memory edges → 7.
    assert db.execute("PRAGMA user_version").fetchone()[0] == 7


# =============================================================================
# TC-E2E-02 — M-6 fix: out-of-MVP table indexes NOT created
# =============================================================================


def test_e2e_02_no_indexes_on_out_of_mvp_tables(db):
    """No indexes on interactions / extracted_items — deferred to Epic 6/7."""
    n_dead = db.execute(
        """
        SELECT count(*) FROM sqlite_master
         WHERE type='index'
           AND tbl_name IN ('interactions', 'extracted_items')
           AND name NOT LIKE 'sqlite_autoindex_%'
        """
    ).fetchone()[0]
    assert n_dead == 0, (
        f"M-6 fix violation: {n_dead} non-autoindex indexes exist on "
        f"interactions/extracted_items. They should be commented out in "
        f"sql/wiki-index-v2.sql until Epic 6/7 activation."
    )

    # Tables themselves MUST exist (forward-compat for Epic 6/7).
    interactions_exists = db.execute(
        "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='interactions'"
    ).fetchone()[0]
    items_exists = db.execute(
        "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='extracted_items'"
    ).fetchone()[0]
    assert interactions_exists == 1
    assert items_exists == 1


# =============================================================================
# TC-UNIT-01 — required tables present
# =============================================================================


REQUIRED_TABLES = (
    "vaults",
    "entities",
    "entity_aliases",
    "pages",
    "page_entity_refs",
    "log_events",
    "interactions",
    "extracted_items",
    "batch_runs",
    "source_state",
    "schema_meta",
    "pages_fts",  # FTS5 virtual table
)


@pytest.mark.parametrize("table", REQUIRED_TABLES)
def test_unit_01_required_table_exists(db, table):
    """Each required table is present in sqlite_master."""
    row = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    assert row is not None, f"table {table!r} missing"


REQUIRED_VIEWS = ("v_vault_stats", "index_meta", "known_concepts", "v_concept_cooccurrence")


@pytest.mark.parametrize("view", REQUIRED_VIEWS)
def test_unit_01b_required_view_exists(db, view):
    """Each required view is present in sqlite_master."""
    row = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='view' AND name=?",
        (view,),
    ).fetchone()
    assert row is not None, f"view {view!r} missing"


# =============================================================================
# TC-UNIT-02 — vault_id CHECK constraint
# =============================================================================


@pytest.mark.parametrize(
    "bad_vault_id, reason",
    [
        ("ab", "too short (2 chars)"),
        ("1bad", "leading digit"),
        ("AB", "uppercase + too short"),
        ("Trade-Agents", "uppercase letter"),
        ("foo--bar", "double hyphen"),
        ("trade-agents-", "trailing hyphen"),
        ("-trade-agents", "leading hyphen"),
        ("a" * 33, "exceeds 32-char length cap"),
    ],
)
def test_unit_02_vault_id_check_rejects_malformed(db, bad_vault_id, reason):
    """vault_id CHECK constraint rejects malformed identifiers."""
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        db.execute(
            "INSERT INTO vaults(vault_id, name, root_path, schema_version, "
            "registered_at) VALUES (?, ?, ?, ?, ?)",
            (bad_vault_id, "n", f"/tmp/{bad_vault_id}-{reason}", "2.0", "2026-05-26T00:00:00Z"),
        )
    db.rollback()


@pytest.mark.parametrize("good_vault_id", ["_global_", "trade-agents", "abc", "a1b", "a-b-c"])
def test_unit_02b_vault_id_accepts_valid(db, good_vault_id):
    """vault_id CHECK accepts well-formed kebab-case + the _global_ sentinel."""
    db.execute(
        "INSERT INTO vaults(vault_id, name, root_path, schema_version, "
        "registered_at) VALUES (?, ?, ?, ?, ?)",
        (good_vault_id, "n", f"/tmp/{good_vault_id}", "2.0", "2026-05-26T00:00:00Z"),
    )
    db.commit()


# =============================================================================
# TC-UNIT-03 — FTS5 triggers sync pages → pages_fts
# =============================================================================


def _seed_vault(db, vault_id="trade-agents"):
    db.execute(
        "INSERT INTO vaults(vault_id, name, root_path, schema_version, registered_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (vault_id, "Test", f"/tmp/{vault_id}-{id(db)}", "2.0", "2026-05-26T00:00:00Z"),
    )


def test_unit_03a_fts_insert_trigger(db):
    """INSERT into pages indexes the row in pages_fts (via pages_fts_ai trigger)."""
    _seed_vault(db)
    db.execute(
        "INSERT INTO pages(vault_id, slug, project, type, title, file_path, tldr, "
        "date, last_modified, file_hash, frontmatter_json, body_excerpt) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "trade-agents",
            "hermes-agent",
            "_vault_",
            "concept",
            "Hermes Agent",
            "_concepts/hermes-agent.md",
            "Self-learning",
            "2026-05-25",
            "2026-05-25T10:00:00Z",
            "abc",
            '{"tags":["agent","trading"]}',
            "self-learning autonomous trading framework",
        ),
    )
    db.commit()
    hit_count = db.execute(
        "SELECT count(*) FROM pages_fts WHERE pages_fts MATCH ? AND vault_id=?",
        ("autonomous", "trade-agents"),
    ).fetchone()[0]
    assert hit_count == 1


def test_unit_03b_fts_update_trigger_removes_stale_tokens(db):
    """UPDATE pages.body_excerpt removes stale FTS tokens (H-1 fix)."""
    _seed_vault(db)
    db.execute(
        "INSERT INTO pages(vault_id, slug, project, type, title, file_path, tldr, "
        "date, last_modified, file_hash, frontmatter_json, body_excerpt) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "trade-agents",
            "hermes-agent",
            "_vault_",
            "concept",
            "Hermes",
            "_concepts/hermes-agent.md",
            "Self-learning",
            "2026-05-25",
            "2026-05-25T10:00:00Z",
            "abc",
            '{}',
            "self-learning autonomous framework",
        ),
    )
    db.commit()
    db.execute(
        "UPDATE pages SET body_excerpt=?, file_hash=? "
        "WHERE vault_id=? AND slug=? AND project=?",
        ("completely different quantum mechanics content", "xyz", "trade-agents", "hermes-agent", "_vault_"),
    )
    db.commit()
    # H-1 invariant: old token gone
    stale = db.execute(
        "SELECT count(*) FROM pages_fts WHERE pages_fts MATCH ?",
        ("autonomous",),
    ).fetchone()[0]
    assert stale == 0, "stale FTS token leaked across UPDATE"
    # New token present
    fresh = db.execute(
        "SELECT count(*) FROM pages_fts WHERE pages_fts MATCH ?",
        ("quantum",),
    ).fetchone()[0]
    assert fresh == 1


def test_unit_03c_fts_delete_trigger(db):
    """DELETE FROM pages cascades to pages_fts (via pages_fts_ad trigger)."""
    _seed_vault(db)
    db.execute(
        "INSERT INTO pages(vault_id, slug, project, type, title, file_path, tldr, "
        "date, last_modified, file_hash, frontmatter_json, body_excerpt) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "trade-agents",
            "hermes-agent",
            "_vault_",
            "concept",
            "Hermes",
            "_concepts/hermes-agent.md",
            "Self-learning",
            "2026-05-25",
            "2026-05-25T10:00:00Z",
            "abc",
            '{}',
            "body about hermes",
        ),
    )
    db.commit()
    assert db.execute("SELECT count(*) FROM pages_fts").fetchone()[0] == 1
    db.execute("DELETE FROM pages WHERE vault_id=? AND slug=?", ("trade-agents", "hermes-agent"))
    db.commit()
    assert db.execute("SELECT count(*) FROM pages_fts").fetchone()[0] == 0


# =============================================================================
# Bonus: CASCADE rename verifies multi-vault partitioning (ADR-002 §D8 reconcile)
# =============================================================================


def test_bonus_cascade_rename_propagates(db):
    """UPDATE vaults.vault_id CASCADEs to pages, entities, page_entity_refs."""
    _seed_vault(db, "trade-agents")
    db.execute(
        "INSERT INTO entities(vault_id, slug, type, name, first_seen, last_updated, file_path) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("trade-agents", "sharpe", "concept", "Sharpe", "2026-05-25T10:00:00Z", "2026-05-25T10:00:00Z", "_concepts/sharpe.md"),
    )
    db.execute(
        "INSERT INTO pages(vault_id, slug, project, type, title, file_path, tldr, "
        "date, last_modified, file_hash, frontmatter_json, body_excerpt) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "trade-agents",
            "hermes",
            "_vault_",
            "concept",
            "Hermes",
            "_concepts/hermes.md",
            "",
            "2026-05-25",
            "2026-05-25T10:00:00Z",
            "abc",
            '{}',
            "body",
        ),
    )
    db.execute(
        "INSERT INTO page_entity_refs(vault_id, page_slug, page_project, entity_slug, ref_type) "
        "VALUES (?, ?, ?, ?, ?)",
        ("trade-agents", "hermes", "_vault_", "sharpe", "mentioned"),
    )
    db.commit()
    # Rename
    db.execute(
        "UPDATE vaults SET vault_id=?, root_path=? WHERE vault_id=?",
        ("trading-research", "/new", "trade-agents"),
    )
    db.commit()
    # All FK rows must have cascaded
    assert db.execute("SELECT vault_id FROM pages WHERE slug='hermes'").fetchone()[0] == "trading-research"
    assert db.execute("SELECT vault_id FROM entities WHERE slug='sharpe'").fetchone()[0] == "trading-research"
    assert db.execute("SELECT vault_id FROM page_entity_refs").fetchone()[0] == "trading-research"
