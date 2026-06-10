"""TASK 028 / Bead 3 — wiki-query per-token stemming + --exact question_hash
symmetry (C1). Exercises the shared `_retrieve` / `_build_match_query` /
`_question_hash` directly (the path both `prepare` and `apply` run)."""

from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest

from scripts.wiki_index.models import Page, Vault
from scripts.wiki_index.sqlite_repository import SQLiteRepository
from scripts.wiki_skills.wiki_query import (
    _build_match_query,
    _question_hash,
    _retrieve,
)

VID = "personal"


def _args(*, exact: bool, expand: bool = True) -> argparse.Namespace:
    return argparse.Namespace(
        vault=VID, vaults=None, types=None, project=None, limit=10,
        no_expand_aliases=not expand, exact=exact,
    )


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
    r.upsert_page(_page(
        "03-pervoe-kasanie", "03 - Первое касание",
        "продуктовая осведомленность; осведомление о продукте", "h2"))
    # Only the INFLECTED form is present (no bare "переговоры") → default stemming
    # finds it, --exact (literal) does not → hit set differs → hash differs.
    r.upsert_page(_page(
        "negotiation", "Тактика", "успешные переговорщики всегда готовятся", "h5"))
    yield r
    r.close()


def _slugs(hits: list[Any]) -> list[str]:
    return [h.page.slug for h in hits]


def test_default_finds_inflected(repo: SQLiteRepository) -> None:
    assert "negotiation" in _slugs(_retrieve(repo, "переговоры", _args(exact=False)))


def test_exact_misses_inflected(repo: SQLiteRepository) -> None:
    # --exact = literal: "переговоры" token does not match "переговорщики".
    assert "negotiation" not in _slugs(_retrieve(repo, "переговоры", _args(exact=True)))


def test_prepare_apply_hash_matches_when_flags_match(repo: SQLiteRepository) -> None:
    # prepare-default → apply-default reproduces the question_hash.
    h1 = _question_hash("переговоры", _retrieve(repo, "переговоры", _args(exact=False)))
    h2 = _question_hash("переговоры", _retrieve(repo, "переговоры", _args(exact=False)))
    assert h1 == h2


def test_exact_flag_asymmetry_changes_hash(repo: SQLiteRepository) -> None:
    # prepare-default → apply-exact yields a DIFFERENT hash → QUESTION_CHANGED
    # (documented, expected — C1).
    h_default = _question_hash("переговоры", _retrieve(repo, "переговоры", _args(exact=False)))
    h_exact = _question_hash("переговоры", _retrieve(repo, "переговоры", _args(exact=True)))
    assert h_default != h_exact


def test_default_finds_pervoe_kasanie(repo: SQLiteRepository) -> None:
    # RAG path independently pinned (not assumed from wiki-search tests).
    assert "03-pervoe-kasanie" in _slugs(
        _retrieve(repo, "продуктовое осведомление", _args(exact=False)))


# --- build_match_query shape / determinism / dedup ------------------------- #
def test_build_match_query_per_token_stem(repo: SQLiteRepository) -> None:
    q = _build_match_query(repo, "продуктовое осведомление", [VID], False, True)
    assert q == '"осведомлен"* OR "продуктов"*'


def test_build_match_query_exact_fold_only(repo: SQLiteRepository) -> None:
    # --exact still folds ё (always-on) but does not stem/prefix; deterministic
    # sorted output.
    q = _build_match_query(repo, "продуктовое всё", [VID], False, False)
    assert q == '"все" OR "продуктовое"'


def test_build_match_query_determinism(repo: SQLiteRepository) -> None:
    a = _build_match_query(repo, "сценарии продажи телефон", [VID], False, True)
    b = _build_match_query(repo, "сценарии продажи телефон", [VID], False, True)
    assert a == b


def test_build_match_query_inflections_dedup_to_one_stem(repo: SQLiteRepository) -> None:
    # M-2: two inflections of one root collapse to a single stem atom.
    q = _build_match_query(repo, "сценарии сценарий продажи", [VID], False, True)
    assert q == '"продаж"* OR "сценар"*'
