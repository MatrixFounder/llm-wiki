"""Tests for scripts/wiki_migrate_flat_to_folders.py (task-001-32)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.wiki_index.security import PathTraversalError
from scripts.wiki_migrate_flat_to_folders import migrate_flat_to_folders


@pytest.fixture
def flat_vault(tmp_path):
    """Vault with 16 flat .md files + a system file."""
    for i in range(16):
        (tmp_path / f"day{i:02d}-x.md").write_text(f"# Day {i}\n")
    (tmp_path / "WIKI_SCHEMA.md").write_text("# Schema\nvault_id: t-test\n")
    return tmp_path


def test_e2e_01_migrate_all_files(flat_vault):
    """16 .md files → _sources/, system file stays."""
    result = migrate_flat_to_folders(flat_vault)
    assert result["moved"] == 16
    assert (flat_vault / "_sources").is_dir()
    assert (flat_vault / "_sources" / "day00-x.md").is_file()
    # System file preserved at root
    assert (flat_vault / "WIKI_SCHEMA.md").is_file()
    # Idempotent re-run → 0 moves
    result2 = migrate_flat_to_folders(flat_vault)
    assert result2["moved"] == 0


def test_e2e_02_dry_run(flat_vault):
    """--dry-run reports but doesn't move."""
    result = migrate_flat_to_folders(flat_vault, dry_run=True)
    assert result["moved"] == 16
    assert result["dry_run"] is True
    # Files still at root
    assert (flat_vault / "day00-x.md").is_file()
    assert not (flat_vault / "_sources" / "day00-x.md").exists()


def test_e2e_03_system_files_skipped(tmp_path):
    """WIKI_SCHEMA / CLAUDE / log / index never moved."""
    for sysname in ("WIKI_SCHEMA.md", "CLAUDE.md", "log.md", "index.md"):
        (tmp_path / sysname).write_text(f"# {sysname}\n")
    (tmp_path / "data.md").write_text("# data\n")
    result = migrate_flat_to_folders(tmp_path)
    assert result["moved"] == 1  # only data.md
    assert result["skipped"] == 4
    for sysname in ("WIKI_SCHEMA.md", "CLAUDE.md", "log.md", "index.md"):
        assert (tmp_path / sysname).is_file()


def test_unit_01_idempotent(flat_vault):
    """First run moves; second run no-ops."""
    migrate_flat_to_folders(flat_vault)
    result = migrate_flat_to_folders(flat_vault)
    assert result["moved"] == 0


def test_unit_02_hash_mismatch_warning(tmp_path):
    """Target exists with different content → error logged, no overwrite."""
    (tmp_path / "_sources").mkdir()
    (tmp_path / "x.md").write_text("# new\n")
    (tmp_path / "_sources" / "x.md").write_text("# old\n")
    result = migrate_flat_to_folders(tmp_path)
    assert result["moved"] == 0
    assert len(result["errors"]) == 1
    assert "manual resolve" in result["errors"][0]["error"]
    # Both files still exist
    assert (tmp_path / "x.md").is_file()
    assert (tmp_path / "_sources" / "x.md").read_text() == "# old\n"


def test_unit_03_subdirs_not_descended(tmp_path):
    """Files already in a subdir are NOT moved (top-level walk only)."""
    (tmp_path / "_sources").mkdir()
    (tmp_path / "_sources" / "already.md").write_text("# already\n")
    (tmp_path / "newone.md").write_text("# new\n")
    result = migrate_flat_to_folders(tmp_path)
    assert result["moved"] == 1
    # The pre-existing file in _sources untouched
    assert (tmp_path / "_sources" / "already.md").is_file()


def test_unit_04_target_subdir_traversal_rejected(tmp_path):
    """--target-subdir ../escape → PathTraversalError; no files moved."""
    (tmp_path / "data.md").write_text("# data\n")
    with pytest.raises(PathTraversalError):
        migrate_flat_to_folders(tmp_path, target_subdir="../escape")
    with pytest.raises(PathTraversalError):
        migrate_flat_to_folders(tmp_path, target_subdir="/abs/path")
    with pytest.raises(PathTraversalError):
        migrate_flat_to_folders(tmp_path, target_subdir="")
    # File still at root
    assert (tmp_path / "data.md").is_file()


def test_cli_invocation(flat_vault):
    """CLI entry point produces JSON summary."""
    result = subprocess.run(
        [sys.executable, "-m", "scripts.wiki_migrate_flat_to_folders",
         str(flat_vault), "--dry-run"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0
    out = json.loads(result.stdout)
    assert out["moved"] == 16
    assert out["dry_run"] is True
