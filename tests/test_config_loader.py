"""Tests for scripts/wiki_index/config_loader.py (task-001-13)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scripts.wiki_index.config_loader import (
    ConfigValidationError,
    VaultRootNotFoundError,
    deep_merge,
    find_project_root,
    find_vault_root,
    load_config,
)


# =============================================================================
# TC-E2E-01 — load config from minimal_vault fixture
# =============================================================================


def test_e2e_01_load_config_from_minimal_vault(minimal_vault: Path):
    """load_config from inside the minimal-vault returns merged config with vault_id."""
    cfg = load_config(minimal_vault)
    assert cfg["vault_id"] == "minimal-test"
    assert cfg["schema_version"] == "2.0"
    assert cfg["language"] == "en"
    assert cfg["layout"] == "flat"


def test_e2e_01b_load_config_from_subdirectory(minimal_vault: Path):
    """load_config walks up correctly when cwd is a vault subdirectory."""
    cfg = load_config(minimal_vault / "_sources")
    assert cfg["vault_id"] == "minimal-test"


# =============================================================================
# TC-UNIT-01 — find_vault_root walk-up
# =============================================================================


def test_unit_01_find_vault_root_from_root(minimal_vault: Path):
    """find_vault_root returns the dir containing WIKI_SCHEMA.md."""
    assert find_vault_root(minimal_vault) == minimal_vault.resolve()


def test_unit_01b_find_vault_root_from_nested_subdir(minimal_vault: Path):
    """find_vault_root walks up from a nested subdirectory."""
    nested = minimal_vault / "_sources"
    assert find_vault_root(nested) == minimal_vault.resolve()


def test_unit_01c_find_vault_root_raises_when_no_schema(tmp_path: Path):
    """find_vault_root raises VaultRootNotFoundError if no WIKI_SCHEMA.md found."""
    bare = tmp_path / "no-vault"
    bare.mkdir()
    with pytest.raises(VaultRootNotFoundError):
        find_vault_root(bare)


# =============================================================================
# TC-UNIT-02 — deep-merge semantics
# =============================================================================


def test_unit_02_deep_merge_dicts_recursively():
    """Nested dicts are merged; override wins per key."""
    base = {"a": 1, "nested": {"x": 1, "y": 2}}
    override = {"nested": {"y": 99, "z": 3}}
    merged = deep_merge(base, override)
    assert merged == {"a": 1, "nested": {"x": 1, "y": 99, "z": 3}}


def test_unit_02b_deep_merge_lists_replaced_not_concatenated():
    """R-01.2 semantic: lists are REPLACED, not concatenated."""
    base = {"tags": ["a", "b"]}
    override = {"tags": ["c"]}
    merged = deep_merge(base, override)
    assert merged == {"tags": ["c"]}


def test_unit_02c_deep_merge_scalars_replaced():
    """Scalar override wins."""
    assert deep_merge({"a": 1}, {"a": 2}) == {"a": 2}


def test_unit_02d_deep_merge_returns_new_dict():
    """Merge does NOT mutate `base`."""
    base = {"a": 1}
    deep_merge(base, {"a": 2})
    assert base == {"a": 1}


# =============================================================================
# TC-UNIT-03 — missing vault_id rejected
# =============================================================================


def test_unit_03_missing_vault_id_rejected(tmp_path: Path):
    """A vault with WIKI_SCHEMA.md but no `vault_id` field fails validation."""
    vault = tmp_path / "broken-vault"
    vault.mkdir()
    (vault / "WIKI_SCHEMA.md").write_text(
        "---\nname: WIKI_SCHEMA\nschema_version: '2.0'\nlanguage: en\nlayout: flat\n---\n"
    )
    with pytest.raises(ConfigValidationError, match=r"vault_id"):
        load_config(vault)


# =============================================================================
# TC-UNIT-04 — malformed vault_id rejected
# =============================================================================


@pytest.mark.parametrize(
    "bad_id, reason",
    [
        ("AB", "uppercase + too short"),
        ("1bad", "leading digit"),
        ("foo--bar", "double hyphen"),
        ("a" * 33, "too long"),
    ],
)
def test_unit_04_malformed_vault_id_rejected(tmp_path: Path, bad_id, reason):
    """Malformed vault_id values are rejected by JSON Schema (round-trip with SQLite CHECK)."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "WIKI_SCHEMA.md").write_text(
        f"---\nname: WIKI_SCHEMA\nvault_id: {bad_id}\nschema_version: '2.0'\n"
        f"language: en\nlayout: flat\n---\n"
    )
    with pytest.raises(ConfigValidationError):
        load_config(vault)


# =============================================================================
# TC-UNIT-05 — project override scalar wins
# =============================================================================


def test_unit_05_project_override_wins(minimal_vault: Path):
    """A .wiki.yaml override overlays scalar fields on the root config."""
    override_file = minimal_vault / "_sources" / ".wiki.yaml"
    override_file.write_text("language: ru\n")
    cfg = load_config(minimal_vault / "_sources")
    assert cfg["language"] == "ru"  # override won
    assert cfg["vault_id"] == "minimal-test"  # root field preserved


def test_unit_05b_no_override_uses_root(minimal_vault: Path):
    """Without any .wiki.yaml, root config alone is returned."""
    cfg = load_config(minimal_vault)
    assert cfg["language"] == "en"


def test_unit_05c_find_project_root_returns_none_when_absent(minimal_vault: Path):
    """find_project_root returns None when no .wiki.yaml exists between cwd and vault."""
    assert find_project_root(minimal_vault / "_sources", minimal_vault) is None


def test_unit_05d_find_project_root_finds_nearest(minimal_vault: Path):
    """find_project_root returns the nearest .wiki.yaml above cwd."""
    sub = minimal_vault / "_sources"
    (sub / ".wiki.yaml").write_text("language: ru\n")
    assert find_project_root(sub, minimal_vault) == sub
