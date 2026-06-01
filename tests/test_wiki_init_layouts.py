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
