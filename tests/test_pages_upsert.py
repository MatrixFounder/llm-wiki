"""Tests for SQLiteRepository pages + refs CRUD (task-001-16 / M-4 contract)."""

from __future__ import annotations

import re
import sqlite3
from datetime import date, datetime
from pathlib import Path

import pytest

from scripts.wiki_index.models import Page, PageRef, Vault
from scripts.wiki_index.sqlite_repository import SQLiteRepository


@pytest.fixture
def repo(tmp_path):
    r = SQLiteRepository(tmp_path / "test.db")
    r.apply_schema()
    r.register_vault(Vault(
        vault_id="trade-agents",
        name="Trade Agents",
        root_path=Path("/tmp/trade-agents"),
        schema_version="2.0",
        registered_at=datetime(2026, 5, 26),
    ))
    yield r
    r.close()


def _page(slug="hermes-agent", project="_vault_", file_hash="abc123",
          title="Hermes", body="self-learning agent framework") -> Page:
    return Page(
        vault_id="trade-agents",
        slug=slug,
        project=project,
        type="concept",
        title=title,
        file_path=f"_concepts/{slug}.md",
        date=date(2026, 5, 25),
        last_modified=datetime(2026, 5, 25, 10, 0, 0),
        file_hash=file_hash,
        frontmatter_json={"tags": ["agent", "trading"]},
        body_excerpt=body,
        tags=["agent", "trading"],
        tldr="Self-learning",
    )


# =============================================================================
# TC-E2E-01 — round-trip
# =============================================================================


def test_e2e_01_round_trip(repo):
    p = _page()
    assert repo.upsert_page(p) == "inserted"
    got = repo.get_page("trade-agents", "hermes-agent", "_vault_")
    assert got is not None
    assert got.title == "Hermes"
    assert got.tags == ["agent", "trading"]


# =============================================================================
# TC-E2E-02 — same hash → unchanged
# =============================================================================


def test_e2e_02_unchanged_on_same_hash(repo):
    p = _page()
    assert repo.upsert_page(p) == "inserted"
    assert repo.upsert_page(p) == "unchanged"


# =============================================================================
# TC-E2E-03 — different hash → updated
# =============================================================================


def test_e2e_03_updated_on_different_hash(repo):
    p1 = _page(file_hash="aaa", title="V1")
    p2 = _page(file_hash="bbb", title="V2")
    assert repo.upsert_page(p1) == "inserted"
    assert repo.upsert_page(p2) == "updated"
    got = repo.get_page("trade-agents", "hermes-agent", "_vault_")
    assert got is not None
    assert got.title == "V2"


# =============================================================================
# TC-E2E-04 — FTS5 trigger fires
# =============================================================================


def test_e2e_04_fts5_trigger_fires(repo):
    repo.upsert_page(_page(body="autonomous agent framework"))
    n = repo._connect().execute(
        "SELECT count(*) FROM pages_fts WHERE pages_fts MATCH ? AND vault_id=?",
        ("autonomous", "trade-agents"),
    ).fetchone()[0]
    assert n == 1


# =============================================================================
# TC-E2E-05 — replace_refs atomic
# =============================================================================


def test_e2e_05_replace_refs_atomic(repo):
    repo.upsert_page(_page(slug="src"))
    # Need entity to FK against
    repo._connect().execute(
        "INSERT INTO entities (vault_id, slug, type, name, first_seen, last_updated, file_path) "
        "VALUES ('trade-agents', 'sharpe', 'concept', 'Sharpe', "
        "'2026-05-25T00:00:00Z', '2026-05-25T00:00:00Z', '_concepts/sharpe.md')"
    )
    repo.upsert_refs([PageRef(
        vault_id="trade-agents", page_slug="src", page_project="_vault_",
        entity_slug="sharpe", ref_type="mentioned",
    )])
    assert len(repo.get_backlinks("trade-agents", "sharpe")) == 1
    # Replace with empty list — deletes all
    repo.replace_refs("trade-agents", "src", "_vault_", [])
    assert repo.get_backlinks("trade-agents", "sharpe") == []


# =============================================================================
# TC-UNIT-01 — M-4 contract: grep guard
# =============================================================================


