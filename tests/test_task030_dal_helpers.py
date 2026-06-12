"""TASK 030 bead 030-02 (R-030-2a) — private txn-free DML helpers on
`SQLiteRepository`.

Zero-behavior-change refactor: the DML bodies of `upsert_page`/`replace_refs`
move into `_upsert_page_in_txn`/`_replace_refs_in_txn`; the public methods keep
their own-tx semantics by delegating (M-4 untouched, ABC untouched).

AC-2.2 mechanical oracle: the PUBLIC methods still raise `OperationalError`
inside an externally-opened transaction (own-tx preserved), while the private
helpers operate INSIDE that open transaction.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest

from scripts.wiki_index.models import Page, PageRef, Vault
from scripts.wiki_index.repository import IndexRepository
from scripts.wiki_index.sqlite_repository import SQLiteRepository


@pytest.fixture
def repo(tmp_path: Path) -> Iterator[SQLiteRepository]:
    r = SQLiteRepository(tmp_path / "g.db")
    r.apply_schema()
    r.register_vault(Vault(vault_id="dal-helpers", name="t", root_path=tmp_path,
                           schema_version="2.0",
                           registered_at=datetime(2026, 5, 1)))
    yield r
    r.close()


def _page(slug: str = "p1", body: str = "body", path: str = "n/p1.md") -> Page:
    return Page(
        vault_id="dal-helpers", slug=slug, project="_vault_", type="summary",
        title=slug.upper(), file_path=path, date=None,
        last_modified=datetime(2026, 6, 1), file_hash=f"hash-{body}",
        frontmatter_json={"type": "summary", "title": slug.upper()},
        body_excerpt=body, tags=[], tldr=None,
    )


def _ref(slug: str = "p1", target: str = "t1", line: int = 1,
         quote: str = "q") -> PageRef:
    return PageRef(
        vault_id="dal-helpers", page_slug=slug, page_project="_vault_",
        entity_slug=target, ref_type="mentioned", line_start=line, line_end=line,
        source_quote=quote, trust_level="medium",
    )


# --------------------------------------------------------------------------- #
# AC-2.2 — own-tx semantics of the PUBLIC methods preserved (pin, green today)
# --------------------------------------------------------------------------- #


def test_public_upsert_page_refuses_foreign_open_tx(repo: SQLiteRepository) -> None:
    conn = repo._connect()
    conn.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(sqlite3.OperationalError):
            repo.upsert_page(_page())
    finally:
        conn.execute("ROLLBACK")


def test_public_replace_refs_refuses_foreign_open_tx(repo: SQLiteRepository) -> None:
    repo.upsert_page(_page())
    conn = repo._connect()
    conn.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(sqlite3.OperationalError):
            repo.replace_refs("dal-helpers", "p1", "_vault_", [_ref()])
    finally:
        conn.execute("ROLLBACK")


# --------------------------------------------------------------------------- #
# The private helpers operate INSIDE a caller-owned open transaction (RED)
# --------------------------------------------------------------------------- #


def test_helper_upsert_joins_open_tx(repo: SQLiteRepository) -> None:
    conn = repo._connect()
    conn.execute("BEGIN IMMEDIATE")
    try:
        outcome = repo._upsert_page_in_txn(conn, _page(), skip_unchanged_check=True)
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    assert outcome == "inserted"
    assert repo.get_page("dal-helpers", "p1", "_vault_") is not None


def test_helper_upsert_rolls_back_with_caller_tx(repo: SQLiteRepository) -> None:
    """The helper contributes NO commit of its own — a caller ROLLBACK discards
    its DML (the whole point of caller-owned chunking)."""
    conn = repo._connect()
    conn.execute("BEGIN IMMEDIATE")
    repo._upsert_page_in_txn(conn, _page(), skip_unchanged_check=True)
    conn.execute("ROLLBACK")
    assert repo.get_page("dal-helpers", "p1", "_vault_") is None


def test_helper_upsert_unchanged_path_without_skip(repo: SQLiteRepository) -> None:
    """skip_unchanged_check=False keeps the hash pre-SELECT (public-path parity):
    same hash → "unchanged", no DML."""
    repo.upsert_page(_page())
    conn = repo._connect()
    conn.execute("BEGIN IMMEDIATE")
    try:
        outcome = repo._upsert_page_in_txn(conn, _page())
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    assert outcome == "unchanged"


def test_helper_replace_refs_joins_open_tx(repo: SQLiteRepository) -> None:
    repo.upsert_page(_page())
    conn = repo._connect()
    conn.execute("BEGIN IMMEDIATE")
    try:
        # Two refs with the SAME composite PK but DIFFERENT provenance — the
        # surviving quote discriminates first-wins from last-wins.
        repo._replace_refs_in_txn(conn, "dal-helpers", "p1", "_vault_",
                                  [_ref(line=1, quote="first"),
                                   _ref(line=9, quote="second")])
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    rows = conn.execute(
        "SELECT entity_slug, source_quote FROM page_entity_refs "
        "WHERE vault_id=? AND page_slug=?",
        ("dal-helpers", "p1")).fetchall()
    assert [(r["entity_slug"], r["source_quote"]) for r in rows] == [("t1", "first")]


def test_helper_replace_refs_rolls_back_with_caller_tx(repo: SQLiteRepository) -> None:
    """The refs helper contributes NO commit of its own either — a caller
    ROLLBACK restores the pre-call refs (no torn DELETE+INSERT)."""
    repo.upsert_page(_page())
    repo.replace_refs("dal-helpers", "p1", "_vault_", [_ref(target="orig")])
    conn = repo._connect()
    conn.execute("BEGIN IMMEDIATE")
    repo._replace_refs_in_txn(conn, "dal-helpers", "p1", "_vault_",
                              [_ref(target="replacement")])
    conn.execute("ROLLBACK")
    rows = conn.execute(
        "SELECT entity_slug FROM page_entity_refs WHERE vault_id=? AND page_slug=?",
        ("dal-helpers", "p1")).fetchall()
    assert [r["entity_slug"] for r in rows] == ["orig"]  # DELETE rolled back too


# --------------------------------------------------------------------------- #
# Privacy pin — helpers are NOT part of the DAL ABC
# --------------------------------------------------------------------------- #


def test_helpers_absent_from_abc() -> None:
    assert not hasattr(IndexRepository, "_upsert_page_in_txn")
    assert not hasattr(IndexRepository, "_replace_refs_in_txn")
