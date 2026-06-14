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
    is_two_tier_scaffold,
    layout_choices,
    load_layout_config,
    resolve_alias,
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


# --------------------------------------------------------------------------- #
# TASK 031 / R-031-3 — config-driven layout registry (de-hardcode)
# --------------------------------------------------------------------------- #


def test_layout_choices_from_registry() -> None:
    """`--layout` choices are the built-in `*.yaml` stems ∪ declared aliases —
    derived from config, not a hardcoded Python list."""
    choices = layout_choices()
    assert {"karpathy", "dev-project", "obsidian-personal", "flat", "per-project"} <= set(choices)
    assert choices == sorted(choices)  # deterministic, sorted


def test_is_two_tier_scaffold_from_config() -> None:
    """Replaces the hardcoded `_KARPATHY_LAYOUTS` set: karpathy + its aliases are
    two-tier; existing-tree layouts are not; an unknown name is False."""
    for tt in ("karpathy", "flat", "per-project"):
        assert is_two_tier_scaffold(tt) is True
    for nt in ("dev-project", "obsidian-personal"):
        assert is_two_tier_scaffold(nt) is False
    assert is_two_tier_scaffold("nonesuch") is False
    assert is_two_tier_scaffold("") is False


def test_resolve_alias_parity_with_old_ALIAS() -> None:
    """flat/per-project still resolve to the karpathy grammar (parity with the
    retired `_ALIAS` dict); a stem resolves to itself; unknown passes through."""
    assert resolve_alias("flat") == "karpathy"
    assert resolve_alias("per-project") == "karpathy"
    assert resolve_alias("karpathy") == "karpathy"
    assert resolve_alias("dev-project") == "dev-project"
    assert resolve_alias("nonesuch") == "nonesuch"


def test_dropin_new_layout_appears_zero_python(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R-031-3 / arch-review 🟡-1: a NEW built-in layout YAML is a pure drop-in —
    it appears in `layout_choices()` with no Python edit. Proves (a) the registry
    re-globs each call (a new file is seen) and (b) `_reset_registry_cache()`
    provides clean test isolation (no stale-list leak across tests)."""
    import scripts.wiki_index.layout_config as lc

    fake = tmp_path / "layouts"
    fake.mkdir()
    monkeypatch.setattr(lc, "LAYOUTS_DIR", fake)
    lc._reset_registry_cache()
    assert lc.layout_choices() == []  # empty dir → no choices (purely glob-driven)

    probe = fake / "zz-probe.yaml"
    probe.write_text(
        "layout: zz-probe\naliases: [zz-alias]\ninit_scaffold: none\n", encoding="utf-8"
    )
    # seen WITHOUT a manual reset — the registry re-globs each call
    assert "zz-probe" in lc.layout_choices()
    assert "zz-alias" in lc.layout_choices()
    assert lc.resolve_alias("zz-alias") == "zz-probe"
    assert lc.is_two_tier_scaffold("zz-probe") is False

    probe.unlink()
    lc._reset_registry_cache()
    assert "zz-probe" not in lc.layout_choices()  # removal reflected; cache cleared


def test_registry_mtime_refresh_on_content_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The parse-once cache refreshes when a file's mtime changes (correctness
    over the perf optimisation)."""
    import os
    import scripts.wiki_index.layout_config as lc

    fake = tmp_path / "layouts"
    fake.mkdir()
    monkeypatch.setattr(lc, "LAYOUTS_DIR", fake)
    lc._reset_registry_cache()
    probe = fake / "zz-mt.yaml"
    probe.write_text("layout: zz-mt\ninit_scaffold: none\n", encoding="utf-8")
    os.utime(probe, (1000, 1000))
    assert lc.is_two_tier_scaffold("zz-mt") is False
    probe.write_text("layout: zz-mt\ninit_scaffold: two-tier\n", encoding="utf-8")
    os.utime(probe, (2000, 2000))  # distinct mtime → cache refresh
    assert lc.is_two_tier_scaffold("zz-mt") is True


def test_cybos_config_loads_and_validates(tmp_path: Path) -> None:
    """TASK 031 / R-031-2 / AC-2.1: the new built-in cybos layout schema-validates,
    loads, and carries the 7 knowledge-class folders + the engineering spine."""
    cfg = _load(tmp_path, "cybos")
    assert cfg.layout == "cybos"
    assert cfg.slug_strategy == "transliterate"
    assert is_two_tier_scaffold("cybos") is False
    globs = {p.glob for p in cfg.paths}
    for folder in ("decisions", "requirements", "risks", "incidents",
                   "hypotheses", "facts", "events"):
        assert f"{folder}/**/*.md" in globs, f"cybos missing {folder} glob"
    assert set(cfg.type_mapping) == {
        "decision", "requirement", "risk", "incident", "hypothesis", "fact",
        "event", "task", "adr", "plan",
    }
    # ref extraction: wiki-link + markdown-link + id-ref (built-in → stdlib re)
    assert {r.kind for r in cfg.ref_extraction} == {"wiki-link", "markdown-link", "id-ref"}
    assert cfg.frontmatter_synthesis.get("enabled") is True


# --------------------------------------------------------------------------- #
# TASK 031 / R-031-3 — registry robustness guards (vdd-multi LOW-1 + LOW-2)
# --------------------------------------------------------------------------- #


def _fake_layouts(tmp_path: Path, files: dict[str, str], monkeypatch: pytest.MonkeyPatch):
    import scripts.wiki_index.layout_config as lc
    fake = tmp_path / "layouts"
    fake.mkdir()
    for name, body in files.items():
        (fake / name).write_text(body, encoding="utf-8")
    monkeypatch.setattr(lc, "LAYOUTS_DIR", fake)
    lc._reset_registry_cache()
    return lc


def test_registry_rejects_duplicate_alias(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """vdd-multi LOW-1: two built-ins declaring the SAME alias would resolve
    glob-order-dependently — caught loudly at registry build instead."""
    lc = _fake_layouts(tmp_path, {
        "zz-b.yaml": "layout: zz-b\naliases: [dup]\n",
        "zz-c.yaml": "layout: zz-c\naliases: [dup]\n",
    }, monkeypatch)
    with pytest.raises(LayoutConfigError, match="declared by both"):
        lc.layout_choices()


def test_registry_rejects_alias_shadowing_stem(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """vdd-multi LOW-1: an alias that equals another layout's stem is ambiguous."""
    lc = _fake_layouts(tmp_path, {
        "zz-a.yaml": "layout: zz-a\n",
        "zz-b.yaml": "layout: zz-b\naliases: [zz-a]\n",
    }, monkeypatch)
    with pytest.raises(LayoutConfigError, match="shadows built-in"):
        lc.resolve_alias("zz-a")


def test_registry_rejects_non_list_aliases(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """vdd-multi LOW-2: a bare-string `aliases` would iterate into per-character
    aliases — rejected loudly instead of silently corrupting the choice set."""
    lc = _fake_layouts(tmp_path, {"zz.yaml": "layout: zz\naliases: flat\n"}, monkeypatch)
    with pytest.raises(LayoutConfigError, match="`aliases` must be a list"):
        lc.layout_choices()


def test_registry_rejects_bad_init_scaffold(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """vdd-multi LOW-2: an unknown `init_scaffold` value is rejected (not coerced)."""
    lc = _fake_layouts(tmp_path, {"zz.yaml": "layout: zz\ninit_scaffold: bogus\n"}, monkeypatch)
    with pytest.raises(LayoutConfigError, match="init_scaffold"):
        lc.is_two_tier_scaffold("zz")
