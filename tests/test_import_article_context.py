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


def test_existing_page_slugs_no_db_ok(tmp_path):
    folder = tmp_path / "F"
    folder.mkdir()
    (folder / "A B.md").write_text("x", encoding="utf-8")
    slugs = _context.existing_page_slugs(str(tmp_path / "missing.db"),
                                         "personal", "P", folder)
    assert slugs == ["a-b"]


def test_known_concepts_normalizes(monkeypatch):
    import scripts.wiki_skills.wiki_extract_concepts as wec
    monkeypatch.setattr(
        wec, "_load_known_and_drift",
        lambda repo, v, root, fmt: (
            [{"slug": "постквантовая-криптография", "name": "Постквантовая криптография"},
             {"slug": "amm", "name": "AMM"}], []),
    )
    out = _context.known_concepts(object(), "personal", tmp := __import__("pathlib").Path("/x"))
    assert {"slug": "amm", "name": "AMM"} in out
    assert any(c["name"] == "Постквантовая криптография" for c in out)
