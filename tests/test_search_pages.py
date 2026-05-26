"""Tests for SQLiteRepository.search_pages (task-001-17, R-29 cross-vault)."""

from __future__ import annotations

import sqlite3
import time
from datetime import date, datetime
from pathlib import Path

import pytest

from scripts.wiki_index.models import Page, Vault
from scripts.wiki_index.sqlite_repository import SQLiteRepository


@pytest.fixture
def repo_with_two_vaults(tmp_path):
    """Repo populated with two vaults (alpha, beta), each having a `shadow-ai`
    concept + one source — mirrors the multi-vault fixture pattern."""
    r = SQLiteRepository(tmp_path / "test.db")
    r.apply_schema()
    for vid in ["vault-alpha", "vault-beta"]:
        r.register_vault(Vault(
            vault_id=vid, name=vid, root_path=Path(f"/tmp/{vid}"),
            schema_version="2.0", registered_at=datetime(2026, 5, 26),
        ))
        r.upsert_page(Page(
            vault_id=vid, slug="shadow-ai", project="_vault_", type="concept",
            title="Shadow AI", file_path="_concepts/shadow-ai.md",
            date=date(2026, 5, 10), last_modified=datetime(2026, 5, 10),
            file_hash=f"{vid}-1", frontmatter_json={"tags": ["shared"]},
            body_excerpt=f"shadow ai concept in {vid}: autonomous emergent behaviour",
            tags=["shared"], tldr="Shared concept",
        ))
        r.upsert_page(Page(
            vault_id=vid, slug="source-1", project="_vault_", type="summary",
            title=f"{vid} Source 1", file_path="_sources/source-1.md",
            date=date(2026, 5, 11), last_modified=datetime(2026, 5, 11),
            file_hash=f"{vid}-2", frontmatter_json={"tags": ["test"]},
            body_excerpt=f"summary of important AI agent topic from {vid}",
            tags=["test"], tldr="Source",
        ))
    yield r
    r.close()


# =============================================================================
# TC-E2E-01 — cross-vault search returns hits from multiple vaults
# =============================================================================


def test_e2e_01_cross_vault_search(repo_with_two_vaults):
    """R-29: shadow-ai hits from both vault-alpha and vault-beta."""
    hits = repo_with_two_vaults.search_pages("shadow", limit=10)
    vault_ids = {h.page.vault_id for h in hits}
    assert vault_ids == {"vault-alpha", "vault-beta"}


# =============================================================================
# TC-E2E-02 — --vaults filter restricts results
# =============================================================================


def test_e2e_02_vaults_filter(repo_with_two_vaults):
    """vaults=['vault-alpha'] excludes vault-beta hits."""
    hits = repo_with_two_vaults.search_pages("shadow", vaults=["vault-alpha"], limit=10)
    assert {h.page.vault_id for h in hits} == {"vault-alpha"}


# =============================================================================
# TC-E2E-03 — snippet contains explicit <b></b>
# =============================================================================


def test_e2e_03_snippet_markers(repo_with_two_vaults):
    """UC-03 AC: snippet uses explicit <b>...</b> markers."""
    hits = repo_with_two_vaults.search_pages("shadow", limit=1)
    assert hits
    snip = hits[0].snippet
    assert "<b>" in snip and "</b>" in snip


# =============================================================================
# TC-E2E-04 — empty result set
# =============================================================================


def test_e2e_04_empty_results(repo_with_two_vaults):
    """A query matching nothing returns []."""
    assert repo_with_two_vaults.search_pages("nonexistenttokenxyz") == []


# =============================================================================
# TC-UNIT-01 — types filter
# =============================================================================


def test_unit_01_types_filter(repo_with_two_vaults):
    """types=['summary'] returns only summary-type pages."""
    hits = repo_with_two_vaults.search_pages("AI", types=["summary"], limit=10)
    assert all(h.page.type == "summary" for h in hits)


# =============================================================================
# TC-UNIT-02 — project filter
# =============================================================================


def test_unit_02_project_filter(repo_with_two_vaults):
    """project='_vault_' filters to vault-root tier."""
    hits = repo_with_two_vaults.search_pages("shadow", project="_vault_", limit=10)
    assert all(h.page.project == "_vault_" for h in hits)


# =============================================================================
# TC-UNIT-03 — BM25 ascending
# =============================================================================


def test_unit_03_bm25_ascending(repo_with_two_vaults):
    """Hits are sorted by bm25_score ascending."""
    hits = repo_with_two_vaults.search_pages("shadow ai concept", limit=10)
    scores = [h.bm25_score for h in hits]
    assert scores == sorted(scores), f"hits not sorted by bm25: {scores}"


# =============================================================================
# TC-UNIT-05 — SQL injection resistant
# =============================================================================


def test_unit_05_sql_injection_resistant(repo_with_two_vaults):
    """FTS5 MATCH is parameterized — injection cannot drop tables.

    Note: SQLite FTS5 has its own query syntax. Quotes/semicolons inside the
    query are passed as FTS5 syntax, not SQL. The MATCH parameter is bound,
    not interpolated.
    """
    # FTS5 may raise OperationalError on malformed FTS5 syntax — that's
    # acceptable. What matters is the DROP TABLE didn't execute.
    try:
        repo_with_two_vaults.search_pages("'; DROP TABLE pages--")
    except sqlite3.OperationalError:
        pass  # FTS5 syntax error is fine
    # Verify pages table still exists with data
    n = repo_with_two_vaults._connect().execute(
        "SELECT count(*) FROM pages"
    ).fetchone()[0]
    assert n > 0


# =============================================================================
# TC-UNIT-06 — performance SLO (1K docs < 50ms; relaxed to 500ms here for CI)
# =============================================================================


def test_unit_06_search_latency_under_1s_on_1k_docs(tmp_path):
    """1K-doc fixture: search latency < 1s (relaxed from 50ms SLO for CI noise).
    Strict SLO check lives in task-001-33 benchmark suite."""
    r = SQLiteRepository(tmp_path / "perf.db")
    r.apply_schema()
    r.register_vault(Vault(
        vault_id="perf-vault", name="perf", root_path=tmp_path / "v",
        schema_version="2.0", registered_at=datetime(2026, 5, 26),
    ))
    base_date = date(2026, 5, 26)
    base_dt = datetime(2026, 5, 26)
    for i in range(1000):
        r.upsert_page(Page(
            vault_id="perf-vault", slug=f"page-{i}", project="_vault_",
            type="summary", title=f"Page {i}", file_path=f"_sources/page-{i}.md",
            date=base_date, last_modified=base_dt, file_hash=f"h{i}",
            frontmatter_json={}, body_excerpt=f"some content about topic-{i % 10} and shadow ai",
            tags=[],
        ))
    t0 = time.perf_counter()
    hits = r.search_pages("shadow", limit=20)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert len(hits) == 20
    assert elapsed_ms < 1000, f"search took {elapsed_ms:.0f}ms on 1K docs"
    r.close()
