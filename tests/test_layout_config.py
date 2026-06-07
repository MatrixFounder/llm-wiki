"""TASK 012-01 (PW-A) — layout-config loader + schema + built-in karpathy.yaml.

The load-bearing test is `test_karpathy_config_matches_layout_constants`: it ties
the built-in `karpathy.yaml` to `layout.py` + `normalization.py` so the
byte-identity projection can never silently drift.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.wiki_index.layout import (
    COURSE_TIER_DIR,
    PAGE_SUBDIRS,
    VAULT_TIER_PROJECT,
)
from scripts.wiki_index.layout_config import (
    LayoutConfig,
    LayoutConfigError,
    PathEntry,
    load_layout_config,
)
from scripts.wiki_index.normalization import _PATH_TYPE_FALLBACK, TYPE_MAPPING
from scripts.wiki_source.parsing import _WIKILINK_RE


def _vault(tmp_path: Path) -> Path:
    root = tmp_path / "v"
    root.mkdir()
    return root


def _load(tmp_path: Path, layout: str = "karpathy", **extra: object) -> LayoutConfig:
    return load_layout_config(_vault(tmp_path), {"layout": layout, **extra})


# --------------------------------------------------------------------------- #
# The byte-identity invariant
# --------------------------------------------------------------------------- #


def test_karpathy_config_matches_layout_constants(tmp_path: Path) -> None:
    cfg = _load(tmp_path, "karpathy")
    assert cfg.layout == "karpathy"
    assert cfg.slug_strategy == "identity"

    root_entries = {p.glob: p for p in cfg.paths if p.project_pattern is None}
    course_entries = {p.glob: p for p in cfg.paths if p.project_pattern is not None}

    # Root tier: one `{sub}/**/*.md` entry per PAGE_SUBDIRS member, project=_vault_.
    for sub in PAGE_SUBDIRS:
        glob = f"{sub}/**/*.md"
        assert glob in root_entries, f"karpathy.yaml missing root glob {glob}"
        assert root_entries[glob].project == VAULT_TIER_PROJECT

    # Course tier: one `Lessons/*/{sub}/**/*.md` entry per member, pattern on COURSE_TIER_DIR.
    for sub in PAGE_SUBDIRS:
        glob = f"{COURSE_TIER_DIR}/*/{sub}/**/*.md"
        assert glob in course_entries, f"karpathy.yaml missing course glob {glob}"
        entry = course_entries[glob]
        assert entry.project_pattern is not None and COURSE_TIER_DIR in entry.project_pattern
        assert entry.project_template == "${course}"
        assert entry.project_slug_strategy == "course-slug"

    # type_mapping == the live 15-entry TYPE_MAPPING (byte-for-byte).
    assert cfg.type_mapping == TYPE_MAPPING

    # path_type_fallback == _PATH_TYPE_FALLBACK (keyed by subdir name).
    assert cfg.path_type_fallback == _PATH_TYPE_FALLBACK

    # ref_extraction wiki-link pattern == _WIKILINK_RE byte-for-byte.
    assert len(cfg.ref_extraction) == 1
    assert cfg.ref_extraction[0].kind == "wiki-link"
    assert cfg.ref_extraction[0].regex == _WIKILINK_RE.pattern
    assert cfg.ref_extraction[0].target_group == 1

    # Karpathy requires frontmatter (no synthesis).
    assert cfg.frontmatter_synthesis.get("enabled") is False
    assert cfg.auto_indexes == ()


# --------------------------------------------------------------------------- #
# Alias + unknown-name resolution
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("legacy", ["flat", "per-project"])
def test_alias_resolution_to_karpathy(tmp_path: Path, legacy: str) -> None:
    cfg = _load(tmp_path, legacy)
    assert cfg.layout == "karpathy"  # both legacy values map to the karpathy grammar


def test_unknown_layout_name_rejected(tmp_path: Path) -> None:
    with pytest.raises(LayoutConfigError, match="unknown layout"):
        _load(tmp_path, "bogus-layout")


def test_missing_layout_field_rejected(tmp_path: Path) -> None:
    with pytest.raises(LayoutConfigError, match="missing required"):
        load_layout_config(_vault(tmp_path), {})


# --------------------------------------------------------------------------- #
# Per-vault override resolution + schema strictness + path guard
# --------------------------------------------------------------------------- #


def _minimal_override(extra_path_keys: str = "") -> str:
    return (
        "schema_version: '2.0'\n"
        "layout: karpathy\n"
        "slug_strategy: identity\n"
        "paths:\n"
        f"  - {{glob: 'docs/**/*.md', project: '_vault_'{extra_path_keys}}}\n"
        "type_mapping:\n"
        "  summary: {db_type: summary, tag: null}\n"
    )


def test_override_replaces_paths(tmp_path: Path) -> None:
    root = _vault(tmp_path)
    (root / ".wiki").mkdir()
    (root / ".wiki" / "layout.yaml").write_text(_minimal_override(), encoding="utf-8")
    cfg = load_layout_config(root, {"layout": "karpathy"})
    # paths is a list → deep_merge REPLACES it with the override's single entry.
    assert cfg.paths == (PathEntry(glob="docs/**/*.md", project="_vault_"),)


def test_override_unions_ignore(tmp_path: Path) -> None:
    """TASK 019 dogfood fix: `ignore` is ADDITIVE — a per-vault override EXTENDS the
    base ignore set (it does NOT replace it like `paths`), so the built-in
    `.obsidian/**`/`**/*.base` exclusions survive a custom `ignore:`. This makes the
    `wiki-init` CLAUDE.md/WIKI_SCHEMA 'extend `ignore`' guidance true."""
    root = _vault(tmp_path)
    (root / ".wiki").mkdir()
    (root / ".wiki" / "layout.yaml").write_text("ignore:\n  - 'custom/**'\n", encoding="utf-8")
    cfg = load_layout_config(root, {"layout": "obsidian-personal"})
    assert "custom/**" in cfg.ignore          # the override entry is present
    assert ".obsidian/**" in cfg.ignore       # ... AND the base entries are NOT lost
    assert "**/*.base" in cfg.ignore
    # base-first order, deduped, override appended
    assert cfg.ignore[-1] == "custom/**"


def test_schema_rejects_misspelled_pathentry_key(tmp_path: Path) -> None:
    root = _vault(tmp_path)
    (root / ".wiki").mkdir()
    (root / ".wiki" / "layout.yaml").write_text(
        _minimal_override(extra_path_keys=", projct_pattern: 'x'"), encoding="utf-8"
    )
    with pytest.raises(LayoutConfigError, match="validation failed"):
        load_layout_config(root, {"layout": "karpathy"})


def test_explicit_layout_config_pointer_wins(tmp_path: Path) -> None:
    root = _vault(tmp_path)
    (root / "custom").mkdir()
    (root / "custom" / "grammar.yaml").write_text(_minimal_override(), encoding="utf-8")
    cfg = load_layout_config(root, {"layout": "karpathy", "layout_config": "custom/grammar.yaml"})
    assert cfg.paths == (PathEntry(glob="docs/**/*.md", project="_vault_"),)


def test_override_symlink_refused(tmp_path: Path) -> None:
    root = _vault(tmp_path)
    (root / ".wiki").mkdir()
    real = root / ".wiki" / "real-grammar.yaml"
    real.write_text(_minimal_override(), encoding="utf-8")
    link = root / ".wiki" / "layout.yaml"
    link.symlink_to(real)
    with pytest.raises(LayoutConfigError, match="symlink"):
        load_layout_config(root, {"layout": "karpathy"})


def test_missing_explicit_pointer_rejected(tmp_path: Path) -> None:
    root = _vault(tmp_path)
    with pytest.raises(LayoutConfigError, match="does not exist"):
        load_layout_config(root, {"layout": "karpathy", "layout_config": "nope/missing.yaml"})
