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
    # TASK 021 (R-021-4): assert DIRECTION, not just the set — kept = the later
    # POSIX-sorted file now in the DB; dropped = the earlier clobbered one.
    assert cols[0]["kept"] == "b/01.md" and cols[0]["dropped"] == "a/01.md"
    row = r._connect().execute(
        "SELECT file_path FROM pages WHERE vault_id='col-delta' AND slug='01'").fetchone()
    assert row["file_path"] == cols[0]["kept"]   # surviving row == kept


def _xbatch_vault(root: Path):
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


def test_delta_surfaces_cross_batch_collision(tmp_path):
    """TASK 021 (R-021-2 / HIGH-2): a delta file colliding with a row written by a PRIOR
    batch (mtime <= cutoff → not re-walked) is REPORTED, not silently clobbered. Seeding
    `seen_keys` from the DB closes the gap the within-batch detector left open."""
    root = tmp_path / "vault"
    _xbatch_vault(root)
    fa = root / "a" / "01.md"
    fa.write_text("# A batch1\n", encoding="utf-8")
    os.utime(fa, (time.time() - 86400, time.time() - 86400))  # old → < cutoff after full
    r = SQLiteRepository(tmp_path / "g.db")
    r.apply_schema()
    r.register_vault(Vault(vault_id="xbatchd", name="t", root_path=root,
                           schema_version="2.0", registered_at=datetime(2026, 5, 1)))
    reindex_full(r, "xbatchd")
    fb = root / "b" / "01.md"
    fb.write_text("# B batch2\n", encoding="utf-8")
    os.utime(fb, (time.time() + 86400, time.time() + 86400))  # future → > cutoff
    result = reindex_delta(r, "xbatchd")
    cols = result["slug_collisions"]
    assert len(cols) == 1 and cols[0]["kept"] == "b/01.md" and cols[0]["dropped"] == "a/01.md"
    row = r._connect().execute(
        "SELECT file_path FROM pages WHERE vault_id='xbatchd' AND slug='01'").fetchone()
    assert row["file_path"] == "b/01.md"


def test_delta_both_touched_on_populated_db_single_record(tmp_path):
    """TASK 021 review L-1: when BOTH colliding files are re-walked in a delta on a
    pre-populated DB, exactly ONE correctly-directed record is emitted (not two, and not an
    inverted first record). The refined seed excludes re-walked rows so the within-batch
    loop is the sole authority."""
    root = tmp_path / "vault"
    _xbatch_vault(root)
    fa = root / "a" / "01.md"; fb = root / "b" / "01.md"
    fa.write_text("# A v1\n", encoding="utf-8")
    fb.write_text("# B v1\n", encoding="utf-8")
    old = time.time() - 86400
    os.utime(fa, (old, old)); os.utime(fb, (old, old))
    r = SQLiteRepository(tmp_path / "g.db")
    r.apply_schema()
    r.register_vault(Vault(vault_id="bothtch", name="t", root_path=root,
                           schema_version="2.0", registered_at=datetime(2026, 5, 1)))
    reindex_full(r, "bothtch")  # DB survivor = b/01.md (later POSIX-sorted)
    new = time.time() + 86400
    fa.write_text("# A v2\n", encoding="utf-8"); fb.write_text("# B v2\n", encoding="utf-8")
    os.utime(fa, (new, new)); os.utime(fb, (new, new))  # BOTH touched
    cols = reindex_delta(r, "bothtch")["slug_collisions"]
    assert len(cols) == 1  # not double-counted
    assert cols[0]["kept"] == "b/01.md" and cols[0]["dropped"] == "a/01.md"  # correct direction
    row = r._connect().execute(
        "SELECT file_path FROM pages WHERE vault_id='bothtch' AND slug='01'").fetchone()
    assert row["file_path"] == "b/01.md"


def test_delta_rename_same_slug_no_false_collision(tmp_path):
    """TASK 021 review L-2: a rename that preserves the resolved (slug, project) — old file
    deleted, new file created — is NOT reported as a collision (the prior row's file is gone,
    so it is not a coexisting collision). The seed excludes off-disk prior rows."""
    root = tmp_path / "vault"
    _xbatch_vault(root)
    fa = root / "a" / "01.md"
    fa.write_text("# A\n", encoding="utf-8")
    os.utime(fa, (time.time() - 86400, time.time() - 86400))
    r = SQLiteRepository(tmp_path / "g.db")
    r.apply_schema()
    r.register_vault(Vault(vault_id="renamev", name="t", root_path=root,
                           schema_version="2.0", registered_at=datetime(2026, 5, 1)))
    reindex_full(r, "renamev")
    fa.unlink()  # rename: remove a/01.md ...
    fb = root / "b" / "01.md"
    fb.write_text("# B (renamed)\n", encoding="utf-8")  # ... create b/01.md (same slug)
    os.utime(fb, (time.time() + 86400, time.time() + 86400))
    result = reindex_delta(r, "renamev")
    assert result["slug_collisions"] == []  # no false positive naming the gone file
    row = r._connect().execute(
        "SELECT file_path FROM pages WHERE vault_id='renamev' AND slug='01'").fetchone()
    assert row["file_path"] == "b/01.md"


def test_delta_self_update_no_collision(tmp_path):
    """TASK 021 (R-021-2 guard): re-processing the SAME file (no colliding sibling) must
    NOT false-collide — `_detect_slug_collision`'s `prior != rel` guard holds against the
    DB-seeded `seen_keys`."""
    root = tmp_path / "vault"
    (root / ".wiki").mkdir(parents=True)
    (root / ".wiki" / "layout.yaml").write_text(
        "schema_version: '2.0'\nlayout: karpathy\nslug_strategy: identity\n"
        "paths:\n  - {glob: 'a/*.md', type: summary, project: '_vault_'}\n"
        "type_mapping:\n  summary: {db_type: summary, tag: null}\n", encoding="utf-8")
    (root / "a").mkdir()
    fa = root / "a" / "01.md"
    fa.write_text("# v1\n", encoding="utf-8")
    os.utime(fa, (time.time() - 86400, time.time() - 86400))
    r = SQLiteRepository(tmp_path / "g.db")
    r.apply_schema()
    r.register_vault(Vault(vault_id="selfupd", name="t", root_path=root,
                           schema_version="2.0", registered_at=datetime(2026, 5, 1)))
    reindex_full(r, "selfupd")
    fa.write_text("# v2 edited\n", encoding="utf-8")
    os.utime(fa, (time.time() + 86400, time.time() + 86400))
    result = reindex_delta(r, "selfupd")
    assert result["touched"] == 1
    assert result["slug_collisions"] == []


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
