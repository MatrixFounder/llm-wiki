"""TASK 012-05 (PW-L) — slug_strategy + the _derive_source_project convergence (C1)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from scripts.wiki_index.layout_config import (
    LayoutConfig,
    PathEntry,
    _apply_slug_strategy,
    derive_project_for_path,
    iter_pages,
)
from scripts.wiki_index.models import Vault
from scripts.wiki_index.reindex import reindex_full
from scripts.wiki_index.sqlite_repository import SQLiteRepository


def _cfg(slug_strategy: str) -> LayoutConfig:
    return LayoutConfig(
        schema_version="2.0", layout="t", slug_strategy=slug_strategy,
        paths=(PathEntry(glob="*.md", project="_vault_"),),
        type_mapping={"note": ("summary", None)},
    )


@pytest.mark.parametrize("strategy,expected", [
    ("identity", "Квартиры"),
    ("preserve-unicode", "квартиры"),
    ("transliterate", "kvartiry"),
    ("ascii-only", "kvartiry"),
])
def test_apply_slug_strategy(strategy: str, expected: str) -> None:
    assert _apply_slug_strategy("Квартиры", strategy) == expected


def test_iter_pages_applies_slug_strategy(tmp_path: Path) -> None:
    (tmp_path / "Квартиры.md").write_text("x", encoding="utf-8")
    identity = {d.slug for d in iter_pages(tmp_path, _cfg("identity"))}
    preserve = {d.slug for d in iter_pages(tmp_path, _cfg("preserve-unicode"))}
    translit = {d.slug for d in iter_pages(tmp_path, _cfg("transliterate"))}
    assert identity == {"Квартиры"}        # karpathy default — verbatim stem
    assert preserve == {"квартиры"}         # lowercased, Cyrillic kept
    assert translit == {"kvartiry"}         # ASCII transliteration


def test_karpathy_slug_strategy_is_identity_byte_identical(tmp_path: Path) -> None:
    """A file whose stem has spaces/caps keeps its exact stem under karpathy
    (the byte-identity contract — no slugify)."""
    (tmp_path / "_sources").mkdir()
    (tmp_path / "_sources" / "OAuth 2.0 Notes.md").write_text(
        "---\ntype: summary\ntitle: T\n---\n\nx\n", encoding="utf-8")
    pages = iter_pages(tmp_path, LayoutConfig(
        schema_version="2.0", layout="karpathy", slug_strategy="identity",
        paths=(PathEntry(glob="_sources/**/*.md", project="_vault_"),),
        type_mapping={"summary": ("summary", None)},
    ))
    assert {d.slug for d in pages} == {"OAuth 2.0 Notes"}


# --------------------------------------------------------------------------- #
# C1: _derive_source_project converges onto the shared config-driven helper
# --------------------------------------------------------------------------- #


def test_derive_source_project_matches_reindex_for_course_tier(tmp_path: Path) -> None:
    """The apply-side project (wiki_extract_concepts._derive_source_project →
    derive_project_for_path) equals the project the reindexer records, for both
    tiers of a karpathy vault — the page_entity_refs FK depends on this (C1)."""
    from scripts.wiki_skills.wiki_extract_concepts import _derive_source_project

    vault = tmp_path / "v"
    (vault / "_sources").mkdir(parents=True)
    (vault / "_sources" / "root-src.md").write_text(
        "---\ntype: summary\ntitle: R\n---\n\nx\n", encoding="utf-8")
    (vault / "Lessons" / "Course-A" / "_sources").mkdir(parents=True)
    (vault / "Lessons" / "Course-A" / "_sources" / "c-src.md").write_text(
        "---\ntype: summary\ntitle: C\n---\n\nx\n", encoding="utf-8")

    repo = SQLiteRepository(tmp_path / "g.db")
    repo.apply_schema()
    repo.register_vault(Vault(
        vault_id="proj-v", name="proj-v", root_path=vault,
        schema_version="2.0", registered_at=datetime(2026, 5, 26)))
    try:
        reindex_full(repo, "proj-v")
        db = {(r["slug"], r["project"]) for r in repo._connect().execute(
            "SELECT slug, project FROM pages WHERE vault_id='proj-v'").fetchall()}
        assert ("root-src", "_vault_") in db
        assert ("c-src", "course-a") in db
        # the shared helper agrees with what reindex recorded
        assert _derive_source_project(vault / "_sources" / "root-src.md", vault) == "_vault_"
        assert _derive_source_project(
            vault / "Lessons" / "Course-A" / "_sources" / "c-src.md", vault) == "course-a"
        assert derive_project_for_path(
            vault / "Lessons" / "Course-A" / "_sources" / "c-src.md", vault) == "course-a"
    finally:
        repo.close()
