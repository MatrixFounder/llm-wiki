"""TASK 012-11 (PW-G, tdd-strict) — KNOWN_ISSUES splitter + partial-confidence report.

Acceptance bar: parse THIS repo's ledger format into per-issue Class-A files with
correct frontmatter + verbatim body, no data loss (count parity), and flag
low-confidence parses (unknown id-prefix / unusual status) in the report.
"""

from __future__ import annotations

from pathlib import Path

import frontmatter

from scripts.migrate_known_issues_to_files import migrate, parse_issues

FIXTURE = Path(__file__).parent / "fixtures" / "known_issues_migration" / "input.md"


def test_parse_skips_example_and_section_headers() -> None:
    issues = parse_issues(FIXTURE.read_text(encoding="utf-8"))
    ids = [i.id for i in issues]
    # the `[YYYY-MM-DD]` format example + all `## <section>` headers are NOT issues
    assert ids == ["L-1", "P-1", "P-6", "DF-2", "ZZ-9"]


def test_status_severity_category_derivation() -> None:
    by_id = {i.id: i for i in parse_issues(FIXTURE.read_text(encoding="utf-8"))}
    assert by_id["L-1"].status == "fixed" and by_id["L-1"].category == "logic"
    assert by_id["P-1"].status == "open" and by_id["P-1"].category == "performance"
    assert by_id["P-6"].severity == "SEV-2"          # parsed from "open, SEV-2"
    assert by_id["DF-2"].status == "by-design" and by_id["DF-2"].category == "dogfood"
    assert by_id["ZZ-9"].category == "uncategorized"  # unknown prefix


def test_body_preserved_verbatim() -> None:
    by_id = {i.id: i for i in parse_issues(FIXTURE.read_text(encoding="utf-8"))}
    assert "- **Symptom**: invariant implicit." in by_id["L-1"].body
    assert "- **Fix plan**: bulk-tx." in by_id["P-1"].body


def test_migrate_writes_files_and_flags_low_confidence(tmp_path: Path) -> None:
    vault = tmp_path / "v"
    (vault / "docs").mkdir(parents=True)
    (vault / "docs" / "KNOWN_ISSUES.md").write_text(
        FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    result = migrate(vault, vault / "docs" / "KNOWN_ISSUES.md")
    # count parity — every issue → one file (no data loss)
    assert result["issues"] == 5
    files = sorted(p.name for p in (vault / "docs" / "issues").glob("*.md")
                   if not p.name.startswith("."))
    assert len(files) == 5
    # ZZ-9 (unknown prefix) is flagged for review, but still written
    flagged = result["flagged"]
    assert isinstance(flagged, list) and "ZZ-9" in flagged
    assert any("zz-9" in f for f in files)
    # a per-issue file round-trips through frontmatter with correct fields
    l1 = next((vault / "docs" / "issues").glob("l-1-*.md"))
    post = frontmatter.load(str(l1))
    assert post["id"] == "L-1"
    assert post["type"] == "known-issue"
    assert post["status"] == "fixed"
    assert post["category"] == "logic"
    assert str(post["opened_at"]) == "2026-05-26"
    assert "invariant implicit" in post.content
    # report exists + lists the flagged id
    report = (vault / "docs" / "issues" / ".migration-report.md").read_text(encoding="utf-8")
    assert "ZZ-9" in report


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    vault = tmp_path / "v"
    (vault / "docs").mkdir(parents=True)
    src = vault / "docs" / "KNOWN_ISSUES.md"
    src.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    result = migrate(vault, src, dry_run=True)
    assert result["issues"] == 5
    assert not (vault / "docs" / "issues").exists()
