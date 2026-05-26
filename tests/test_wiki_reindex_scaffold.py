"""wiki-reindex flag validation. Real reindex tests live in
tests/test_wiki_reindex_full.py (task-001-30)."""

from __future__ import annotations

import subprocess
import sys

import pytest


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
