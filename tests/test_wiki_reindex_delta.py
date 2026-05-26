"""Tests for wiki-reindex --delta (task-001-31)."""

from __future__ import annotations

import os
import time
from datetime import datetime
from pathlib import Path

import pytest

from scripts.wiki_index.models import Vault
from scripts.wiki_index.reindex import reindex_delta, reindex_full
from scripts.wiki_index.sqlite_repository import SQLiteRepository


@pytest.fixture
def populated(minimal_vault, tmp_path):
    r = SQLiteRepository(tmp_path / "g.db")
    r.apply_schema()
    r.register_vault(Vault(
        vault_id="minimal-test", name="t", root_path=minimal_vault,
        schema_version="2.0", registered_at=datetime(2026, 5, 26),
    ))
    reindex_full(r, "minimal-test")
    yield r, minimal_vault
    r.close()


def test_delta_no_changes_is_fast(populated):
    """Delta with no file changes: touched=0, deleted=0."""
    r, _ = populated
    result = reindex_delta(r, "minimal-test")
    assert result["touched"] == 0
    assert result["deleted"] == 0


def test_delta_picks_up_modified_file(populated):
    """Touching a file's mtime → delta re-ingests it."""
    r, vault = populated
    target = vault / "_sources" / "alpha.md"
    # Force future mtime
    future = time.time() + 60
    os.utime(target, (future, future))
    result = reindex_delta(r, "minimal-test")
    assert result["touched"] >= 1


def test_delta_deletes_orphan_db_row(populated):
    """File removed from disk → DB row deleted."""
    r, vault = populated
    (vault / "_sources" / "alpha.md").unlink()
    result = reindex_delta(r, "minimal-test")
    assert result["deleted"] >= 1
    # Confirm absent from DB
    assert r.get_page("minimal-test", "alpha", "_vault_") is None
