"""TASK 012-13 (R-X2.1) — wiki-init --layout flag (5 values; no stray scaffold)."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.wiki_index.config_loader import load_root_config
from scripts.wiki_index.layout_config import resolve_layout_config
from scripts.wiki_skills.wiki_init import main as init_main


@pytest.mark.parametrize("layout", ["flat", "per-project", "karpathy", "dev-project", "obsidian-personal"])
def test_all_five_layouts_accepted(tmp_path: Path, layout: str) -> None:
    vault = tmp_path / "v"
    db = tmp_path / "g.db"
    rc = init_main(["--scaffold-new", "--vault", str(vault), "--vault-id", "test-vault",
                    "--layout", layout, "--db-path", str(db)])
    assert rc == 0
    # WIKI_SCHEMA.md carries the chosen layout
    assert load_root_config(vault)["layout"] == layout
    # the engine resolves the matching built-in (flat/per-project → karpathy alias)
    cfg = resolve_layout_config(vault)
    expected = "karpathy" if layout in ("flat", "per-project") else layout
    assert cfg.layout == expected


def test_dev_project_does_not_scaffold_karpathy_dirs(tmp_path: Path) -> None:
    vault = tmp_path / "dv"
    init_main(["--scaffold-new", "--vault", str(vault), "--vault-id", "dev-vault",
               "--layout", "dev-project", "--db-path", str(tmp_path / "g.db")])
    # NO stray Karpathy page-subdirs scaffolded into a dev-vault
    assert not (vault / "_sources").exists()
    assert not (vault / "_concepts").exists()
    assert not (vault / "00-Vault-Index").exists()
    assert (vault / "WIKI_SCHEMA.md").is_file()  # but the schema + registration happened


def test_karpathy_still_scaffolds_page_subdirs(tmp_path: Path) -> None:
    vault = tmp_path / "kv"
    init_main(["--scaffold-new", "--vault", str(vault), "--vault-id", "karp-vault",
               "--layout", "per-project", "--db-path", str(tmp_path / "g.db")])
    assert (vault / "_sources").is_dir()
    assert (vault / "_concepts").is_dir()
    assert (vault / "00-Vault-Index").is_dir()


# --------------------------------------------------------------------------- #
# TASK 025 / R-5 — layout-aware CLAUDE.md agent template
# --------------------------------------------------------------------------- #


def test_obsidian_personal_writes_layout_aware_claude_md(tmp_path: Path) -> None:
    """obsidian-personal (an existing-tree layout) must get the layout-aware CLAUDE.md,
    NOT the Karpathy three-layer/_sources/global.db template."""
    vault = tmp_path / "pv"
    init_main(["--scaffold-new", "--vault", str(vault), "--vault-id", "para-vault",
               "--layout", "obsidian-personal", "--db-path", str(tmp_path / "g.db")])
    text = (vault / "CLAUDE.md").read_text(encoding="utf-8")
    assert "existing-tree" in text and ".wiki/sync.yaml" in text  # layout template markers
    assert "The three layers" not in text   # Karpathy-only section header absent
    assert "global.db" not in text          # no hardcoded DB delete


def test_karpathy_claude_md_drops_hardcoded_global_db_rm(tmp_path: Path) -> None:
    """R-5a: the Karpathy template keeps its three layers but no longer hardcodes
    `rm …/global.db` in the rebuild step."""
    vault = tmp_path / "kv2"
    init_main(["--scaffold-new", "--vault", str(vault), "--vault-id", "karp2-vault",
               "--layout", "karpathy", "--db-path", str(tmp_path / "g.db")])
    text = (vault / "CLAUDE.md").read_text(encoding="utf-8")
    assert "_sources/" in text                       # still the Karpathy template
    assert 'rm "' not in text and "global.db" not in text  # the hardcoded rm is gone


def test_gemini_vendor_also_gets_layout_template(tmp_path: Path) -> None:
    """R-5 (arch Q-025-3 / gate 🟢-1): the layout switch is layout-driven, not
    vendor-driven — a non-Karpathy layout gives EVERY selected vendor the layout
    template (GEMINI.md written, not silently errored)."""
    vault = tmp_path / "gv"
    rc = init_main(["--scaffold-new", "--vault", str(vault), "--vault-id", "gem-vault",
                    "--layout", "obsidian-personal", "--vendor", "gemini",
                    "--db-path", str(tmp_path / "g.db")])
    assert rc == 0
    gemini = vault / "GEMINI.md"
    assert gemini.is_file(), "GEMINI.md not written (KeyError→silent error?)"
    text = gemini.read_text(encoding="utf-8")
    assert "existing-tree" in text and "The three layers" not in text


# --------------------------------------------------------------------------- #
# TASK 031 / R-031-3 — --layout choices sourced from the built-in registry
# --------------------------------------------------------------------------- #


def test_wiki_init_rejects_unknown_layout(tmp_path: Path) -> None:
    """`--layout` choices come from the config-driven registry (layout_choices());
    an unknown value is rejected by argparse (SystemExit 2), not silently accepted."""
    with pytest.raises(SystemExit):
        init_main(["--scaffold-new", "--vault", str(tmp_path / "v"),
                   "--vault-id", "x-vault", "--layout", "nonesuch",
                   "--db-path", str(tmp_path / "g.db")])
