"""Tests for scripts/wiki_index/security.py (task-001-12 / R-26)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts.wiki_index.security import (
    PathTraversalError,
    assert_no_symlink_escape,
    validate_inside_vault,
)


# =============================================================================
# TC-E2E-01 — valid path inside vault returns resolved
# =============================================================================


def test_e2e_01_valid_path_returns_resolved(tmp_path):
    """Valid candidate path inside vault returns its resolved absolute form."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "_sources").mkdir()
    target = vault / "_sources" / "x.md"
    target.write_text("body")

    resolved = validate_inside_vault(target, vault)
    assert resolved == target.resolve()
    assert resolved.is_absolute()


def test_e2e_01b_vault_root_itself_accepted(tmp_path):
    """Vault root path itself passes (is_relative_to is True for self)."""
    vault = tmp_path / "vault"
    vault.mkdir()
    resolved = validate_inside_vault(vault, vault)
    assert resolved == vault.resolve()


# =============================================================================
# TC-UNIT-01 — path traversal rejected
# =============================================================================


def test_unit_01_dotdot_outside_vault_rejected(tmp_path):
    """A `../../` candidate that escapes the vault → PathTraversalError."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (tmp_path / "outside.md").write_text("evil")
    candidate = vault / ".." / "outside.md"  # resolves to tmp_path/outside.md

    with pytest.raises(PathTraversalError, match=r"outside vault root"):
        validate_inside_vault(candidate, vault)


def test_unit_01b_absolute_path_outside_rejected(tmp_path):
    """An absolute path that's not inside vault_root is rejected."""
    vault = tmp_path / "vault"
    vault.mkdir()
    outside = tmp_path / "other.md"
    outside.write_text("x")

    with pytest.raises(PathTraversalError):
        validate_inside_vault(outside, vault)


# =============================================================================
# TC-UNIT-02 — symlink escape via assert_no_symlink_escape
# =============================================================================


@pytest.mark.skipif(os.name == "nt", reason="Windows symlink semantics differ")
def test_unit_02_symlink_inside_anchor_traversed_safely(tmp_path):
    """Symlink inside the filesystem anchor: traversed without raising.

    Builds a symlinked ancestor (`a/link → a/target/`) and walks from
    deeper inside. Exercises the `current.is_symlink()` branch of the
    parent-walker without triggering the (Unix-impossible) "escapes
    anchor" check.
    """
    target = tmp_path / "target"
    target.mkdir()
    (target / "leaf").mkdir()
    link = tmp_path / "link"
    os.symlink(target, link)
    # Walking up from /tmp/.../link/leaf hits a symlink ancestor.
    assert_no_symlink_escape(link / "leaf")


@pytest.mark.skipif(os.name == "nt", reason="Windows symlink semantics differ")
def test_unit_02b_assert_no_symlink_escape_via_reindex(tmp_path):
    """reindex_full / reindex_delta call assert_no_symlink_escape on the
    resolved vault root. Re-rooting through a clean ancestor symlink is
    accepted (anchor unchanged on Unix); the guard is a defensive sanity
    rail, not a hard veto. See security.py module docstring for limits.
    """
    # Smoke: walking up from tmp_path itself does not raise.
    assert_no_symlink_escape(tmp_path)


# =============================================================================
# TC-UNIT-03 — vault root itself accepted (covered above)
# =============================================================================
# (Implemented as test_e2e_01b above.)


# =============================================================================
# TC-UNIT-04 — nonexistent path raises FileNotFoundError (NOT PathTraversalError)
# =============================================================================


def test_unit_04_nonexistent_candidate_propagates_filenotfound(tmp_path):
    """Per spec: `resolve(strict=True)` raises FileNotFoundError; caller decides
    whether to catch. We do NOT wrap it in PathTraversalError."""
    vault = tmp_path / "vault"
    vault.mkdir()
    bogus = vault / "does-not-exist.md"
    with pytest.raises(FileNotFoundError):
        validate_inside_vault(bogus, vault)


def test_unit_04b_nonexistent_vault_root_propagates_filenotfound(tmp_path):
    """resolve(strict=True) on missing vault_root also propagates FileNotFoundError."""
    bogus_vault = tmp_path / "nope-vault"
    candidate = tmp_path  # exists
    with pytest.raises(FileNotFoundError):
        validate_inside_vault(candidate, bogus_vault)


# =============================================================================
# assert_no_symlink_escape — basic API
# =============================================================================


def test_assert_no_symlink_escape_requires_absolute(tmp_path):
    """Relative path argument is rejected with PathTraversalError."""
    with pytest.raises(PathTraversalError, match=r"absolute"):
        assert_no_symlink_escape(Path("relative/path"))


def test_assert_no_symlink_escape_clean_path(tmp_path):
    """Clean absolute path under tmp_path passes without raising."""
    p = tmp_path / "x" / "y"
    p.mkdir(parents=True)
    assert_no_symlink_escape(p)  # no exception
