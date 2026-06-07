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
    assert result["slug_collisions"] == []  # TASK 020: field present, empty


def test_delta_surfaces_slug_collision_within_batch(tmp_path):
    """TASK 020: `--delta` surfaces a within-batch `(slug, project)` collision (both
    files newer than the cutoff are processed → the later overwrites the earlier)."""
    root = tmp_path / "vault"
    (root / ".wiki").mkdir(parents=True)
    (root / ".wiki" / "layout.yaml").write_text(
        "schema_version: '2.0'\nlayout: karpathy\nslug_strategy: identity\n"
        "paths:\n"
        "  - {glob: 'a/*.md', type: summary, project: '_vault_'}\n"
        "  - {glob: 'b/*.md', type: summary, project: '_vault_'}\n"
        "type_mapping:\n  summary: {db_type: summary, tag: null}\n",
        encoding="utf-8",
    )
    (root / "a").mkdir(); (root / "b").mkdir()
    (root / "a" / "01.md").write_text("# A\nx\n", encoding="utf-8")
    (root / "b" / "01.md").write_text("# B\ny\n", encoding="utf-8")
    r = SQLiteRepository(tmp_path / "g.db")
    r.apply_schema()
    r.register_vault(Vault(
        vault_id="col-delta", name="t", root_path=root,
        schema_version="2.0", registered_at=datetime(2026, 5, 26),
    ))
    result = reindex_delta(r, "col-delta")  # cutoff = registered_at < both mtimes
    cols = result["slug_collisions"]
    assert len(cols) == 1 and cols[0]["slug"] == "01"
    assert {cols[0]["kept"], cols[0]["dropped"]} == {"a/01.md", "b/01.md"}


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
