"""Smoke tests for scripts/benchmark.py (task-001-33).

CI does NOT enforce SLOs by default (machine-specific). Tests assert harness
correctness only.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.benchmark import (
    generate_synthetic_vault,
    measure,
    run_multivault_scaling,
    run_suite,
)


def test_unit_01_synthetic_vault_page_count(tmp_path):
    """generate_synthetic_vault produces N source pages + WIKI_SCHEMA.md."""
    generate_synthetic_vault(tmp_path, "bench-v", 25)
    sources = list((tmp_path / "_sources").glob("page-*.md"))
    assert len(sources) == 25
    assert (tmp_path / "WIKI_SCHEMA.md").is_file()
    # frontmatter parseable
    txt = sources[0].read_text()
    assert txt.startswith("---\n")


def test_unit_02_synthetic_deterministic_with_seed(tmp_path):
    """Same seed → identical file contents."""
    a = tmp_path / "a"
    b = tmp_path / "b"
    generate_synthetic_vault(a, "v-a", 10, seed=1)
    generate_synthetic_vault(b, "v-b", 10, seed=1)
    # WIKI_SCHEMA differs (vault_id), but page bodies depend only on i + seed
    for i in range(10):
        ap = (a / "_sources" / f"page-{i:04d}.md").read_text()
        bp = (b / "_sources" / f"page-{i:04d}.md").read_text()
        assert ap == bp


def test_unit_03_measure_returns_expected_keys():
    stats = measure("noop", lambda: None, runs=3)
    for k in ("op", "runs", "min_ms", "p50_ms", "p95_ms", "max_ms"):
        assert k in stats
    assert stats["op"] == "noop"
    assert stats["runs"] == 3


@pytest.mark.slow
def test_e2e_01_suite_runs_to_completion_100(capsys):
    """N=100 suite produces JSON, exits cleanly."""
    ok = run_suite(100, enforce_slos=False)
    assert ok is True or ok is False  # any value fine, just no exception
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["n_pages"] == 100
    ops = {r["op"] for r in payload["results"]}
    assert {"wiki-search", "wiki-index-upsert", "wiki-index-render",
            "wiki-lint", "wiki-reindex-full", "wiki-reindex-delta"} <= ops


@pytest.mark.slow
def test_e2e_02_multivault_scaling_smoke(capsys):
    """Multi-vault smoke: 2 vaults × 20 pages."""
    ok = run_multivault_scaling(2, 20)
    assert ok is True
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["n_vaults"] == 2


@pytest.mark.slow
def test_e2e_03_cli_invocation(tmp_path):
    """CLI exit 0 with --n 50."""
    output = tmp_path / "bench.json"
    result = subprocess.run(
        [sys.executable, "-m", "scripts.benchmark",
         "--n", "50", "--output", str(output)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(output.read_text())
    assert payload["n_pages"] == 50
