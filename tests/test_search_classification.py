"""TASK 049 (R-2 / ADR-009) — the `search_pages` classification predicate.

Contract: with `allowed_classifications` + `classification_default` set, only
pages whose effective level (authored `classification`, else the default) is
in the allowed list are returned — on ALL THREE query shapes, applied BEFORE
the LIMIT; unknown labels fail closed; null ≡ absent; OFF (None) is
byte-identical to the pre-TASK-049 behaviour.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest

from scripts.wiki_index.models import Page, Vault
from scripts.wiki_index.sqlite_repository import SQLiteRepository

VAULT_ID = "cls-test"
_ALLOWED = ["public", "internal"]          # audience=internal over the builtin ladder
_DEFAULT = "public"


def _page(slug: str, *, classification: object = "__absent__",
          body: str = "policy demo content", project: str = "_vault_") -> Page:
    fm: dict[str, object] = {"tags": ["cls-demo"], "status": "open"}
    if classification != "__absent__":
        fm["classification"] = classification
    return Page(
        vault_id=VAULT_ID, slug=slug, project=project, type="concept",
        title=slug, file_path=f"_concepts/{slug}.md",
        date=date(2026, 7, 1), last_modified=datetime(2026, 7, 1),
        file_hash=f"h-{slug}", frontmatter_json=fm,
        body_excerpt=body, tags=["cls-demo"], tldr="tldr",
    )


_CORPUS: list[tuple[str, object]] = [
    ("p-public", "public"),
    ("p-internal", "internal"),
    ("p-restricted", "restricted"),
    ("p-absent", "__absent__"),          # no key → default_level (public)
    ("p-null", None),                     # YAML null → default_level (null ≡ absent)
    ("p-foreign", "geheim"),              # a foreign vault's label → fail closed
    ("p-numeric", 3),                     # non-str authored value → CAST'd text "3" → excluded
]
_VISIBLE = {"p-public", "p-internal", "p-absent", "p-null"}


@pytest.fixture
def repo(tmp_path: Path):
    r = SQLiteRepository(tmp_path / "cls.db")
    r.apply_schema()
    r.register_vault(Vault(
        vault_id=VAULT_ID, name=VAULT_ID, root_path=tmp_path / VAULT_ID,
        schema_version="7.0", registered_at=datetime(2026, 7, 1)))
    for slug, cls in _CORPUS:
        r.upsert_page(_page(slug, classification=cls))
    yield r
    r.close()


def _slugs(hits) -> set[str]:
    return {h.page.slug for h in hits}


# =============================================================================
# (a)(b)(c) — the three query shapes filter identically
# =============================================================================

def test_fts_path_filters(repo):
    hits = repo.search_pages(
        '"policy"', vaults=[VAULT_ID],
        allowed_classifications=_ALLOWED, classification_default=_DEFAULT)
    assert _slugs(hits) == _VISIBLE


def test_metadata_scan_path_filters(repo):
    hits = repo.search_pages(
        None, vaults=[VAULT_ID], where_fields=[("status", "open")],
        allowed_classifications=_ALLOWED, classification_default=_DEFAULT)
    assert _slugs(hits) == _VISIBLE


def test_fts_narrowed_tags_path_filters(repo):
    # tags-membership metadata path — the TASK 035 FTS-narrowed shape.
    prod = repo.search_pages(
        None, vaults=[VAULT_ID], where_fields=[("tags", "cls-demo")],
        allowed_classifications=_ALLOWED, classification_default=_DEFAULT)
    scan = repo.search_pages(
        None, vaults=[VAULT_ID], where_fields=[("tags", "cls-demo")],
        allowed_classifications=_ALLOWED, classification_default=_DEFAULT,
        _use_fts_narrowing=False)
    assert _slugs(prod) == _VISIBLE
    assert [ (h.page.slug) for h in prod ] == [ (h.page.slug) for h in scan ]


# =============================================================================
# (d) — pre-LIMIT: a filtered page must never consume a top-limit slot
# =============================================================================

def test_restricted_page_does_not_evict_visible_hit_at_limit(tmp_path):
    r = SQLiteRepository(tmp_path / "lim.db")
    r.apply_schema()
    r.register_vault(Vault(
        vault_id=VAULT_ID, name=VAULT_ID, root_path=tmp_path / VAULT_ID,
        schema_version="7.0", registered_at=datetime(2026, 7, 1)))
    # The restricted page is the STRONGEST BM25 match for "policy".
    r.upsert_page(_page("top-restricted", classification="restricted",
                        body="policy policy policy policy policy"))
    r.upsert_page(_page("weak-public", classification="public",
                        body="policy mentioned once"))
    try:
        hits = r.search_pages(
            '"policy"', vaults=[VAULT_ID], limit=1,
            allowed_classifications=_ALLOWED, classification_default=_DEFAULT)
        assert _slugs(hits) == {"weak-public"}
    finally:
        r.close()


# =============================================================================
# (e)(f) — fail-closed + null ≡ absent (covered in _VISIBLE; assert explicitly)
# =============================================================================

def test_unknown_and_foreign_labels_fail_closed(repo):
    hits = repo.search_pages(
        '"policy"', vaults=[VAULT_ID],
        allowed_classifications=_ALLOWED, classification_default=_DEFAULT)
    assert "p-foreign" not in _slugs(hits)
    assert "p-numeric" not in _slugs(hits)


def test_null_equals_absent_equals_default(repo):
    hits = repo.search_pages(
        '"policy"', vaults=[VAULT_ID],
        allowed_classifications=["public"], classification_default="public")
    assert {"p-absent", "p-null", "p-public"} == _slugs(hits)


# =============================================================================
# (g) — library-caller defense
# =============================================================================

def test_both_or_neither_valueerror(repo):
    with pytest.raises(ValueError):
        repo.search_pages('"policy"', vaults=[VAULT_ID],
                          allowed_classifications=_ALLOWED)
    with pytest.raises(ValueError):
        repo.search_pages('"policy"', vaults=[VAULT_ID],
                          classification_default=_DEFAULT)
    with pytest.raises(ValueError):
        repo.search_pages('"policy"', vaults=[VAULT_ID],
                          allowed_classifications=[],
                          classification_default=_DEFAULT)


# =============================================================================
# (h) — OFF-equivalence (NFR-1): None ⇒ identical to a plain call
# =============================================================================

def test_off_is_byte_identical(repo):
    plain = repo.search_pages('"policy"', vaults=[VAULT_ID])
    off = repo.search_pages('"policy"', vaults=[VAULT_ID],
                            allowed_classifications=None,
                            classification_default=None)
    assert [(h.page.slug, h.bm25_score, h.snippet) for h in plain] == \
           [(h.page.slug, h.bm25_score, h.snippet) for h in off]
    assert _slugs(plain) == {s for s, _ in _CORPUS}


def test_off_metadata_path_identical(repo):
    plain = repo.search_pages(None, vaults=[VAULT_ID],
                              where_fields=[("status", "open")])
    off = repo.search_pages(None, vaults=[VAULT_ID],
                            where_fields=[("status", "open")],
                            allowed_classifications=None,
                            classification_default=None)
    assert [h.page.slug for h in plain] == [h.page.slug for h in off]


# =============================================================================
# Injection posture: a hostile level value is inert (bound param)
# =============================================================================

def test_hostile_level_value_is_inert(repo):
    hits = repo.search_pages(
        '"policy"', vaults=[VAULT_ID],
        allowed_classifications=["public", "x'); DROP TABLE pages;--"],
        classification_default="public")
    assert _slugs(hits) == {"p-public", "p-absent", "p-null"}
    # table survives
    assert repo.get_page(VAULT_ID, "p-restricted", "_vault_") is not None


# =============================================================================
# SEC-2 — home-vault-scoped default (cross-vault fail-closed for unclassified)
# =============================================================================

def test_home_vault_scoped_default(tmp_path):
    r = SQLiteRepository(tmp_path / "home.db")
    r.apply_schema()
    from scripts.wiki_index.models import Vault as _V
    for vid in (VAULT_ID, "foreign-vault"):
        r.register_vault(_V(
            vault_id=vid, name=vid, root_path=tmp_path / vid,
            schema_version="7.0", registered_at=datetime(2026, 7, 1)))
    r.upsert_page(_page("home-plain"))
    foreign = _page("foreign-plain")
    foreign = Page(**{**foreign.__dict__, "vault_id": "foreign-vault"})
    r.upsert_page(foreign)
    try:
        hits = r.search_pages(
            '"policy"', vaults=None,
            allowed_classifications=["public"], classification_default="public",
            classification_home_vault=VAULT_ID)
        assert {h.page.slug for h in hits} == {"home-plain"}
        # без home-vault (uniform) обе непомеченные страницы видимы
        hits = r.search_pages(
            '"policy"', vaults=None,
            allowed_classifications=["public"], classification_default="public")
        assert {h.page.slug for h in hits} == {"home-plain", "foreign-plain"}
    finally:
        r.close()
