"""CLI scaffold tests for scripts/wiki_skills/* (task-001-08).

Each scaffold is invoked two ways:
1. As `python -m scripts.wiki_skills.<name>` (E2E shell path).
2. Via `main(argv)` direct call (programmatic; faster, used by harness).

Both paths MUST produce identical JSON output.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys

import pytest


SKILL_MODULES = [
    # ALL skills are now IMPLEMENTED beyond Stage 1:
    #   wiki_init        → tests/test_wiki_init_flows.py (001-21..23)
    #   wiki_index_upsert → tests/test_wiki_index_upsert.py (001-25)
    #   wiki_index_render → tests/test_wiki_index_render.py (001-26)
    #   wiki_append_log  → tests/test_wiki_append_log.py (001-27)
    #   wiki_search      → tests/test_wiki_search_lint_cli.py (001-28)
    #   wiki_lint        → tests/test_wiki_search_lint_cli.py (001-29)
    # Stage 1 stub-scaffold tests are obsolete and skipped (empty parametrize).
]


@pytest.mark.parametrize("module, args", SKILL_MODULES)
def test_e2e_01_skill_module_invocation(module, args):
    """Each scaffold invokable via `python -m`; emits valid JSON with action='stub'."""
    result = subprocess.run(
        [sys.executable, "-m", f"scripts.wiki_skills.{module}", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"{module} exited {result.returncode}: {result.stderr}"
    data = json.loads(result.stdout)
    assert data["action"] == "stub"
    assert "skill" in data


@pytest.mark.parametrize("module, args", SKILL_MODULES)
def test_e2e_01b_skill_main_direct_call(module, args, capsys):
    """`main(argv)` direct call works (used by harness)."""
    mod = __import__(f"scripts.wiki_skills.{module}", fromlist=["main"])
    exit_code = mod.main(args)
    assert exit_code == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["action"] == "stub"


@pytest.mark.parametrize("module", [m for m, _ in SKILL_MODULES])
def test_unit_01_argparse_rejects_bogus_flag(module):
    """argparse exits 2 on unknown flag (Python convention)."""
    result = subprocess.run(
        [sys.executable, "-m", f"scripts.wiki_skills.{module}", "--bogus-flag-xyz"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2


# test_unit_02_wiki_search_passes_query_through — REMOVED.
# wiki_search is no longer a stub (001-28 IMPLEMENTED). Real query tests
# live in tests/test_wiki_search_lint_cli.py.


# test_unit_02b_wiki_init_modes_distinguished — REMOVED. wiki_init is no longer
# a stub; mode-distinction tests live in tests/test_wiki_init_flows.py.
