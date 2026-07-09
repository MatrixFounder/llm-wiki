"""S2 — `wiki_import_article._context` (R-2/R-5 inputs)."""
from __future__ import annotations

import sqlite3

from scripts.wiki_skills.wiki_import_article import _context


def _make_db(path, rows):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE pages (vault_id TEXT, slug TEXT, project TEXT)")
    conn.executemany("INSERT INTO pages VALUES (?,?,?)", rows)
    conn.commit()
    conn.close()


def test_existing_page_slugs_union_db_and_fs(tmp_path):
    db = tmp_path / "index.db"
    _make_db(db, [
        ("personal", "defi", "Материалы/Криптовалюты"),          # the owner's Defi.md, indexed
        ("personal", "uniswap", "Материалы/Криптовалюты"),
        ("personal", "other", "Материалы/Инвестиции"),            # different project — excluded
    ])
    folder = tmp_path / "Криптовалюты"
    (folder / "_concepts").mkdir(parents=True)
    (folder / "Новая заметка.md").write_text("x", encoding="utf-8")
    (folder / "_concepts" / "амм.md").write_text("x", encoding="utf-8")

    slugs = _context.existing_page_slugs(
        str(db), "personal", "Материалы/Криптовалюты", folder)
    assert "defi" in slugs                 # the eviction-risk slug is caught
    assert "uniswap" in slugs
    assert "other" not in slugs            # other project not included
    assert "новая-заметка" in slugs        # on-disk note stem, slugified
    assert "амм" in slugs                  # on-disk concept stem


def test_existing_page_slugs_karpathy_scans_parent_concepts(tmp_path):
    # source_subdir layout (karpathy): the note writes to <course>/_sources/, but concept pages
    # live in the SIBLING <course>/_concepts/ (where _apply_write files them). The collision
    # guard must scan THAT dir, not _sources/_concepts (which doesn't exist) — else an unindexed
    # concept page is invisible to the guard and gets evicted at reindex.
    course = tmp_path / "Lessons" / "Quantum"
    sources = course / "_sources"
    (course / "_concepts").mkdir(parents=True)
    sources.mkdir(parents=True)
    (sources / "Lecture 1.md").write_text("x", encoding="utf-8")        # a note in _sources
    (course / "_concepts" / "shor.md").write_text("x", encoding="utf-8")  # sibling concept page
    (sources / "_concepts").mkdir()                                      # decoy — must be IGNORED
    (sources / "_concepts" / "decoy.md").write_text("x", encoding="utf-8")

    slugs = _context.existing_page_slugs(
        None, "v", "Lessons/Quantum", sources, source_subdir="_sources")
    assert "lecture-1" in slugs   # _sources note stem
    assert "shor" in slugs        # SIBLING _concepts/ stem is caught
    assert "decoy" not in slugs   # _sources/_concepts is NOT where concepts live → ignored


def test_existing_page_slugs_no_db_ok(tmp_path):
    folder = tmp_path / "F"
    folder.mkdir()
    (folder / "A B.md").write_text("x", encoding="utf-8")
    slugs = _context.existing_page_slugs(str(tmp_path / "missing.db"),
                                         "personal", "P", folder)
    assert slugs == ["a-b"]


def test_known_concepts_normalizes(monkeypatch):
    # known_concepts uses the cheap single-query loader (not the full-vault drift walk)
    from scripts.wiki_skills.wiki_extract_concepts import _db
    monkeypatch.setattr(
        _db, "load_known_entities",
        lambda repo, v: [
            {"slug": "постквантовая-криптография", "name": "Постквантовая криптография"},
            {"slug": "amm", "name": "AMM"}],
    )
    out = _context.known_concepts(object(), "personal", __import__("pathlib").Path("/x"))
    assert {"slug": "amm", "name": "AMM"} in out
    assert any(c["name"] == "Постквантовая криптография" for c in out)


def test_known_concepts_slugs_only_shape(monkeypatch):
    # P-6 residual: `slugs-only` emits a bare [slug, …] list (mirrors wiki-extract-concepts
    # R-015-3), shrinking the prepare envelope on a large vault; `full` (default) is byte-identical
    # to today. An empty slug is dropped from the slugs-only list (never emits a bare "").
    from pathlib import Path

    from scripts.wiki_skills.wiki_extract_concepts import _db
    monkeypatch.setattr(
        _db, "load_known_entities",
        lambda repo, v: [{"slug": "amm", "name": "AMM"},
                         {"slug": "defi", "name": "DeFi"},
                         {"slug": "", "name": "junk"}],
    )
    slugs = _context.known_concepts(object(), "v", Path("/x"), fmt="slugs-only")
    assert slugs == ["amm", "defi"]                       # bare slug strings, empty dropped
    full = _context.known_concepts(object(), "v", Path("/x"))  # default fmt="full"
    assert {"slug": "amm", "name": "AMM"} in full
    assert all(isinstance(c, dict) and set(c) == {"slug", "name"} for c in full)
