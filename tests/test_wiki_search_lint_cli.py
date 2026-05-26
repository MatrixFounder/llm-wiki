"""Tests for wiki-search and wiki-lint CLIs (task-001-28, task-001-29)."""

from __future__ import annotations

import io
import json
import sys
from datetime import date, datetime
from pathlib import Path

import pytest

from scripts.wiki_index.models import Page, Vault
from scripts.wiki_index.sqlite_repository import SQLiteRepository
from scripts.wiki_skills.wiki_lint import main as lint_main
from scripts.wiki_skills.wiki_search import main as search_main


@pytest.fixture
def populated_repo(tmp_path):
    r = SQLiteRepository(tmp_path / "db.db")
    r.apply_schema()
    vault_root = tmp_path / "v"
    vault_root.mkdir()
    r.register_vault(Vault(
        vault_id="search-test", name="t", root_path=vault_root,
        schema_version="2.0", registered_at=datetime(2026, 5, 26),
    ))
    from scripts.wiki_source.parsing import compute_file_hash
    body = "self-learning autonomous trading agent framework"
    (vault_root / "_concepts").mkdir()
    fm_body = (
        f"---\ntype: concept\ntitle: Hermes Agent\n"
        f"date: 2026-05-25\ntags: [agent]\n---\n{body}\n"
    )
    (vault_root / "_concepts" / "hermes.md").write_text(fm_body)
    # Adapter/check_drift convention (post-adversarial fix): hash full file
    # bytes so frontmatter-only edits trigger re-index. Mirrors
    # ManualSourceAdapter.fetch which uses `abs_source.read_bytes()`.
    file_hash = compute_file_hash(fm_body.encode("utf-8"))
    r.upsert_page(Page(
        vault_id="search-test", slug="hermes", project="_vault_",
        type="concept", title="Hermes Agent",
        file_path="_concepts/hermes.md",
        date=date(2026, 5, 25), last_modified=datetime(2026, 5, 25),
        file_hash=file_hash,
        frontmatter_json={"tags": ["agent"]},
        body_excerpt=body, tags=["agent"],
    ))
    yield r
    r.close()


def _run(skill, argv):
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        code = skill(argv)
    finally:
        sys.stdout = old
    return code, json.loads(buf.getvalue())


def test_search_basic(populated_repo):
    code, out = _run(search_main, [
        "autonomous", "--vaults", "search-test",
        "--db-path", str(populated_repo.db_path),
    ])
    assert code == 0
    assert out["action"] == "searched"
    assert out["count"] == 1
    assert out["hits"][0]["slug"] == "hermes"


def test_search_no_match(populated_repo):
    code, out = _run(search_main, [
        "totallyabsenttoken", "--vaults", "search-test",
        "--db-path", str(populated_repo.db_path),
    ])
    assert out["count"] == 0


def test_lint_clean_vault(populated_repo):
    code, out = _run(lint_main, [
        "--vault", "search-test",
        "--db-path", str(populated_repo.db_path),
    ])
    assert code == 0
    assert out["action"] == "linted"
    assert out["total_issues"] == 0


def test_lint_markdown_report(populated_repo, tmp_path):
    report = tmp_path / "report.md"
    _run(lint_main, [
        "--vault", "search-test",
        "--report", str(report),
        "--db-path", str(populated_repo.db_path),
    ])
    text = report.read_text()
    assert "Healthy" in text  # clean vault


def test_lint_json_sidecar(populated_repo, tmp_path):
    sidecar = tmp_path / "issues.json"
    _run(lint_main, [
        "--vault", "search-test",
        "--json-sidecar", str(sidecar),
        "--db-path", str(populated_repo.db_path),
    ])
    data = json.loads(sidecar.read_text())
    assert isinstance(data, list)
