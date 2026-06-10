"""TASK 028 / Bead 4 — ё/е index-side body fold (R-028-4).

Proves: (a) normalize_body_for_fts folds ё→е; (b) a ё-body is found by the
е-form query and vice-versa (isolated from stemming via --exact); (c)
pages.title keeps ё (display fidelity); (d) snippet() renders the folded form.
Karpathy byte-identity for ё-free content is covered by the existing golden
anchors in the full suite."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest

from scripts.wiki_index.models import Page, Vault
from scripts.wiki_index.normalization import normalize_body_for_fts
from scripts.wiki_index.sqlite_repository import SQLiteRepository
from scripts.wiki_skills._retrieval import build_search_query

VID = "personal"


def test_normalize_body_folds_yo() -> None:
    out = normalize_body_for_fts("текст: ещё всё объём Ёлка")
    assert "ё" not in out and "Ё" not in out
    assert out == "текст: еще все объем Елка"


def test_normalize_body_yo_free_identical() -> None:
    src = "обычный текст без особых букв\n\nвторой абзац"
    assert normalize_body_for_fts(src) == src


@pytest.fixture
def repo(tmp_path: Path) -> SQLiteRepository:
    r = SQLiteRepository(tmp_path / "t.db")
    r.apply_schema()
    r.register_vault(Vault(
        vault_id=VID, name=VID, root_path=tmp_path / VID,
        schema_version="2.0", registered_at=datetime(2026, 6, 1)))
    # Mirror _build_page: title stored raw (ё kept); body via normalize_body_for_fts (ё folded).
    r.upsert_page(Page(
        vault_id=VID, slug="obyom", project="_vault_", type="summary",
        title="Объём данных", file_path="obyom.md", date=date(2026, 6, 1),
        last_modified=datetime(2026, 6, 1), file_hash="h1",
        frontmatter_json={"tags": []},
        body_excerpt=normalize_body_for_fts("важный объём информации в системе"),
        tags=[], tldr="Объём"))
    yield r
    r.close()


def _slugs(hits: list[Any]) -> list[str]:
    return [h.page.slug for h in hits]


def test_yo_body_found_by_e_form(repo: SQLiteRepository) -> None:
    # Query the е-form; isolate from stemming with --exact (stem=False) → fold only.
    q = build_search_query(repo, "объем", [VID], stem=False, expand=False)
    assert q == "объем"
    assert "obyom" in _slugs(repo.search_pages(q, vaults=[VID]))


def test_e_body_found_by_yo_form(repo: SQLiteRepository) -> None:
    # Query the ё-form → folded to е → matches the folded corpus (symmetric).
    q = build_search_query(repo, "объём", [VID], stem=False, expand=False)
    assert q == "объем"
    assert "obyom" in _slugs(repo.search_pages(q, vaults=[VID]))


def test_title_keeps_yo(repo: SQLiteRepository) -> None:
    hits = repo.search_pages("объем", vaults=[VID])
    assert hits and hits[0].page.title == "Объём данных"   # NOT folded


def test_snippet_renders_folded_form(repo: SQLiteRepository) -> None:
    hits = repo.search_pages("объем", vaults=[VID])
    assert hits
    # body_excerpt is folded → snippet shows the е-form, never ё (accepted cosmetic).
    assert "ё" not in hits[0].snippet
