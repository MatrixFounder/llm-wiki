"""TASK 028 / Bead 2 — wiki-search query-side stemming e2e + F-1 composition.

Seeds pages whose bodies use DIFFERENT inflections than the query (the real
dogfood misses), proving default stemming finds them while `--exact` reproduces
the literal-AND miss. Composition (stem-first, then OR-in exact alias surfaces)
is pinned with a stub repo."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest

from scripts.wiki_index.models import Page, Vault
from scripts.wiki_index.sqlite_repository import SQLiteRepository
from scripts.wiki_skills import wiki_search
from scripts.wiki_skills._retrieval import build_search_query

VID = "personal"


def _page(slug: str, title: str, body: str, h: str) -> Page:
    return Page(
        vault_id=VID, slug=slug, project="_vault_", type="summary",
        title=title, file_path=f"{slug}.md", date=date(2026, 6, 1),
        last_modified=datetime(2026, 6, 1), file_hash=h,
        frontmatter_json={"tags": []}, body_excerpt=body, tags=[], tldr=title,
    )


@pytest.fixture
def repo(tmp_path: Path) -> SQLiteRepository:
    r = SQLiteRepository(tmp_path / "t.db")
    r.apply_schema()
    r.register_vault(Vault(
        vault_id=VID, name=VID, root_path=tmp_path / VID,
        schema_version="2.0", registered_at=datetime(2026, 6, 1)))
    # Miss #1: query "сценарии продаж" but body uses singular/other inflections.
    r.upsert_page(_page(
        "scenarii-prodazh-pkch", "Сценарии продаж П-К-Ч",
        "холодный сценарий продажи по телефону: проблема контакт human", "h1"))
    # Miss #2: on-topic page uses "осведомление"/"продуктовая", query is "продуктовое осведомление".
    r.upsert_page(_page(
        "03-pervoe-kasanie", "03 - Первое касание",
        "продуктовая осведомленность; осведомление о продукте важно", "h2"))
    # Tangential page: matches "продуктов*" but NOT "осведомлен*" → excluded by AND.
    r.upsert_page(_page(
        "ai-panel", "AI panel", "продуктовое мышление обсуждали однажды", "h3"))
    # ё-free page for the --exact byte-identity anchor.
    r.upsert_page(_page("dofamin", "Дофамин", "дофамин и мотивация", "h4"))
    yield r
    r.close()


def _slugs(hits: list[Any]) -> list[str]:
    return [h.page.slug for h in hits]


def test_default_stemming_finds_inflected_scenarii(repo: SQLiteRepository) -> None:
    q = build_search_query(repo, "сценарии продаж", [VID], stem=True, expand=False)
    assert q == "сценар* продаж*"
    assert "scenarii-prodazh-pkch" in _slugs(repo.search_pages(q, vaults=[VID]))


def test_exact_reproduces_literal_and_miss(repo: SQLiteRepository) -> None:
    # --exact = literal implicit-AND: "продуктовое" AND "осведомление". No page
    # has BOTH exact forms (03 has "продуктовая"+"осведомление"; ai-panel has
    # "продуктовое" but no "осведомление") → literal misses everything. This is
    # the pre-028 behaviour the production incident hit; stemming is what fixes it.
    q = build_search_query(repo, "продуктовое осведомление", [VID], stem=False, expand=False)
    assert q == "продуктовое осведомление"
    assert "03-pervoe-kasanie" not in _slugs(repo.search_pages(q, vaults=[VID]))


def test_default_stemming_finds_pervoe_kasanie_not_tangential(repo: SQLiteRepository) -> None:
    q = build_search_query(repo, "продуктовое осведомление", [VID], stem=True, expand=False)
    assert q == "продуктов* осведомлен*"
    slugs = _slugs(repo.search_pages(q, vaults=[VID]))
    assert "03-pervoe-kasanie" in slugs           # on-topic, found by default
    assert "ai-panel" not in slugs                # tangential, AND-excluded


def test_exact_byte_identity_for_yo_free_query(repo: SQLiteRepository) -> None:
    # For ё-free content, --exact == a direct literal search_pages call.
    q = build_search_query(repo, "дофамин", [VID], stem=False, expand=False)
    assert q == "дофамин"
    assert _slugs(repo.search_pages(q, vaults=[VID])) == \
        _slugs(repo.search_pages("дофамин", vaults=[VID]))


# --- F-1: stem-first composition; alias surfaces stay exact, typed words broaden ---
class _StubRepo:
    def __init__(self, surfaces: set[str]) -> None:
        self._surfaces = surfaces

    def expand_query_aliases(self, vid: str, query: str) -> set[str]:
        return self._surfaces

    def list_vaults(self) -> list[Any]:
        return []


def test_composition_stems_typed_words_and_keeps_aliases_exact() -> None:
    stub = _StubRepo({"Сценарии продаж"})
    q = build_search_query(stub, "продажи", [VID], stem=True, expand=True)
    # typed word IS stemmed (F-1 regression: NOT skipped on alias hit);
    # alias surface stays exact + quoted.
    assert q == '(продаж*) OR "Сценарии продаж"'


def test_composition_no_alias_is_just_stemmed() -> None:
    stub = _StubRepo(set())
    q = build_search_query(stub, "сценарии продажи", [VID], stem=True, expand=True)
    assert q == "сценар* продаж*"


def test_main_whitespace_query_clean_invalid_not_crash(tmp_path: Path) -> None:
    # vdd-multi regression: a whitespace-only query collapses to '' in the
    # stemming lexer; search_pages rejects '' with ValueError (NOT caught by the
    # OperationalError-only DF-1 net). main() must strip → clean INVALID_QUERY
    # (exit 2), never an uncaught exception.
    db = tmp_path / "ws.db"
    r = SQLiteRepository(db)
    r.apply_schema()
    r.register_vault(Vault(
        vault_id=VID, name=VID, root_path=tmp_path / VID,
        schema_version="2.0", registered_at=datetime(2026, 6, 1)))
    r.close()
    for q in ["   ", "\t", "\n", "   "]:
        rc = wiki_search.main([q, "--vaults", VID, "--db-path", str(db)])
        assert rc == 2, f"expected clean INVALID_QUERY for {q!r}, got {rc}"


def test_empty_base_never_paren_wraps() -> None:
    # Defense-in-depth (vdd-multi LOW): a whitespace-only query must never become
    # "() OR ..." even if alias resolution returned surfaces.
    stub = _StubRepo({"Сценарии продаж"})
    q = build_search_query(stub, "   ", [VID], stem=True, expand=True)
    assert "()" not in q
    assert q.strip() == ""


def test_lexer_leaves_hyphenated_term_for_df1(repo: SQLiteRepository) -> None:
    # A hyphenated bare term is preserved verbatim (it's not a bare word) → it
    # reaches FTS as-is and trips OperationalError, which main()'s DF-1 fallback
    # catches (fold-aware quoted phrase). Here we just pin the lexer behaviour.
    q = build_search_query(repo, "hermes-agent", [VID], stem=True, expand=False)
    assert q == "hermes-agent"
