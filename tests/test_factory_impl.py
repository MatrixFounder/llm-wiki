"""Tests for factory.make_repo real impl (task-001-20)."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.wiki_index.factory import (
    ConfigValidationError,
    ICloudRejectionError,
    apply_schema_if_missing,
    make_repo,
)


def test_e2e_01_schema_applied_on_first_call(tmp_path):
    """First call on a fresh DB applies schema; subsequent calls don't re-apply
    (apply_schema_if_missing is idempotent by file-size check)."""
    db = tmp_path / "g.db"
    repo = make_repo({"vault_id": "test-vault", "db_path": str(db)})
    assert db.exists() and db.stat().st_size > 0
    # Verify schema applied: pages_fts virtual table exists
    n = repo._connect().execute(
        "SELECT count(*) FROM sqlite_master WHERE name='pages_fts'"
    ).fetchone()[0]
    assert n == 1
    # Re-call doesn't blow up
    repo2 = make_repo({"vault_id": "test-vault", "db_path": str(db)})
    assert repo2.db_path == db
    repo.close()
    repo2.close()


def test_e2e_02_icloud_path_rejected(tmp_path):
    """A config pointing at an iCloud path → ICloudRejectionError."""
    icloud = "/Users/me/Library/Mobile Documents/iCloud~md~obsidian/v.db"
    with pytest.raises(ICloudRejectionError):
        make_repo({"vault_id": "test-vault", "db_path": icloud})


def test_e2e_03_missing_vault_id_rejected():
    """Config without vault_id → ConfigValidationError before any DB I/O."""
    with pytest.raises(ConfigValidationError, match=r"REQUIRED"):
        make_repo({})


@pytest.mark.parametrize("bad", ["1bad", "AB", "foo--bar", "a", "trade-agents-"])
def test_unit_02_invalid_vault_id_rejected(bad):
    """Format-violating vault_id rejected at factory level."""
    with pytest.raises(ConfigValidationError):
        make_repo({"vault_id": bad, "db_path": "/tmp/x.db"})


def test_e2e_04_valid_config_returns_usable_repo(tmp_path):
    """Returned repo is functional — list_vaults works on empty registry."""
    repo = make_repo({"vault_id": "test-vault", "db_path": str(tmp_path / "v.db")})
    assert repo.list_vaults() == []
    repo.close()


def test_unit_01_apply_schema_if_missing_idempotent(tmp_path):
    """Second call on populated DB does not raise or overwrite."""
    db = tmp_path / "x.db"
    apply_schema_if_missing(db)
    mtime1 = db.stat().st_mtime
    # Re-call should no-op
    apply_schema_if_missing(db)
    mtime2 = db.stat().st_mtime
    assert mtime1 == mtime2  # not rewritten
