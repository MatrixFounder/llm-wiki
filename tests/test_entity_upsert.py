"""Tests for SQLiteRepository.upsert_entity (TASK 003 v2 / I-7.7a / R-37)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from scripts.wiki_index.models import Vault
from scripts.wiki_index.sqlite_repository import SQLiteRepository


@pytest.fixture
def repo(tmp_path: Path):
    r = SQLiteRepository(tmp_path / "test.db")
    r.apply_schema()
    r.register_vault(Vault(
        vault_id="trade-agents",
        name="Trade Agents",
        root_path=tmp_path / "trade-agents",
        schema_version="2.0",
        registered_at=datetime(2026, 5, 27),
    ))
    yield r
    r.close()


def _upsert(repo: SQLiteRepository, vault_id: str = "trade-agents",
            slug: str = "sharpe-ratio", name: str = "Sharpe Ratio",
            type_: str = "concept", is_candidate: int = 1,
            canonicalized_by: str = "llm:claude-sonnet-4-6@2026-05-27",
            ts: str = "2026-05-27T12:00:00",
            file_path: str | None = None) -> None:
    repo.upsert_entity(
        vault_id=vault_id, slug=slug, name=name, type=type_,
        is_candidate=is_candidate, canonicalized_by=canonicalized_by,
        first_seen=ts, last_updated=ts,
        file_path=file_path or f"_entities/{slug}.md",
    )


def _row(repo: SQLiteRepository, vault_id: str, slug: str) -> dict | None:
    cur = repo._connect().execute(
        "SELECT slug, name, type, is_candidate, canonicalized_by, "
        "first_seen, last_updated, file_path "
        "FROM entities WHERE vault_id=? AND slug=?", (vault_id, slug),
    )
    r = cur.fetchone()
    return dict(r) if r else None


def test_upsert_entity_inserts_new_row(repo: SQLiteRepository) -> None:
    """R-37(a): repo.upsert_entity creates a row with is_candidate=1."""
    _upsert(repo)
    row = _row(repo, "trade-agents", "sharpe-ratio")
    assert row is not None
    assert row["is_candidate"] == 1
    assert row["name"] == "Sharpe Ratio"
    assert row["type"] == "concept"
    assert row["canonicalized_by"].startswith("llm:claude-sonnet-4-6")


def test_upsert_entity_updates_existing_row(repo: SQLiteRepository) -> None:
    """Re-upsert mutates name, type, last_updated; first_seen NOT updated."""
    _upsert(repo, name="Old Name", ts="2026-05-01T10:00:00")
    _upsert(repo, name="New Name", ts="2026-05-27T12:00:00")
    row = _row(repo, "trade-agents", "sharpe-ratio")
    assert row is not None
    assert row["name"] == "New Name"
    assert row["last_updated"] == "2026-05-27T12:00:00"
    # first_seen preserved from initial insert
    assert row["first_seen"] == "2026-05-01T10:00:00"


def test_upsert_entity_no_downgrade_from_confirmed(repo: SQLiteRepository) -> None:
    """R-37(b) CRITICAL: confirmed entity (is_candidate=0) STAYS confirmed
    even when upsert re-runs with is_candidate=1. SQL-level guard via MIN()."""
    _upsert(repo, is_candidate=0)  # operator-confirmed
    _upsert(repo, is_candidate=1)  # candidate re-extraction attempt
    row = _row(repo, "trade-agents", "sharpe-ratio")
    assert row is not None
    assert row["is_candidate"] == 0, "MIN() guard must preserve confirmed status"


def test_upsert_entity_multi_vault_isolation(repo: SQLiteRepository) -> None:
    """Same slug in two vaults → two distinct rows (ADR-002 §D1.1)."""
    # Register second vault
    repo.register_vault(Vault(
        vault_id="other-vault", name="Other", root_path=Path("/tmp/other"),
        schema_version="2.0", registered_at=datetime(2026, 5, 27),
    ))
    _upsert(repo, vault_id="trade-agents", slug="hermes", name="Hermes in A",
            file_path="_entities/hermes.md")
    _upsert(repo, vault_id="other-vault", slug="hermes", name="Hermes in B",
            file_path="_entities/hermes.md")

    rows = repo._connect().execute(
        "SELECT vault_id, name FROM entities WHERE slug=?", ("hermes",),
    ).fetchall()
    assert len(rows) == 2
    by_vault = {r["vault_id"]: r["name"] for r in rows}
    assert by_vault["trade-agents"] == "Hermes in A"
    assert by_vault["other-vault"] == "Hermes in B"
