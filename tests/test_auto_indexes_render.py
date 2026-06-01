"""TASK 012-09 (PW-H, tdd-strict) — auto_indexes[] render engine.

The §D8 rebuildability keystone: the rendered ledger is a pure deterministic
function of the Class-A per-issue pages (only the GENERATED-AT header line is
volatile), stably ordered with an `id` tiebreaker, with a sha256 pinned in
.wiki/state.json and BEGIN-CUSTOM blocks preserved.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from scripts.wiki_index.models import Vault
from scripts.wiki_index.reindex import reindex_full
from scripts.wiki_index.rendering import (
    auto_index_body_sha,
    render_and_write_auto_indexes,
    render_auto_index,
)
from scripts.wiki_index.layout_config import resolve_layout_config
from scripts.wiki_index.security import PathTraversalError
from scripts.wiki_index.sqlite_repository import SQLiteRepository

_ISSUE = "---\nid: {id}\ntype: known-issue\nstatus: open\ncategory: {cat}\nseverity: {sev}\nopened_at: {opened}\n---\n\n# {title}\n\nbody\n"


def _dev_vault(tmp_path: Path, issues: list[dict[str, str]]) -> Path:
    vault = tmp_path / "dev-vault"
    (vault / "issues").mkdir(parents=True)
    (vault / "WIKI_SCHEMA.md").write_text(
        '---\nvault_id: dv\nschema_version: "2.0"\nlanguage: en\nlayout: dev-project\n---\n',
        encoding="utf-8")
    for iss in issues:
        (vault / "issues" / f"{iss['id'].lower()}-{iss['slug']}.md").write_text(
            _ISSUE.format(id=iss["id"], cat=iss["cat"], sev=iss["sev"],
                          opened=iss["opened"], title=iss["title"]),
            encoding="utf-8")
    return vault


def _make(tmp_path: Path, issues: list[dict[str, str]]) -> tuple[SQLiteRepository, Path]:
    vault = _dev_vault(tmp_path, issues)
    repo = SQLiteRepository(tmp_path / "g.db")
    repo.apply_schema()
    repo.register_vault(Vault(vault_id="dev-vault", name="dev-vault", root_path=vault,
                              schema_version="2.0", registered_at=datetime(2026, 5, 26)))
    return repo, vault


_ISSUES = [
    {"id": "P-1", "slug": "perf-a", "cat": "performance", "sev": "SEV-1", "opened": "2026-01-01", "title": "Perf A"},
    {"id": "L-2", "slug": "logic-b", "cat": "logic", "sev": "SEV-2", "opened": "2026-01-02", "title": "Logic B"},
    {"id": "P-3", "slug": "perf-c", "cat": "performance", "sev": "SEV-1", "opened": "2026-01-01", "title": "Perf C"},
]


def test_reindex_renders_ledger_and_pins_state(tmp_path: Path) -> None:
    repo, vault = _make(tmp_path, _ISSUES)
    try:
        result = reindex_full(repo, "dev-vault")
        assert "KNOWN_ISSUES.md" in result["auto_rendered"]
        ledger = (vault / "KNOWN_ISSUES.md").read_text(encoding="utf-8")
        assert ledger.startswith("<!-- GENERATED-AT:")
        assert "## performance" in ledger and "## logic" in ledger
        assert "**P-1**" in ledger and "**L-2**" in ledger
        # state.json pinned the header-stripped sha
        state = (vault / ".wiki" / "state.json").read_text(encoding="utf-8")
        assert auto_index_body_sha(ledger) in state
    finally:
        repo.close()


def test_rebuildability_byte_identical_modulo_header(tmp_path: Path) -> None:
    """Delete the ledger + re-render → byte-identical except the GENERATED-AT line."""
    repo, vault = _make(tmp_path, _ISSUES)
    try:
        reindex_full(repo, "dev-vault")
        first = (vault / "KNOWN_ISSUES.md").read_text(encoding="utf-8")
        (vault / "KNOWN_ISSUES.md").unlink()
        layout = resolve_layout_config(vault)
        render_and_write_auto_indexes(repo, "dev-vault", vault, layout,
                                      generated_at="DIFFERENT-TIMESTAMP")
        second = (vault / "KNOWN_ISSUES.md").read_text(encoding="utf-8")
        assert first != second                                  # header differs
        assert auto_index_body_sha(first) == auto_index_body_sha(second)  # body identical
    finally:
        repo.close()


def test_render_is_deterministic_and_id_tiebroken(tmp_path: Path) -> None:
    """Two issues equal on (severity, opened_at) order by `id` — independent of
    input order (architecture-review M2)."""
    repo, vault = _make(tmp_path, _ISSUES)
    try:
        reindex_full(repo, "dev-vault")
        layout = resolve_layout_config(vault)
        ai = layout.auto_indexes[0]
        a = render_auto_index(repo, "dev-vault", ai, generated_at="X")
        b = render_auto_index(repo, "dev-vault", ai, generated_at="X")
        assert a == b
        # P-1 and P-3 share (SEV-1, 2026-01-01) → P-1 before P-3 (id tiebreaker)
        assert a.index("**P-1**") < a.index("**P-3**")
    finally:
        repo.close()


def test_preserve_custom_block(tmp_path: Path) -> None:
    repo, vault = _make(tmp_path, _ISSUES)
    try:
        reindex_full(repo, "dev-vault")
        ledger = vault / "KNOWN_ISSUES.md"
        body = ledger.read_text(encoding="utf-8")
        ledger.write_text(
            body + "\n<!-- BEGIN-CUSTOM:notes -->\nhand notes\n<!-- END-CUSTOM:notes -->\n",
            encoding="utf-8")
        reindex_full(repo, "dev-vault")  # re-render
        assert "BEGIN-CUSTOM:notes" in ledger.read_text(encoding="utf-8")
    finally:
        repo.close()


def test_output_path_traversal_refused(tmp_path: Path) -> None:
    repo, vault = _make(tmp_path, _ISSUES)
    try:
        reindex_full(repo, "dev-vault")
        layout = resolve_layout_config(vault)
        bad = layout.auto_indexes[0] | {"output": "../../escape.md"}
        from dataclasses import replace
        evil = replace(layout, auto_indexes=(bad,))
        with pytest.raises(PathTraversalError):
            render_and_write_auto_indexes(repo, "dev-vault", vault, evil, generated_at="X")
    finally:
        repo.close()
