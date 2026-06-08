"""TASK 024 / R-1 + R-2 — `wiki-index-upsert` is layout-aware (byte-parity with
`reindex`) and FTS indexes the full body.

R-1: `upsert_one` must file a single page byte-identically to `reindex_full` for
the same file under the vault's resolved layout — slug (slug_strategy), project
(project_pattern), type (type_mapping), title (frontmatter_synthesis), refs
(ref_extraction + slug_strategy). Before TASK 024 it used `derive_slug`'s
`_vault_` fallback + the karpathy module `TYPE_MAPPING` and diverged on PARA.

R-2: `pages_fts` indexes the full normalized body (was `body_excerpt[:1000]`), so
a term past char 1000 is searchable; display stays bounded via `snippet()`.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest

from scripts.wiki_index.models import Page, Vault
from scripts.wiki_index.reindex import reindex_full
from scripts.wiki_index.sqlite_repository import SQLiteRepository
from scripts.wiki_skills.wiki_index_upsert import upsert_one


def _schema(root: Path, vault_id: str, layout: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "WIKI_SCHEMA.md").write_text(
        f'---\nvault_id: {vault_id}\nschema_version: "2.0"\nlanguage: ru\n'
        f'layout: {layout}\n---\n', encoding="utf-8")


def _repo(tmp_path: Path, name: str, vault_id: str, root: Path) -> SQLiteRepository:
    repo = SQLiteRepository(tmp_path / f"{name}.db")
    repo.apply_schema()
    repo.register_vault(Vault(
        vault_id=vault_id, name=vault_id, root_path=root,
        schema_version="2.0", registered_at=datetime(2026, 6, 8)))
    return repo


def _rows(repo: SQLiteRepository, vault_id: str) -> dict[str, tuple]:
    out: dict[str, tuple] = {}
    for r in repo._connect().execute(
        "SELECT slug, project, type, title, frontmatter_json FROM pages "
        "WHERE vault_id=?", (vault_id,)
    ).fetchall():
        tags = tuple(sorted(json.loads(r["frontmatter_json"]).get("tags") or []))
        out[r["slug"]] = (r["project"], r["type"], r["title"], tags)
    return out


def _refs(repo: SQLiteRepository, vault_id: str, slug: str) -> set[tuple[str, str]]:
    return {
        (r["entity_slug"], r["ref_type"])
        for r in repo._connect().execute(
            "SELECT entity_slug, ref_type FROM page_entity_refs "
            "WHERE vault_id=? AND page_slug=?", (vault_id, slug)
        ).fetchall()
    }


def _parity(tmp_path: Path, layout: str, files: dict[str, str]) -> tuple[
        SQLiteRepository, SQLiteRepository, str]:
    """Build a vault, reindex_full into repo A, upsert_one each file into repo B."""
    vid = "pvault"
    root = tmp_path / "vault"
    _schema(root, vid, layout)
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    repo_a = _repo(tmp_path, "a", vid, root)
    repo_b = _repo(tmp_path, "b", vid, root)
    reindex_full(repo_a, vid)
    for rel in files:
        upsert_one(vid, (root / rel).resolve(), root, repo_b)
    return repo_a, repo_b, vid


# --------------------------------------------------------------------------- #
# R-1 parity
# --------------------------------------------------------------------------- #

def test_parity_obsidian_personal_unicode_slug(tmp_path: Path) -> None:
    """AC-1.1: a Cyrillic-titled note → slug via preserve-unicode (NOT `_vault_`/
    bare stem); upsert tuple == reindex tuple."""
    a, b, vid = _parity(tmp_path, "obsidian-personal", {
        "02 - Personal Home/Квартиры.md": "# Квартиры\nbody about flats\n",
    })
    ra, rb = _rows(a, vid), _rows(b, vid)
    assert "квартиры" in ra, f"reindex slug set: {set(ra)}"
    assert rb == ra
    assert ra["квартиры"][0] == "Personal Home"  # project, not _vault_


def test_parity_obsidian_personal_frontmatterless_title(tmp_path: Path) -> None:
    """AC-1.6: a frontmatter-less note → H1-synthesized title, same in both paths."""
    a, b, vid = _parity(tmp_path, "obsidian-personal", {
        "03 - Learning/Courses/note.md": "# A Synthesized Title\n\nprose body\n",
    })
    ra, rb = _rows(a, vid), _rows(b, vid)
    assert ra["note"][2] == "A Synthesized Title"  # title (H1 synth)
    assert rb == ra


def test_parity_obsidian_personal_summary_types(tmp_path: Path) -> None:
    """AC-1.3: types karpathy lacks (moc/note/lesson-summary) map under the
    resolved obsidian-personal layout — no UnmappedTypeError, parity holds."""
    a, b, vid = _parity(tmp_path, "obsidian-personal", {
        "03 - Learning/AI/conf.md": "---\ntype: moc\ntitle: Conf MOC\n---\nbody\n",
        "03 - Learning/AI/lec.md": "---\ntype: lesson-summary\ntitle: Lec\n---\nbody\n",
        "03 - Learning/AI/raw.md": "---\ntype: note\ntitle: Raw\n---\nbody\n",
    })
    ra, rb = _rows(a, vid), _rows(b, vid)
    assert ra["conf"][1] == "summary" and "moc" in ra["conf"][3]
    assert ra["lec"][1] == "summary" and "lesson" in ra["lec"][3]
    assert ra["raw"][1] == "summary"
    assert rb == ra


def test_parity_refs_slugified(tmp_path: Path) -> None:
    """AC-1.5: body wikilink targets slugified via slug_strategy — upsert refs ==
    reindex refs (a non-identity layout would otherwise diverge)."""
    a, b, vid = _parity(tmp_path, "obsidian-personal", {
        "05 - Материалы/Бизнес/m.md": "# M\n\nsee [[Заметка Тест]] and [[Idea]]\n",
    })
    ra = _refs(a, vid, "m")
    rb = _refs(b, vid, "m")
    assert ra == rb
    assert ("заметка-тест", "mentioned") in ra  # preserve-unicode slugified target


def test_upsert_then_reindex_no_duplicate(tmp_path: Path) -> None:
    """AC-1.4: upsert then reindex_full → exactly one row (no slug/project drift)."""
    vid = "pvault"
    root = tmp_path / "vault"
    _schema(root, vid, "obsidian-personal")
    f = root / "03 - Learning/Courses/lesson.md"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("---\ntype: lesson-summary\ntitle: L\n---\nbody\n", encoding="utf-8")
    repo = _repo(tmp_path, "g", vid, root)
    upsert_one(vid, f.resolve(), root, repo)
    reindex_full(repo, vid)
    n = repo._connect().execute(
        "SELECT count(*) FROM pages WHERE vault_id=? AND slug='lesson'", (vid,)
    ).fetchone()[0]
    assert n == 1


def test_parity_karpathy_byte_identical(tmp_path: Path) -> None:
    """AC-1.2: karpathy golden anchor — upsert == reindex, unchanged from before."""
    a, b, vid = _parity(tmp_path, "karpathy", {
        "_sources/lesson-x.md": "---\ntype: summary\ntitle: Lesson X\n---\n"
                                 "see [[Some Concept]]\n",
    })
    ra, rb = _rows(a, vid), _rows(b, vid)
    assert rb == ra
    assert ra["lesson-x"][0] == "_vault_"  # karpathy vault-tier project (identity)
    assert _refs(a, vid, "lesson-x") == _refs(b, vid, "lesson-x")


def test_upsert_unmappable_type_exit6(tmp_path: Path) -> None:
    """UC-1/A4: a type not in the resolved layout's type_mapping → exit 6 envelope,
    no traceback (error contract survives the rewire)."""
    vid = "pvault"
    root = tmp_path / "vault"
    _schema(root, vid, "obsidian-personal")
    f = root / "03 - Learning/Courses/weird.md"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("---\ntype: totally-unmapped-xyz\ntitle: W\n---\nbody\n",
                 encoding="utf-8")
    repo = _repo(tmp_path, "u", vid, root)
    try:
        res = upsert_one(vid, f.resolve(), root, repo)
        assert res["_exit_code"] == 6
        assert res["error"] == "UnmappedTypeError"
    finally:
        repo.close()


# --------------------------------------------------------------------------- #
# R-2 FTS full body
# --------------------------------------------------------------------------- #

def _deep_body(deep_term: str) -> str:
    return "# Title\n\n" + ("filler word " * 250) + f"\n\n{deep_term} appears here.\n"


def test_fts_indexes_full_body(tmp_path: Path) -> None:
    """AC-2.1/2.2: a term past char 1000 of the body is found by search; a term in
    the first 1000 chars is still found."""
    vid = "pvault"
    root = tmp_path / "vault"
    _schema(root, vid, "obsidian-personal")
    body = _deep_body("zzdeepterm")
    assert body.index("zzdeepterm") > 1000  # the term really is past the old cap
    f = root / "03 - Learning/Courses/long.md"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("---\ntype: lesson-summary\ntitle: Long\n---\n" + body, encoding="utf-8")
    repo = _repo(tmp_path, "f", vid, root)
    try:
        reindex_full(repo, vid)
        deep = repo.search_pages("zzdeepterm", vaults=[vid])
        assert any(h.page.slug == "long" for h in deep), "deep (>1000) term not found"
        near = repo.search_pages("filler", vaults=[vid])
        assert any(h.page.slug == "long" for h in near), "near (<1000) term not found"
    finally:
        repo.close()


def test_fts_full_body_after_reindex_rebuild(tmp_path: Path) -> None:
    """UC-2/A2: a DB whose row was stored under the OLD 1000-cap misses the deep
    term; `reindex_full` (Class-A→B rebuild, ADR-002 §D8) repopulates the full-body
    corpus → the deep term is then found."""
    vid = "pvault"
    root = tmp_path / "vault"
    _schema(root, vid, "obsidian-personal")
    body = _deep_body("qqlegacyterm")
    f = root / "03 - Learning/Courses/legacy.md"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("---\ntype: lesson-summary\ntitle: Legacy\n---\n" + body, encoding="utf-8")
    repo = _repo(tmp_path, "r", vid, root)
    try:
        # simulate an OLD-cap row: store body_excerpt truncated to 1000 chars
        repo.upsert_page(Page(
            vault_id=vid, slug="legacy", project="Learning/Courses",
            type="summary", title="Legacy",
            file_path="03 - Learning/Courses/legacy.md", tldr=None, date=None,
            last_modified=datetime(2026, 6, 8), file_hash="old",
            frontmatter_json={}, body_excerpt=body[:1000], tags=[]))
        miss = repo.search_pages("qqlegacyterm", vaults=[vid])
        assert not any(h.page.slug == "legacy" for h in miss), "old cap should miss"
        reindex_full(repo, vid)
        hit = repo.search_pages("qqlegacyterm", vaults=[vid])
        assert any(h.page.slug == "legacy" for h in hit), "rebuild should index full body"
    finally:
        repo.close()
