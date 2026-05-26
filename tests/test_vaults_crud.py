"""Tests for SQLiteRepository vaults CRUD impl (task-001-15)."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from scripts.wiki_index.models import Vault
from scripts.wiki_index.sqlite_repository import SQLiteRepository, VaultRegistrationError


@pytest.fixture
def repo(tmp_path: Path):
    """A fresh SQLiteRepository with schema applied + bootstrap '_global_' row."""
    r = SQLiteRepository(tmp_path / "test.db")
    r.apply_schema()
    yield r
    r.close()


def _vault(vault_id: str = "trade-agents", root_path: Path | None = None) -> Vault:
    return Vault(
        vault_id=vault_id,
        name=f"{vault_id} display",
        root_path=root_path or Path(f"/tmp/{vault_id}"),
        schema_version="2.0",
        registered_at=datetime(2026, 5, 26, 14, 0, 0),
        config_json={"language": "en"},
        notes=None,
    )


# =============================================================================
# TC-E2E-01 — register + get round-trip
# =============================================================================


def test_e2e_01_register_then_get_round_trip(repo):
    """register_vault persists; get_vault returns equivalent row."""
    v = _vault()
    repo.register_vault(v)
    got = repo.get_vault("trade-agents")
    assert got is not None
    assert got.vault_id == v.vault_id
    assert got.name == v.name
    assert got.root_path == v.root_path
    assert got.config_json == {"language": "en"}


def test_e2e_01b_get_unknown_returns_none(repo):
    assert repo.get_vault("no-such-vault") is None


# =============================================================================
# TC-E2E-02 — list_vaults excludes '_global_' sentinel
# =============================================================================


def test_e2e_02_list_excludes_global_sentinel(repo):
    """If the '_global_' sentinel exists, list_vaults excludes it."""
    repo._connect().execute(
        "INSERT INTO vaults VALUES ('_global_', 'sentinel', '/dev/null', '2.0', "
        "'2026-05-26T00:00:00Z', NULL, 'auto')"
    )
    repo.register_vault(_vault("vault-a", Path("/tmp/a")))
    repo.register_vault(_vault("vault-b", Path("/tmp/b")))
    listed = repo.list_vaults()
    assert {v.vault_id for v in listed} == {"vault-a", "vault-b"}
    assert "_global_" not in {v.vault_id for v in listed}


# =============================================================================
# TC-E2E-03 — rename CASCADEs to dependent tables
# =============================================================================


def test_e2e_03_rename_cascades_to_pages(repo):
    """Renaming a vault propagates through pages.vault_id (ON UPDATE CASCADE)."""
    repo.register_vault(_vault("trade-agents", Path("/tmp/trade-agents")))
    repo._connect().execute(
        "INSERT INTO pages (vault_id, slug, project, type, title, file_path, date, "
        "last_modified, file_hash, frontmatter_json) "
        "VALUES ('trade-agents', 'hermes-agent', '_vault_', 'concept', 'Hermes', "
        "'_concepts/hermes-agent.md', '2026-05-25', '2026-05-25T10:00:00Z', "
        "'abc', '{}')"
    )
    repo.rename_vault("trade-agents", "trading-research")
    row = repo._connect().execute(
        "SELECT vault_id FROM pages WHERE slug = 'hermes-agent'"
    ).fetchone()
    assert row["vault_id"] == "trading-research"


# =============================================================================
# TC-UNIT-01/02 — IntegrityError → VaultRegistrationError
# =============================================================================


def test_unit_01_duplicate_vault_id_raises(repo):
    """Duplicate vault_id INSERT raises VaultRegistrationError."""
    repo.register_vault(_vault("trade-agents", Path("/tmp/a")))
    with pytest.raises(VaultRegistrationError, match=r"trade-agents"):
        repo.register_vault(_vault("trade-agents", Path("/tmp/b")))


def test_unit_02_duplicate_root_path_raises(repo):
    """Duplicate root_path INSERT raises VaultRegistrationError."""
    repo.register_vault(_vault("vault-a", Path("/tmp/shared")))
    with pytest.raises(VaultRegistrationError):
        repo.register_vault(_vault("vault-b", Path("/tmp/shared")))


# =============================================================================
# TC-UNIT-03/04/05 — connection management + pragmas
# =============================================================================


def test_unit_03_connect_is_idempotent(repo):
    """_connect returns the same Connection on repeated calls."""
    c1 = repo._connect()
    c2 = repo._connect()
    assert c1 is c2


def test_unit_04_wal_pragma_active(repo):
    """journal_mode is WAL after _connect."""
    assert repo._connect().execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_unit_05_foreign_keys_active(repo):
    """foreign_keys ON; orphan FK insert fails."""
    assert repo._connect().execute("PRAGMA foreign_keys").fetchone()[0] == 1
    # pages.vault_id has FK to vaults; inserting without parent row → IntegrityError
    with pytest.raises(sqlite3.IntegrityError):
        repo._connect().execute(
            "INSERT INTO pages (vault_id, slug, project, type, title, file_path, "
            "date, last_modified, file_hash, frontmatter_json) "
            "VALUES ('no-such-vault', 's', '_vault_', 'summary', 't', '/x', "
            "'2026-01-01', '2026-01-01T00:00:00Z', 'h', '{}')"
        )


# =============================================================================
# TC-UNIT M-1 — vault_id CHECK rejects malformed at INSERT (defense in depth)
# =============================================================================


def test_unit_m1_check_rejects_malformed_vault_id(repo):
    """Malformed vault_id rejected by SQLite CHECK (ADR-002 §D1.1, M-1).

    Note: this test uses raw SQL to bypass the Python-side dataclass validation
    (which doesn't actually enforce vault_id format). The schema constraint is
    the source-of-truth.
    """
    with pytest.raises(sqlite3.IntegrityError, match=r"CHECK"):
        repo._connect().execute(
            "INSERT INTO vaults VALUES ('1bad', 'n', '/tmp/x', '2.0', "
            "'2026-01-01T00:00:00Z', NULL, NULL)"
        )


# =============================================================================
# context manager support
# =============================================================================


def test_context_manager_closes_connection(tmp_path):
    """`with SQLiteRepository(...) as r:` closes connection on exit."""
    r = SQLiteRepository(tmp_path / "ctx.db")
    r.apply_schema()
    with r:
        assert r._conn is not None
    assert r._conn is None


def test_rename_unknown_vault_raises(repo):
    """Renaming a nonexistent vault_id raises VaultRegistrationError."""
    with pytest.raises(VaultRegistrationError, match=r"not found"):
        repo.rename_vault("ghost", "phantom")
