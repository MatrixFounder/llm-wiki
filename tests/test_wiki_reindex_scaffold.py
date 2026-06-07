"""wiki-reindex flag validation. Real reindex tests live in
tests/test_wiki_reindex_full.py (task-001-30)."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime

import pytest

from scripts.wiki_index.models import Vault
from scripts.wiki_index.sqlite_repository import SQLiteRepository
from scripts.wiki_skills import wiki_reindex


@pytest.mark.parametrize(
    "argv",
    [
        ["--full", "--vault", "x", "--all-vaults"],   # scope mutually exclusive
        ["--full", "--delta", "--vault", "x"],         # mode mutually exclusive
        ["--vault", "x"],                              # missing mode
        ["--full"],                                    # missing scope
    ],
)
def test_unit_01_invalid_combinations_exit_2(argv):
    """argparse rejects invalid flag combinations with exit code 2."""
    result = subprocess.run(
        [sys.executable, "-m", "scripts.wiki_skills.wiki_reindex", *argv],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 2


def _register_two(db_path, tmp_path):
    repo = SQLiteRepository(db_path)
    repo.apply_schema()
    for vid in ("vault-one", "vault-two"):
        root = tmp_path / vid
        root.mkdir()
        repo.register_vault(Vault(
            vault_id=vid, name=vid, root_path=root,
            schema_version="2.0", registered_at=datetime(2026, 5, 26)))
    repo.close()


def test_all_vaults_delta_mode(tmp_path, capsys):
    """TASK 021 (R-021-3): `--all-vaults --delta` honours delta (was silently --full).
    Envelope reports mode=delta + `touched`/`deleted`, NOT `pages_indexed`, and never
    KeyErrors; `slug_collisions` is aggregated."""
    db = str(tmp_path / "g.db")
    _register_two(db, tmp_path)
    rc = wiki_reindex.main(["--all-vaults", "--delta", "--db-path", db])
    assert rc == 0
    env = json.loads(capsys.readouterr().out)
    assert env["mode"] == "delta" and env["scope"] == "all-vaults"
    assert env["vaults_processed"] == 2
    assert "touched" in env and "deleted" in env
    assert "pages_indexed" not in env
    assert env["slug_collisions"] == []


def test_all_vaults_full_mode_unchanged(tmp_path, capsys):
    """`--all-vaults --full` keeps its shape (mode=full, pages_indexed present)."""
    db = str(tmp_path / "g.db")
    _register_two(db, tmp_path)
    rc = wiki_reindex.main(["--all-vaults", "--full", "--db-path", db])
    assert rc == 0
    env = json.loads(capsys.readouterr().out)
    assert env["mode"] == "full" and "pages_indexed" in env
    assert "touched" not in env
