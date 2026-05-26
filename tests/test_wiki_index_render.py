"""Tests for wiki-index-render (task-001-26)."""

from __future__ import annotations

import io
import json
import sys
from datetime import date, datetime
from pathlib import Path

import pytest

from scripts.wiki_index.models import Page, Vault
from scripts.wiki_index.rendering import (
    atomic_write,
    extract_custom_sections,
    render_index,
)
from scripts.wiki_index.sqlite_repository import SQLiteRepository
from scripts.wiki_skills.wiki_index_render import main


@pytest.fixture
def repo_with_pages(tmp_path):
    r = SQLiteRepository(tmp_path / "test.db")
    r.apply_schema()
    r.register_vault(Vault(
        vault_id="test-vault", name="t",
        root_path=tmp_path / "test-vault",
        schema_version="2.0", registered_at=datetime(2026, 5, 26),
    ))
    (tmp_path / "test-vault").mkdir()
    for slug, ttl, kind in [
        ("alpha", "Alpha source", "summary"),
        ("beta", "Beta source", "summary"),
        ("concept-x", "Concept X", "concept"),
    ]:
        r.upsert_page(Page(
            vault_id="test-vault", slug=slug, project="_vault_", type=kind,
            title=ttl, file_path=f"_sources/{slug}.md",
            date=date(2026, 5, 25), last_modified=datetime(2026, 5, 25),
            file_hash=slug, frontmatter_json={"tags": []},
            body_excerpt="x", tags=[],
        ))
    yield r
    r.close()


def _run(argv: list[str]) -> tuple[int, dict]:
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        code = main(argv)
    finally:
        sys.stdout = old
    return code, json.loads(buf.getvalue())


def test_e2e_01_render_minimal_repo(repo_with_pages, tmp_path):
    content = render_index(repo_with_pages, "test-vault")
    assert "# Index — test-vault" in content
    assert "alpha" in content
    assert "beta" in content
    assert "concept-x" in content


def test_e2e_02_render_via_cli(repo_with_pages, tmp_path):
    out_path = tmp_path / "rendered.md"
    code, out = _run([
        "--vault", "test-vault",
        "--output", str(out_path),
        "--db-path", str(repo_with_pages.db_path),
    ])
    assert code == 0
    assert out["action"] == "rendered"
    assert out_path.exists()


def test_e2e_03_custom_section_preserved(repo_with_pages, tmp_path):
    """Re-render preserves <!-- BEGIN-CUSTOM:... --> blocks."""
    out_path = tmp_path / "idx.md"
    out_path.write_text(
        "# old\n\n"
        "<!-- BEGIN-CUSTOM:notes -->\n"
        "Operator's hand-written notes.\n"
        "<!-- END-CUSTOM:notes -->\n"
    )
    _run([
        "--vault", "test-vault",
        "--output", str(out_path),
        "--db-path", str(repo_with_pages.db_path),
    ])
    new = out_path.read_text()
    assert "Operator's hand-written notes." in new
    assert "BEGIN-CUSTOM:notes" in new


def test_unit_01_extract_custom_handles_multiple():
    md = (
        "<!-- BEGIN-CUSTOM:a -->A content<!-- END-CUSTOM:a -->\n"
        "stuff\n"
        "<!-- BEGIN-CUSTOM:b -->\nB content\n<!-- END-CUSTOM:b -->\n"
    )
    sections = extract_custom_sections(md)
    assert set(sections.keys()) == {"a", "b"}
    assert "A content" in sections["a"]
    assert "B content" in sections["b"]


def test_unit_02_atomic_write_no_partial_on_crash(tmp_path, monkeypatch):
    """If os.rename fails, no partial file at target."""
    target = tmp_path / "out.md"
    import os
    orig = os.rename

    def boom(src, dst):
        os.unlink(src)
        raise OSError("simulated")

    monkeypatch.setattr(os, "rename", boom)
    with pytest.raises(OSError):
        atomic_write(target, "content")
    monkeypatch.setattr(os, "rename", orig)
    assert not target.exists()