def test_unit_01_no_insert_or_replace_in_source():
    """M-4 grep guard: `INSERT OR REPLACE` MUST NOT appear as ACTIVE code in
    the SQLite DAL. Comment lines (lines whose stripped form starts with `#`)
    are exempt — they may discuss the anti-pattern. Layout-agnostic: covers
    both the historical single module (sqlite_repository.py) and the
    TASK 056 package (sqlite_repository/*.py)."""
    base = Path(__file__).parent.parent / "scripts" / "wiki_index" / "sqlite_repository"
    module = base.with_suffix(".py")
    sources = [module] if module.exists() else sorted(base.glob("*.py"))
    assert sources, f"M-4 guard found no DAL source at {base}[.py|/]"
    offenders = []
    for src in sources:
        for i, line in enumerate(src.read_text().splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue  # comment lines exempt
            if re.search(r"INSERT\s+OR\s+REPLACE", line, flags=re.IGNORECASE):
                offenders.append(f"{src.name}:L{i}: {line.strip()}")
    assert offenders == [], (
        "M-4 contract violation — INSERT OR REPLACE in active code:\n"
        + "\n".join(offenders)
    )


# =============================================================================
# TC-UNIT-02 — SQL injection resistant
# =============================================================================


def test_unit_02_sql_injection_resistant(repo):
    """Parameterized queries — title cannot inject SQL."""
    p = _page(slug="hostile", title="'; DROP TABLE pages--")
    repo.upsert_page(p)
    # pages table still present and now contains our hostile row
    n = repo._connect().execute("SELECT count(*) FROM pages").fetchone()[0]
    assert n == 1


# =============================================================================
# TC-UNIT-03 — composite PK enforced
# =============================================================================


def test_unit_03_composite_pk_enforced(repo):
    """Re-upsert produces 'updated', only 1 row remains."""
    repo.upsert_page(_page(file_hash="a"))
    repo.upsert_page(_page(file_hash="b"))
    n = repo._connect().execute(
        "SELECT count(*) FROM pages WHERE slug='hermes-agent'"
    ).fetchone()[0]
    assert n == 1


# =============================================================================
# TC-UNIT-04 — delete CASCADEs to refs
# =============================================================================


def test_unit_04_delete_cascades(repo):
    repo.upsert_page(_page(slug="src"))
    repo._connect().execute(
        "INSERT INTO entities (vault_id, slug, type, name, first_seen, last_updated, file_path) "
        "VALUES ('trade-agents', 'e', 'concept', 'E', '2026-05-25', '2026-05-25', '_c/e.md')"
    )
    repo.upsert_refs([PageRef(
        vault_id="trade-agents", page_slug="src", page_project="_vault_",
        entity_slug="e", ref_type="mentioned",
    )])
    assert len(repo.get_backlinks("trade-agents", "e")) == 1
    repo.delete_page("trade-agents", "src", "_vault_")
    assert repo.get_backlinks("trade-agents", "e") == []


# =============================================================================
# TC-UNIT-05 — replace_refs([]) deletes without insert
# =============================================================================


def test_unit_05_replace_refs_empty_list(repo):
    repo.upsert_page(_page(slug="src"))
    repo._connect().execute(
        "INSERT INTO entities (vault_id, slug, type, name, first_seen, last_updated, file_path) "
        "VALUES ('trade-agents', 'e', 'concept', 'E', '2026-05-25', '2026-05-25', '_c/e.md')"
    )
    repo.upsert_refs([PageRef(
        vault_id="trade-agents", page_slug="src", page_project="_vault_",
        entity_slug="e", ref_type="mentioned",
    )])
    repo.replace_refs("trade-agents", "src", "_vault_", [])
    assert repo.get_backlinks("trade-agents", "e") == []


# =============================================================================
# TC-UNIT-06 — backlinks sorted by (page_slug, line_start)
# =============================================================================


def test_unit_06_backlinks_sorted(repo):
    repo.upsert_page(_page(slug="z-page", file_hash="1"))
    repo.upsert_page(_page(slug="a-page", file_hash="2"))
    repo._connect().execute(
        "INSERT INTO entities (vault_id, slug, type, name, first_seen, last_updated, file_path) "
        "VALUES ('trade-agents', 'e', 'concept', 'E', '2026-05-25', '2026-05-25', '_c/e.md')"
    )
    refs = [
        PageRef(vault_id="trade-agents", page_slug="z-page", page_project="_vault_",
                entity_slug="e", ref_type="mentioned", line_start=10),
        PageRef(vault_id="trade-agents", page_slug="a-page", page_project="_vault_",
                entity_slug="e", ref_type="mentioned", line_start=20),
        PageRef(vault_id="trade-agents", page_slug="a-page", page_project="_vault_",
                entity_slug="e", ref_type="cited", line_start=5),
    ]
    repo.upsert_refs(refs)
    got = repo.get_backlinks("trade-agents", "e")
    assert [(r.page_slug, r.line_start) for r in got] == [
        ("a-page", 5), ("a-page", 20), ("z-page", 10)
    ]
