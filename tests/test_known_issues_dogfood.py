"""TASK 012-12 (R-X3 dogfood) — post-migration committed-state acceptance.

After the live migration, THIS repo's `docs/KNOWN_ISSUES.md` is the Class-B
auto-rendered ledger (an index), and the Class-A source is the per-issue
`docs/issues/<id>-<slug>.md` files. These tests pin that end state: the per-issue
files exist with valid known-issue frontmatter + non-empty bodies (no data loss),
and the ledger is a generated index (not prose). The splitter's lossless parsing
of the original format is separately pinned by `test_known_issues_splitter.py`
(fixture) + the real-format parse below.
"""

from __future__ import annotations

from pathlib import Path

import frontmatter

DOCS = Path(__file__).parent.parent / "docs"
ISSUES_DIR = DOCS / "issues"
LEDGER = DOCS / "KNOWN_ISSUES.md"


def test_per_issue_files_exist_with_valid_frontmatter() -> None:
    files = [p for p in ISSUES_DIR.glob("*.md") if not p.name.startswith(".")]
    assert len(files) >= 40, f"expected the migrated per-issue files, found {len(files)}"
    for p in files:
        post = frontmatter.load(str(p))
        assert post["type"] == "known-issue", f"{p.name}: not type known-issue"
        assert post.get("id"), f"{p.name}: missing id"
        assert post.get("status"), f"{p.name}: missing status"
        assert post.content.strip(), f"{p.name}: empty body (data loss?)"


def test_ledger_is_generated_index_not_prose() -> None:
    text = LEDGER.read_text(encoding="utf-8")
    assert text.startswith("<!-- GENERATED-AT:"), "ledger is not the auto-generated index"
    assert "# Known Issues" in text
    # the index links to per-issue files; it is NOT the old prose (no `## [date] … [STATUS]`)
    import re
    assert not re.search(r"^##\s+\[\d{4}-\d{2}-\d{2}\].*\[STATUS:", text, re.MULTILINE)


def test_migration_report_present() -> None:
    report = ISSUES_DIR / ".migration-report.md"
    assert report.is_file(), "the PW-G migration report should be committed alongside the issues"
