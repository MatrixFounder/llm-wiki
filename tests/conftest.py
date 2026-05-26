"""Shared pytest fixtures for the wiki-index test suite.

Conventions per tests/.AGENTS.md:
- Fixtures live in this file (shared across tests/) or in subdir conftest.py
  (scoped).
- Vault fixtures copy from tests/fixtures/<name>/ to tmp_path on every use
  so individual tests can mutate the tree without polluting siblings.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

import pytest

from scripts.wiki_index.repository import IndexRepository
from scripts.wiki_index.sqlite_repository import SQLiteRepository

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def run_skill_cli(skill_name: str, args: list[str]) -> dict[str, Any]:
    """Spawn `python -m scripts.wiki_skills.<skill_name> <args...>`; parse JSON.

    Raises AssertionError if exit code != 0.
    """
    result = subprocess.run(
        [sys.executable, "-m", f"scripts.wiki_skills.{skill_name}", *args],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, (
        f"{skill_name} exit {result.returncode}; stderr={result.stderr!r}"
    )
    return json.loads(result.stdout)


@pytest.fixture
def minimal_vault(tmp_path: Path) -> Path:
    """Copy of tests/fixtures/minimal-vault/ to a tmp dir; safe to mutate."""
    dst = tmp_path / "minimal-vault"
    shutil.copytree(FIXTURES_DIR / "minimal-vault", dst)
    return dst


@pytest.fixture
def multi_vault(tmp_path: Path) -> dict[str, Path]:
    """Both vault-alpha and vault-beta copied to tmp; returns {vault_id: path}."""
    src_root = FIXTURES_DIR / "multi-vault"
    dst_root = tmp_path / "multi-vault"
    shutil.copytree(src_root, dst_root)
    return {
        "vault-alpha": dst_root / "vault-alpha",
        "vault-beta": dst_root / "vault-beta",
    }


@pytest.fixture
def repo_factory(tmp_path: Path) -> Callable[[], IndexRepository]:
    """Factory returning a fresh SQLiteRepository for each call.

    Each call creates a unique DB path under `tmp_path` so tests that need
    multiple isolated repos can do so. Once task-001-15 lands, calling
    methods on the returned repo will hit real SQL; until then they raise
    NotImplementedError per task-001-04.
    """
    counter = {"n": 0}

    def _make() -> IndexRepository:
        counter["n"] += 1
        return SQLiteRepository(tmp_path / f"wiki-{counter['n']}.db")

    return _make
