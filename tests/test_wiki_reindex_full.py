"""Tests for wiki-reindex --full (task-001-30, ADR-002 §D8 rebuildability)."""

from __future__ import annotations

import io
import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

from scripts.wiki_index.models import Vault
from scripts.wiki_index.reindex import discover_pages, reindex_full
from scripts.wiki_index.sqlite_repository import SQLiteRepository


@pytest.fixture
def fresh_db(tmp_path):
    return tmp_path / "g.db"


def _register_vault(repo, vault_id, root):
    repo.register_vault(Vault(
        vault_id=vault_id, name=vault_id, root_path=root,
        schema_version="2.0", registered_at=datetime(2026, 5, 26),
    ))


def test_unit_01_discover_pages_both_tiers(multi_vault):
    """discover_pages walks vault-root AND Lessons/<course>/_*/ trees."""
    paths = discover_pages(multi_vault["vault-alpha"])
    projects = {project for (_, _, project) in paths}
    assert "_vault_" in projects
    # Course-A → kebab-slugified
    assert any(p.startswith("course-a") for p in projects)


def test_unit_02_course_kebab_slug(multi_vault):
    paths = discover_pages(multi_vault["vault-alpha"])
    proj = {project for (_, _, project) in paths if project != "_vault_"}
    assert "course-a" in proj


def test_e2e_01_reindex_minimal_vault(minimal_vault, fresh_db):
    """Reindex on minimal-vault → all 3 pages indexed."""
    r = SQLiteRepository(fresh_db)
    r.apply_schema()
    _register_vault(r, "minimal-test", minimal_vault)
    result = reindex_full(r, "minimal-test")
    assert result["action"] == "reindexed"
    assert result["pages"] == 3
    # Searchable
    hits = r.search_pages("Alpha", vaults=["minimal-test"])
    assert len(hits) >= 1
    r.close()


def test_e2e_02_reindex_multi_vault_two_tier(multi_vault, fresh_db):
    """Reindex on vault-alpha (two-tier) → root + course-local pages distinguishable."""
    r = SQLiteRepository(fresh_db)
    r.apply_schema()
    _register_vault(r, "vault-alpha", multi_vault["vault-alpha"])
    result = reindex_full(r, "vault-alpha")
    assert result["pages"] >= 3  # 1 source + 1 concept (root) + 1 concept (course)
    # Verify project values
    projects = {row["project"] for row in r._connect().execute(
        "SELECT project FROM pages WHERE vault_id='vault-alpha'"
    ).fetchall()}
    assert "_vault_" in projects
    assert "course-a" in projects
    r.close()


def test_e2e_03_rebuildability_invariant(minimal_vault, fresh_db):
    """ADR-002 §D8 invariant: rm DB → re-register → reindex → identical state.

    This is THE proof gate for Phase 3a.
    """
    r1 = SQLiteRepository(fresh_db)
    r1.apply_schema()
    _register_vault(r1, "minimal-test", minimal_vault)
    reindex_full(r1, "minimal-test")
    pre_hits = r1.search_pages("Alpha", vaults=["minimal-test"])
    pre_slugs = {h.page.slug for h in pre_hits}
    pre_page_count = r1._connect().execute(
        "SELECT count(*) FROM pages WHERE vault_id='minimal-test'"
    ).fetchone()[0]
    r1.close()

    # Delete DB and rebuild from scratch
    fresh_db.unlink()
    r2 = SQLiteRepository(fresh_db)
    r2.apply_schema()
    _register_vault(r2, "minimal-test", minimal_vault)
    reindex_full(r2, "minimal-test")
    post_hits = r2.search_pages("Alpha", vaults=["minimal-test"])
    post_slugs = {h.page.slug for h in post_hits}
    post_page_count = r2._connect().execute(
        "SELECT count(*) FROM pages WHERE vault_id='minimal-test'"
    ).fetchone()[0]
    r2.close()

    assert pre_page_count == post_page_count, (
        f"page count drift: pre={pre_page_count} post={post_page_count}"
    )
    assert pre_slugs == post_slugs, (
        f"slug set drift: pre={pre_slugs} post={post_slugs}"
    )


def test_e2e_04_log_md_round_trip(minimal_vault, fresh_db):
    """log.md → log_events round-trip via reindex (M-2 contract)."""
    r = SQLiteRepository(fresh_db)
    r.apply_schema()
    # Write a synthetic monthly log file to make parse_log_md happy
    log_dir = minimal_vault / "00-Vault-Index" / "log"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "2026-05.md"
    log_file.write_text(
        "## [2026-05-25 10:00:00] ingest | Alpha\n"
        "- pages_created: ['alpha']\n\n"
        "## [2026-05-26 11:00:00] lint | health-check\n\n"
    )
    _register_vault(r, "minimal-test", minimal_vault)
    result = reindex_full(r, "minimal-test")
    assert result["log_events"] >= 2
    r.close()


def test_unit_05_mentions_count_recomputed(minimal_vault, fresh_db):
    """I-5 invariant: entities.mentions_count == COUNT(*) FROM page_entity_refs
    after reindex (regression guard for rebuildability)."""
    r = SQLiteRepository(fresh_db)
    r.apply_schema()
    _register_vault(r, "minimal-test", minimal_vault)
    reindex_full(r, "minimal-test")
    rows = r._connect().execute(
        "SELECT slug, mentions_count, "
        "       (SELECT COUNT(*) FROM page_entity_refs r "
        "        WHERE r.vault_id='minimal-test' AND r.entity_slug=entities.slug) AS actual "
        "FROM entities WHERE vault_id='minimal-test'"
    ).fetchall()
    for row in rows:
        assert row["mentions_count"] == row["actual"], (
            f"mentions_count drift for {row['slug']}: stored={row['mentions_count']} "
            f"actual={row['actual']}"
        )
    r.close()
