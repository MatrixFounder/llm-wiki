"""TASK 012 — /vdd-multi adversarial-review fix regressions.

Pins the fixes for the critic findings: ledger egress-sanitisation (SEC-1),
splitter code-fence + slug-collision (LOG-3/4), reindex_delta re-render (LOG-1),
project_pattern-without-template rejection (LOG-6).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from scripts.migrate_known_issues_to_files import migrate, parse_issues
from scripts.wiki_index.layout_config import LayoutConfigError, load_layout_config
from scripts.wiki_index.models import Vault
from scripts.wiki_index.reindex import reindex_delta, reindex_full
from scripts.wiki_index.sqlite_repository import SQLiteRepository


def _dev_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "dv"
    (vault / "issues").mkdir(parents=True)
    (vault / "WIKI_SCHEMA.md").write_text(
        '---\nvault_id: dev-vault\nschema_version: "2.0"\nlanguage: en\nlayout: dev-project\n---\n',
        encoding="utf-8")
    return vault


def _repo(tmp_path: Path, vault: Path) -> SQLiteRepository:
    repo = SQLiteRepository(tmp_path / "g.db")
    repo.apply_schema()
    repo.register_vault(Vault(vault_id="dev-vault", name="dev-vault", root_path=vault,
                              schema_version="2.0", registered_at=datetime(2026, 5, 26)))
    return repo


# --------------------------------------------------------------------------- #
# SEC-1 — ledger egress-sanitises untrusted titles
# --------------------------------------------------------------------------- #


def test_ledger_sanitizes_malicious_title(tmp_path: Path) -> None:
    vault = _dev_vault(tmp_path)
    (vault / "issues" / "x-1-evil.md").write_text(
        '---\nid: X-1\ntype: known-issue\nstatus: open\ncategory: logic\n'
        'opened_at: 2026-01-01\ntitle: "pwn]] [[evil-target"\n---\n\nbody\n',
        encoding="utf-8")
    repo = _repo(tmp_path, vault)
    try:
        reindex_full(repo, "dev-vault")
        ledger = (vault / "KNOWN_ISSUES.md").read_text(encoding="utf-8")
        # the injected wikilink target must NOT render as a functional [[evil-target]]
        assert "[[evil-target]]" not in ledger
        # the title's brackets are escaped (rendered literal)
        assert "pwn\\]\\] \\[\\[evil-target" in ledger
        # a title can't smuggle a second GENERATED-AT line past the drift-hash strip
        assert ledger.count("<!-- GENERATED-AT:") == 1
    finally:
        repo.close()


def test_ledger_title_cannot_inject_generated_at_or_custom_block(tmp_path: Path) -> None:
    vault = _dev_vault(tmp_path)
    (vault / "issues" / "x-2-hdr.md").write_text(
        '---\nid: X-2\ntype: known-issue\nstatus: open\ncategory: logic\n'
        'opened_at: 2026-01-01\n'
        'title: "a <!-- BEGIN-CUSTOM:pwn --> x <!-- END-CUSTOM:pwn -->"\n---\n\nbody\n',
        encoding="utf-8")
    repo = _repo(tmp_path, vault)
    try:
        reindex_full(repo, "dev-vault")
        ledger = (vault / "KNOWN_ISSUES.md").read_text(encoding="utf-8")
        # the HTML-comment markers are escaped (&lt;) → cannot hijack the custom-block parser
        assert "<!-- BEGIN-CUSTOM:pwn -->" not in ledger
    finally:
        repo.close()


# --------------------------------------------------------------------------- #
# LOG-3 — splitter honours fenced code blocks (no body truncation)
# --------------------------------------------------------------------------- #


def test_splitter_preserves_fenced_hash_lines() -> None:
    text = (
        "## [2026-01-01] L-1 a logic issue [STATUS: open]\n\n"
        "- **Symptom**: x.\n\n"
        "```bash\n## not a section — inside a fence\nrm -rf y\n```\n\n"
        "- **Fix plan**: z.\n\n"
        "## Some section header\n\n"
        "## [2026-01-02] L-2 next [STATUS: open]\n\n- **Symptom**: y.\n"
    )
    issues = {i.id: i for i in parse_issues(text)}
    assert set(issues) == {"L-1", "L-2"}
    body = issues["L-1"].body
    assert "## not a section" in body      # fenced ## preserved
    assert "- **Fix plan**: z." in body    # body after the fence NOT truncated


# --------------------------------------------------------------------------- #
# LOG-4 — splitter detects slug collisions (no silent overwrite)
# --------------------------------------------------------------------------- #


def test_splitter_disambiguates_slug_collision(tmp_path: Path) -> None:
    text = (
        "## [2026-01-01] A-1 same title [STATUS: open]\n\n- **Symptom**: first.\n\n"
        "## [2026-01-02] A-1 same title [STATUS: open]\n\n- **Symptom**: second.\n"
    )
    vault = tmp_path / "v"
    (vault / "docs").mkdir(parents=True)
    (vault / "docs" / "KNOWN_ISSUES.md").write_text(text, encoding="utf-8")
    result = migrate(vault, vault / "docs" / "KNOWN_ISSUES.md")
    files = sorted(p.name for p in (vault / "docs" / "issues").glob("*.md")
                   if not p.name.startswith("."))
    assert len(files) == 2                          # both written (no overwrite)
    assert any(f.endswith("-2.md") for f in files)  # the 2nd disambiguated
    assert result["issues"] == 2
    # the collision is flagged for review in the report
    report = (vault / "docs" / "issues" / ".migration-report.md").read_text(encoding="utf-8")
    assert "collision" in report


# --------------------------------------------------------------------------- #
# LOG-1 — reindex_delta re-renders the ledger
# --------------------------------------------------------------------------- #


def test_delta_rerenders_ledger(tmp_path: Path) -> None:
    vault = _dev_vault(tmp_path)
    (vault / "issues" / "p-1-a.md").write_text(
        '---\nid: P-1\ntype: known-issue\nstatus: open\ncategory: performance\n'
        'opened_at: 2026-01-01\n---\n\n# Perf A\n\nbody\n', encoding="utf-8")
    repo = _repo(tmp_path, vault)
    try:
        reindex_full(repo, "dev-vault")
        assert "P-1" in (vault / "KNOWN_ISSUES.md").read_text(encoding="utf-8")
        # add a new issue, then DELTA reindex — the ledger must update
        import time
        time.sleep(0.01)
        (vault / "issues" / "p-2-b.md").write_text(
            '---\nid: P-2\ntype: known-issue\nstatus: open\ncategory: performance\n'
            'opened_at: 2026-01-02\n---\n\n# Perf B\n\nbody\n', encoding="utf-8")
        result = reindex_delta(repo, "dev-vault")
        assert "KNOWN_ISSUES.md" in result["auto_rendered"]
        assert "P-2" in (vault / "KNOWN_ISSUES.md").read_text(encoding="utf-8")
    finally:
        repo.close()


# --------------------------------------------------------------------------- #
# LOG-6 — project_pattern without project_template rejected at load
# --------------------------------------------------------------------------- #


def test_project_pattern_without_template_rejected(tmp_path: Path) -> None:
    root = tmp_path / "v"; root.mkdir()
    (root / ".wiki").mkdir()
    (root / ".wiki" / "layout.yaml").write_text(
        "schema_version: '2.0'\nlayout: karpathy\nslug_strategy: identity\n"
        "type_mapping:\n  note: {db_type: summary, tag: null}\n"
        "paths:\n  - {glob: 'x/**/*.md', project_pattern: '^(?P<a>[^/]+)/'}\n",
        encoding="utf-8")
    with pytest.raises(LayoutConfigError, match="requires a project_template"):
        load_layout_config(root, {"layout": "karpathy"})
