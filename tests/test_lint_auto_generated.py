"""TASK 012-10 (PW-Q) — wiki-lint auto-generated ledger drift guard."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from scripts.wiki_index.lint import check_auto_generated_unchanged, run_all_checks
from scripts.wiki_index.models import Vault
from scripts.wiki_index.reindex import reindex_full
from scripts.wiki_index.sqlite_repository import SQLiteRepository

_ISSUE = "---\nid: P-1\ntype: known-issue\nstatus: open\ncategory: performance\nseverity: SEV-1\nopened_at: 2026-01-01\n---\n\n# Perf One\n\nbody\n"


def _make(tmp_path: Path) -> tuple[SQLiteRepository, Path]:
    vault = tmp_path / "dev-vault"
    (vault / "issues").mkdir(parents=True)
    (vault / "WIKI_SCHEMA.md").write_text(
        '---\nvault_id: dev-vault\nschema_version: "2.0"\nlanguage: en\nlayout: dev-project\n---\n',
        encoding="utf-8")
    (vault / "issues" / "p-1-perf.md").write_text(_ISSUE, encoding="utf-8")
    repo = SQLiteRepository(tmp_path / "g.db")
    repo.apply_schema()
    repo.register_vault(Vault(vault_id="dev-vault", name="dev-vault", root_path=vault,
                              schema_version="2.0", registered_at=datetime(2026, 5, 26)))
    reindex_full(repo, "dev-vault")  # renders the ledger
    return repo, vault


def test_clean_ledger_no_drift(tmp_path: Path) -> None:
    repo, vault = _make(tmp_path)
    try:
        issues = check_auto_generated_unchanged(repo, "dev-vault", vault)
        assert issues == []
    finally:
        repo.close()


def test_hand_edit_flagged(tmp_path: Path) -> None:
    repo, vault = _make(tmp_path)
    try:
        ledger = vault / "KNOWN_ISSUES.md"
        ledger.write_text(ledger.read_text(encoding="utf-8") + "\nhand-added line\n",
                          encoding="utf-8")
        issues = check_auto_generated_unchanged(repo, "dev-vault", vault)
        assert len(issues) == 1
        assert issues[0].category == "auto-generated-drift"
        assert "KNOWN_ISSUES.md" in issues[0].details["path"]
        # surfaced through run_all_checks too
        all_issues = run_all_checks(repo, vaults=["dev-vault"])
        assert any(i.category == "auto-generated-drift" for i in all_issues)
    finally:
        repo.close()


def test_generated_at_header_change_not_flagged(tmp_path: Path) -> None:
    """Only the body matters — a differing GENERATED-AT timestamp is not drift."""
    repo, vault = _make(tmp_path)
    try:
        ledger = vault / "KNOWN_ISSUES.md"
        text = ledger.read_text(encoding="utf-8")
        swapped = text.replace(text.splitlines()[0],
                               "<!-- GENERATED-AT: 1999-01-01T00:00:00 by wiki-index-render --auto-indexes -->")
        ledger.write_text(swapped, encoding="utf-8")
        assert check_auto_generated_unchanged(repo, "dev-vault", vault) == []
    finally:
        repo.close()


def test_custom_block_edit_not_flagged(tmp_path: Path) -> None:
    from scripts.wiki_index.layout_config import resolve_layout_config
    from scripts.wiki_index.rendering import render_and_write_auto_indexes

    repo, vault = _make(tmp_path)
    try:
        ledger = vault / "KNOWN_ISSUES.md"
        # add a custom block, then re-render so it lands in its canonical position
        ledger.write_text(
            ledger.read_text(encoding="utf-8")
            + "\n<!-- BEGIN-CUSTOM:notes -->\nmy notes\n<!-- END-CUSTOM:notes -->\n",
            encoding="utf-8")
        layout = resolve_layout_config(vault)
        render_and_write_auto_indexes(repo, "dev-vault", vault, layout, generated_at="X")
        assert check_auto_generated_unchanged(repo, "dev-vault", vault) == []  # canonical → clean
        # now EDIT inside the custom block — still preserved on re-render → not drift
        ledger.write_text(ledger.read_text(encoding="utf-8").replace("my notes", "edited notes"),
                          encoding="utf-8")
        assert check_auto_generated_unchanged(repo, "dev-vault", vault) == []
    finally:
        repo.close()


def test_karpathy_vault_no_auto_index_no_op(tmp_path: Path) -> None:
    vault = tmp_path / "kv"
    (vault / "_sources").mkdir(parents=True)
    repo = SQLiteRepository(tmp_path / "k.db")
    repo.apply_schema()
    repo.register_vault(Vault(vault_id="karp-vault", name="karp-vault", root_path=vault,
                              schema_version="2.0", registered_at=datetime(2026, 5, 26)))
    try:
        assert check_auto_generated_unchanged(repo, "karp-vault", vault) == []
    finally:
        repo.close()
