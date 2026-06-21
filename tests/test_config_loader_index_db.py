"""TASK 022 / bead 02-01 — `config_loader.resolve_index_db_path`.

`index_db` (raw WIKI_SCHEMA.md frontmatter) → DB Path | None. Relative form is
contained-in-vault via resolve-then-check (symlink escape blocked); absolute form is
the explicit operator escape; absent → None; the offending value is never echoed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from scripts.wiki_index.config_loader import (
    ConfigValidationError,
    resolve_index_db_path,
)


def _vault(tmp_path: Path, index_db_line: str | None) -> Path:
    root = tmp_path / "v"
    root.mkdir()
    fm = "---\nvault_id: demo-vault\nschema_version: '2.0'\n"
    if index_db_line is not None:
        fm += f"{index_db_line}\n"
    fm += "---\n\n# schema\n"
    (root / "WIKI_SCHEMA.md").write_text(fm, encoding="utf-8")
    return root


def test_relative_in_vault(tmp_path):
    root = _vault(tmp_path, "index_db: .wiki/index.db")
    got = resolve_index_db_path(root)
    assert got == root / ".wiki" / "index.db"


def test_absent_is_none(tmp_path):
    root = _vault(tmp_path, None)
    assert resolve_index_db_path(root) is None


def test_non_string_is_none(tmp_path):
    root = _vault(tmp_path, "index_db: 42")
    assert resolve_index_db_path(root) is None


def test_absolute_rejected_without_env(tmp_path, monkeypatch):
    """vdd-multi HIGH-S2: an absolute index_db is an arbitrary-write primitive under an
    attacker-shippable config → rejected unless WIKI_ALLOW_ABSOLUTE_INDEX_DB is set."""
    monkeypatch.delenv("WIKI_ALLOW_ABSOLUTE_INDEX_DB", raising=False)
    root = _vault(tmp_path, "index_db: ~/wiki-dbs/demo.db")
    with pytest.raises(ConfigValidationError):
        resolve_index_db_path(root)


def test_absolute_allowed_with_env(tmp_path, monkeypatch):
    monkeypatch.setenv("WIKI_ALLOW_ABSOLUTE_INDEX_DB", "1")
    root = _vault(tmp_path, "index_db: ~/wiki-dbs/demo.db")
    assert resolve_index_db_path(root) == Path.home() / "wiki-dbs" / "demo.db"


def test_absolute_under_appdata_trusted_without_env(tmp_path, monkeypatch):
    """TASK 042 carve-out: an absolute DB under the OS app-data root (where wiki-init writes;
    never iCloud) is trusted WITHOUT the env var — the required config for an iCloud vault whose
    DB must live outside iCloud (this is the exact case that failed in the dogfood session)."""
    import scripts.wiki_index.factory as factory
    appdata = tmp_path / "appdata"
    (appdata / "obsidian-llm-wiki").mkdir(parents=True)
    monkeypatch.setattr(factory, "appdata_root", lambda platform=None: appdata)
    monkeypatch.delenv("WIKI_ALLOW_ABSOLUTE_INDEX_DB", raising=False)
    db = appdata / "obsidian-llm-wiki" / "personal.db"
    root = _vault(tmp_path, f"index_db: {db}")
    assert resolve_index_db_path(root) == db


def test_absolute_outside_appdata_still_requires_env(tmp_path, monkeypatch):
    """The carve-out is NARROW: an absolute path NOT under app-data still needs the env var."""
    import scripts.wiki_index.factory as factory
    monkeypatch.setattr(factory, "appdata_root", lambda platform=None: tmp_path / "appdata")
    monkeypatch.delenv("WIKI_ALLOW_ABSOLUTE_INDEX_DB", raising=False)
    root = _vault(tmp_path, "index_db: ~/wiki-dbs/demo.db")  # not under the (patched) app-data
    with pytest.raises(ConfigValidationError):
        resolve_index_db_path(root)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlink")
def test_absolute_appdata_symlink_escape_not_trusted(tmp_path, monkeypatch):
    """The carve-out resolves symlinks FIRST: a symlink located under app-data but pointing
    OUTSIDE it is NOT trusted, so it can't smuggle an arbitrary-write target past the gate."""
    import scripts.wiki_index.factory as factory
    appdata = tmp_path / "appdata"
    appdata.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = appdata / "sneaky.db"
    link.symlink_to(outside / "evil.db")
    monkeypatch.setattr(factory, "appdata_root", lambda platform=None: appdata)
    monkeypatch.delenv("WIKI_ALLOW_ABSOLUTE_INDEX_DB", raising=False)
    root = _vault(tmp_path, f"index_db: {link}")
    with pytest.raises(ConfigValidationError):
        resolve_index_db_path(root)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlink")
def test_symlinked_leaf_escape_rejected(tmp_path):
    """vdd-multi HIGH-S1: a symlinked LEAF (`.wiki/index.db → /outside`) — the parent
    dir is in-vault but the file itself escapes — is rejected (full-path resolve +
    leaf-symlink refusal), closing the arbitrary-write hole the parent-only check left."""
    outside = tmp_path / "outside"
    outside.mkdir()
    root = _vault(tmp_path, "index_db: .wiki/index.db")
    (root / ".wiki").mkdir()
    (root / ".wiki" / "index.db").symlink_to(outside / "evil.db")
    with pytest.raises(ConfigValidationError):
        resolve_index_db_path(root)


def test_vault_id_mismatch_returns_none(tmp_path):
    """vdd-multi HIGH-L1: when the caller names a vault, an index_db at a root that
    belongs to a DIFFERENT vault is ignored (→ None → global), so a CWD walk-up can't
    redirect a by-id command to the wrong DB."""
    root = _vault(tmp_path, "index_db: .wiki/index.db")  # vault_id == demo-vault
    assert resolve_index_db_path(root, expected_vault_id="other-vault") is None
    assert resolve_index_db_path(
        root, expected_vault_id="demo-vault") == root / ".wiki" / "index.db"


def test_relative_dotdot_escape_rejected(tmp_path):
    root = _vault(tmp_path, "index_db: ../escape.db")
    with pytest.raises(ConfigValidationError) as exc:
        resolve_index_db_path(root)
    assert "escape.db" not in str(exc.value)  # CWE-209: value not echoed


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlink")
def test_symlinked_wiki_dir_escape_rejected(tmp_path):
    """`<vault>/.wiki -> /outside`; relative `index_db: .wiki/index.db` resolves out
    of the vault → rejected (resolve-then-check, not a lexical check)."""
    outside = tmp_path / "outside"
    outside.mkdir()
    root = _vault(tmp_path, "index_db: .wiki/index.db")
    (root / ".wiki").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ConfigValidationError):
        resolve_index_db_path(root)
