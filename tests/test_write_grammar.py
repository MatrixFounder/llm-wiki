"""TASK 040 — config-driven write-grammar (`LayoutConfig.write`); the inverse of the
read-side `paths` grammar. Proves Karpathy is a layout YAML, not a code fork (ADR-007)."""
from __future__ import annotations

import pathlib
import tempfile

import pytest

from scripts.wiki_index.layout_config import WriteGrammar, resolve_layout_config


def _vault(layout: str, override: str | None = None) -> pathlib.Path:
    v = pathlib.Path(tempfile.mkdtemp())
    (v / "WIKI_SCHEMA.md").write_text(f"---\nvault_id: t\nlayout: {layout}\n---\n", encoding="utf-8")
    if override is not None:
        (v / ".wiki").mkdir()
        (v / ".wiki" / "layout.yaml").write_text(override, encoding="utf-8")
    return v


@pytest.mark.parametrize("layout,subdir,fname", [
    ("karpathy", "_sources", "slug"),
    ("obsidian-personal", "", "title"),
    ("dev-project", "", "title"),
    ("cybos", "", "title"),
])
def test_builtin_write_grammar(layout, subdir, fname):
    w = resolve_layout_config(_vault(layout)).write
    assert w.source_subdir == subdir and w.source_filename == fname


def test_default_writegrammar_is_para_legacy():
    # the dataclass/schema default (for a YAML that omits `write:`) is PARA-legacy
    assert WriteGrammar() == WriteGrammar(source_subdir="", source_filename="title")


def test_per_vault_override_is_honored_zero_python():
    # a NEW write-grammar comes from YAML — no Python change (NF-2 / drop-in proof)
    w = resolve_layout_config(_vault(
        "obsidian-personal",
        'write:\n  source_subdir: "_inbox"\n  source_filename: "slug"\n')).write
    assert w.source_subdir == "_inbox" and w.source_filename == "slug"


@pytest.mark.parametrize("bad_subdir", ["../../etc", "..", "a/b", "/abs", ".hidden"])
def test_malicious_source_subdir_rejected_at_load(bad_subdir):
    # critic-security MAJOR: source_subdir is operator config (per-vault override) → it MUST be
    # load-gated to a safe single segment, so a traversal/absolute value never reaches a mkdir.
    from scripts.wiki_index.layout_config import LayoutConfigError
    with pytest.raises(LayoutConfigError):
        resolve_layout_config(_vault(
            "obsidian-personal", f'write:\n  source_subdir: "{bad_subdir}"\n'))


def test_bad_source_filename_rejected_at_load():
    from scripts.wiki_index.layout_config import LayoutConfigError
    with pytest.raises(LayoutConfigError):
        resolve_layout_config(_vault(
            "obsidian-personal", 'write:\n  source_filename: "bogus"\n'))


def test_partial_override_inherits_builtin():
    # overriding only source_subdir leaves source_filename at the built-in (deep-merge)
    w = resolve_layout_config(_vault(
        "karpathy", 'write:\n  source_subdir: "src"\n')).write
    assert w.source_subdir == "src" and w.source_filename == "slug"  # inherited from karpathy.yaml
