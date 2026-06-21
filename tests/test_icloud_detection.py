"""Tests for iCloud detection + DB path resolver (task-001-14, R-03)."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.wiki_index.factory import (
    ICloudRejectionError,
    _is_icloud_path,
    _resolve_db_path,
    validate_db_path,
)


# =============================================================================
# TC-UNIT-01 — both iCloud patterns detected
# =============================================================================


@pytest.mark.parametrize(
    "path_str",
    [
        "/Users/me/Library/Mobile Documents/iCloud~md~obsidian/vault.db",
        "/Users/me/Library/Mobile Documents/iCloud~com~example/file.db",
        "/Users/me/Library/Mobile Documents/com~apple~CloudDocs/vault.db",
    ],
)
def test_unit_01_icloud_paths_detected(path_str):
    """Both iCloud~ and com~apple~ patterns flagged under Mobile Documents/."""
    assert _is_icloud_path(Path(path_str)) is True


@pytest.mark.parametrize(
    "path_str",
    [
        "/tmp/plain.db",
        "/Users/me/Library/Application Support/wiki-index/global.db",
        "/Users/me/Documents/notes.db",
        "/home/u/.local/share/wiki-index/global.db",
        "/Users/me/iCloud-fake/notiCloud.db",  # no `Mobile Documents/` prefix
    ],
)
def test_unit_01b_non_icloud_paths_pass(path_str):
    """Non-iCloud paths are not flagged."""
    assert _is_icloud_path(Path(path_str)) is False


# =============================================================================
# TC-UNIT-02/03/04 — platform-default paths
# =============================================================================


def test_unit_02_macos_default_path():
    """macOS default is ~/Library/Application Support/wiki-index/global.db."""
    p = _resolve_db_path("trade-agents", "darwin")
    expected = Path.home() / "Library" / "Application Support" / "wiki-index" / "global.db"
    assert p == expected


def test_unit_03_linux_default_path():
    """Linux default is ~/.local/share/wiki-index/global.db."""
    p = _resolve_db_path("trade-agents", "linux")
    expected = Path.home() / ".local" / "share" / "wiki-index" / "global.db"
    assert p == expected


def test_unit_04_unknown_platform_raises():
    """Unknown platform → RuntimeError."""
    with pytest.raises(RuntimeError, match=r"Unsupported platform"):
        _resolve_db_path("v", "klingon-os")


def test_appdata_root_is_parent_of_wiki_index_dir():
    """TASK 042: the carve-out's trusted root MUST be exactly the parent of where wiki-init
    writes the default DB — so `appdata_root` cannot drift from `_resolve_db_path`."""
    from scripts.wiki_index.factory import appdata_root
    for plat in ("darwin", "linux"):
        assert _resolve_db_path("v", plat).parent.parent == appdata_root(plat)
    with pytest.raises(RuntimeError, match=r"Unsupported platform"):
        appdata_root("klingon-os")


def test_unit_05_parent_dir_created(tmp_path, monkeypatch):
    """_resolve_db_path ensures parent directory exists."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    p = _resolve_db_path("v", "darwin")
    assert p.parent.is_dir()


def test_unit_06_global_db_single_file(monkeypatch, tmp_path):
    """ADR-002 §D1: one global.db for all vaults — vault_id does not affect path."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    p1 = _resolve_db_path("vault-a", "darwin")
    p2 = _resolve_db_path("vault-b", "darwin")
    assert p1 == p2  # same file


# =============================================================================
# TC-E2E-01 / TC-E2E-02 — validate_db_path
# =============================================================================


def test_e2e_01_icloud_path_rejected():
    """validate_db_path raises on an iCloud-located path."""
    icloud = Path("/Users/me/Library/Mobile Documents/iCloud~md~obsidian/v.db")
    with pytest.raises(ICloudRejectionError, match=r"iCloud"):
        validate_db_path(icloud)


def test_e2e_02_non_icloud_path_accepted(tmp_path):
    """validate_db_path returns silently on non-iCloud paths."""
    validate_db_path(tmp_path / "global.db")  # no exception


def test_e2e_03_task_md_fixture_pattern_detected():
    """The fixture pattern from TASK.md §6.3 is correctly flagged.

    `/private/tmp/wiki-test-vault/Mobile Documents/iCloud~md~obsidian/test-vault/`
    is documented as iCloud-test setup and MUST be rejected.
    """
    fixture = Path(
        "/private/tmp/wiki-test-vault/Mobile Documents/iCloud~md~obsidian/test-vault/x.db"
    )
    assert _is_icloud_path(fixture) is True
