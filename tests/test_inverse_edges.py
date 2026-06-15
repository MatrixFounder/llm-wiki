"""TASK 032-02 (R-032-3, ADR-004 D3) — auto-inverse edge derivation (global pass).

Forward edges ride the per-page write (032-01); the INVERSE rows (on the TARGET
page) are derived by a global post-pass in reindex_full — after AM-3, before
_recompute_mentions. Orphan targets get NO inverse (arch-review M1). Idempotent +
bidirectional-author convergent.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from scripts.wiki_index.models import Vault
from scripts.wiki_index.reindex import reindex_full
from scripts.wiki_index.sqlite_repository import SQLiteRepository


def _vault(tmp_path: Path, files: dict[str, str]) -> SQLiteRepository:
    root = tmp_path / "vault"
    root.mkdir()
    (root / "WIKI_SCHEMA.md").write_text(
        '---\nvault_id: cvault\nschema_version: "2.0"\nlanguage: en\nlayout: cybos\n---\n',
        encoding="utf-8")
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    repo = SQLiteRepository(tmp_path / "g.db")
    repo.apply_schema()
    repo.register_vault(Vault(vault_id="cvault", name="cvault", root_path=root,
                              schema_version="2.0", registered_at=datetime(2026, 6, 15)))
    return repo


def _refs(repo: SQLiteRepository) -> set[tuple[str, str, str]]:
    return {(r["page_slug"], r["entity_slug"], r["ref_type"]) for r in
            repo._connect().execute(
                "SELECT page_slug, entity_slug, ref_type FROM page_entity_refs "
                "WHERE vault_id='cvault'").fetchall()}


def test_inverse_derived_for_real_target(tmp_path: Path) -> None:
    """AC-3.1: supersedes: [[d1]] on d2 → BOTH (d2→d1, supersedes) [forward] and
    (d1→d2, superseded-by) [derived inverse, on the target page d1]."""
    repo = _vault(tmp_path, {
        "decisions/d1.md": "---\ntype: decision\ntitle: D1\n---\nbody\n",
        "decisions/d2.md": "---\ntype: decision\ntitle: D2\nsupersedes: [[d1]]\n---\nbody\n",
    })
    try:
        assert reindex_full(repo, "cvault")["skipped"] == []
        refs = _refs(repo)
        assert ("d2", "d1", "supersedes") in refs       # forward
        assert ("d1", "d2", "superseded-by") in refs    # derived inverse
    finally:
        repo.close()


def test_orphan_target_gets_no_inverse(tmp_path: Path) -> None:
    """AC-3.3 (arch M1): an edge to a NON-page target keeps its forward orphan ref
    but derives NO inverse (the enforced FK would otherwise crash)."""
    repo = _vault(tmp_path, {
        "decisions/d2.md": "---\ntype: decision\ntitle: D2\nimplements: [[ghost-req]]\n---\nbody\n",
    })
    try:
        assert reindex_full(repo, "cvault")["skipped"] == []
        refs = _refs(repo)
        assert ("d2", "ghost-req", "implements") in refs           # forward orphan kept
        assert not any(r[0] == "ghost-req" for r in refs)          # no inverse row on a non-page
    finally:
        repo.close()


def test_idempotent_second_full(tmp_path: Path) -> None:
    """AC-3.2: a 2nd reindex --full yields the identical ref set (no inverse pile-up)."""
    files = {
        "decisions/d1.md": "---\ntype: decision\ntitle: D1\n---\nbody\n",
        "decisions/d2.md": "---\ntype: decision\ntitle: D2\ncauses: [[d1]]\n---\nbody\n",
    }
    repo = _vault(tmp_path, files)
    try:
        reindex_full(repo, "cvault")
        first = _refs(repo)
        reindex_full(repo, "cvault")
        assert _refs(repo) == first
        assert ("d2", "d1", "causes") in first and ("d1", "d2", "caused-by") in first
    finally:
        repo.close()


def test_bidirectional_author_converges(tmp_path: Path) -> None:
    """AC-3.2: author writes BOTH directions → PK dedup → exactly one row each."""
    repo = _vault(tmp_path, {
        "decisions/d1.md": "---\ntype: decision\ntitle: D1\nsuperseded_by: [[d2]]\n---\nbody\n",
        "decisions/d2.md": "---\ntype: decision\ntitle: D2\nsupersedes: [[d1]]\n---\nbody\n",
    })
    try:
        reindex_full(repo, "cvault")
        refs = _refs(repo)
        assert sum(1 for r in refs if r == ("d1", "d2", "superseded-by")) == 1
        assert sum(1 for r in refs if r == ("d2", "d1", "supersedes")) == 1
    finally:
        repo.close()


def test_relates_to_symmetric_inverse(tmp_path: Path) -> None:
    repo = _vault(tmp_path, {
        "facts/a.md": "---\ntype: fact\ntitle: A\nrelates_to: [[b]]\n---\nbody\n",
        "facts/b.md": "---\ntype: fact\ntitle: B\n---\nbody\n",
    })
    try:
        reindex_full(repo, "cvault")
        refs = _refs(repo)
        assert ("a", "b", "related") in refs and ("b", "a", "related") in refs
    finally:
        repo.close()


# --------------------------------------------------------------------------- #
# Delta (R-032-3 / AC-3.4) — additions on the un-walked target; removal residual
# --------------------------------------------------------------------------- #
import os
import time as _time

from scripts.wiki_index.reindex import reindex_delta


def _bare_vault(tmp_path: Path) -> tuple[SQLiteRepository, Path]:
    root = tmp_path / "vault"
    root.mkdir()
    (root / "WIKI_SCHEMA.md").write_text(
        '---\nvault_id: cvault\nschema_version: "2.0"\nlanguage: en\nlayout: cybos\n---\n',
        encoding="utf-8")
    (root / "decisions").mkdir()
    (root / "decisions" / "d1.md").write_text(
        "---\ntype: decision\ntitle: D1\n---\nbody\n", encoding="utf-8")
    repo = SQLiteRepository(tmp_path / "g.db")
    repo.apply_schema()
    repo.register_vault(Vault(vault_id="cvault", name="cvault", root_path=root,
                              schema_version="2.0", registered_at=datetime(2026, 6, 15)))
    return repo, root


def test_delta_adds_inverse_on_unwalked_target(tmp_path: Path) -> None:
    """AC-3.4: an edge on a NEW/changed source materializes its inverse on the
    (un-walked) target via the delta global additions pass."""
    repo, root = _bare_vault(tmp_path)
    try:
        reindex_full(repo, "cvault")  # baseline: d1 only, no edges
        (root / "decisions" / "d2.md").write_text(
            "---\ntype: decision\ntitle: D2\nsupersedes: [[d1]]\n---\nbody\n", encoding="utf-8")
        res = reindex_delta(repo, "cvault")
        assert res["skipped"] == []
        refs = _refs(repo)
        assert ("d2", "d1", "supersedes") in refs       # forward (d2 walked)
        assert ("d1", "d2", "superseded-by") in refs    # inverse on UN-walked d1
    finally:
        repo.close()


def test_delta_edge_removal_residual_repaired_by_full(tmp_path: Path) -> None:
    """AC-3.4: removing an edge on --delta leaves a STALE inverse (delta never
    deletes an inverse — provenance-safe); --full repairs it (ADR-004 D4)."""
    repo, root = _bare_vault(tmp_path)
    d2 = root / "decisions" / "d2.md"
    d2.write_text("---\ntype: decision\ntitle: D2\nsupersedes: [[d1]]\n---\nbody\n", encoding="utf-8")
    try:
        reindex_full(repo, "cvault")
        assert ("d1", "d2", "superseded-by") in _refs(repo)
        d2.write_text("---\ntype: decision\ntitle: D2\n---\nbody\n", encoding="utf-8")
        os.utime(d2, (_time.time() + 10, _time.time() + 10))  # re-walk on delta
        reindex_delta(repo, "cvault")
        refs = _refs(repo)
        assert ("d2", "d1", "supersedes") not in refs        # forward removed (d2 re-walked)
        assert ("d1", "d2", "superseded-by") in refs         # inverse STALE (documented residual)
        reindex_full(repo, "cvault")
        assert ("d1", "d2", "superseded-by") not in _refs(repo)  # --full repairs
    finally:
        repo.close()


def test_delta_missing_derivation_from_untouched_source_repaired_by_full(tmp_path: Path) -> None:
    """vdd-multi MEDIUM / ADR-004 D4 divergence class (2): under BIDIRECTIONAL authoring
    (d1 `superseded_by:[[d2]]`, d2 `supersedes:[[d1]]`), removing ONLY d2's `supersedes`
    re-walks only d2; the delta inverse pass is scoped to the touched source {d2}, so it
    never reprocesses d1's still-authored `superseded_by` to re-derive `(d2→d1,
    supersedes)` → the graph is temporarily ASYMMETRIC (the supersedes edge is MISSING),
    repaired by --full. This is the deliberate cost of source-scoping (which also
    prevents class (1)'s resurrection); documented in reindex_delta Step 4.5."""
    repo, root = _bare_vault(tmp_path)
    d1 = root / "decisions" / "d1.md"
    d2 = root / "decisions" / "d2.md"
    d1.write_text("---\ntype: decision\ntitle: D1\nsuperseded_by: [[d2]]\n---\nbody\n", encoding="utf-8")
    d2.write_text("---\ntype: decision\ntitle: D2\nsupersedes: [[d1]]\n---\nbody\n", encoding="utf-8")
    try:
        reindex_full(repo, "cvault")
        refs0 = _refs(repo)
        assert ("d1", "d2", "superseded-by") in refs0   # d1 authored forward
        assert ("d2", "d1", "supersedes") in refs0       # d2 authored forward
        d2.write_text("---\ntype: decision\ntitle: D2\n---\nbody\n", encoding="utf-8")
        os.utime(d2, (_time.time() + 10, _time.time() + 10))  # re-walk only d2 on delta
        reindex_delta(repo, "cvault")
        refs1 = _refs(repo)
        assert ("d1", "d2", "superseded-by") in refs1            # d1's forward untouched
        assert ("d2", "d1", "supersedes") not in refs1           # MISSING — class (2) divergence
        reindex_full(repo, "cvault")
        assert ("d2", "d1", "supersedes") in _refs(repo)         # --full re-derives from d1
    finally:
        repo.close()


# --------------------------------------------------------------------------- #
# vdd-multi fixes: MED-1 (ambiguous cross-project target) + LOW-1 (self-loop)
# --------------------------------------------------------------------------- #
from scripts.wiki_index.reindex import _derive_inverse_edges


def _repo_with_pages(tmp_path: Path, pages: list[tuple[str, str]]):
    repo = SQLiteRepository(tmp_path / "g.db")
    repo.apply_schema()
    repo.register_vault(Vault(vault_id="vtest", name="vtest", root_path=tmp_path,
                              schema_version="2.0", registered_at=datetime(2026, 6, 15)))
    conn = repo._connect()
    for slug, proj in pages:
        conn.execute(
            "INSERT INTO pages (vault_id,slug,project,type,title,file_path,"
            "last_modified,file_hash,frontmatter_json) VALUES ('vtest',?,?,'research',?,?,"
            "'2026-06-15','h','{}')", (slug, proj, slug, f"{proj}/{slug}.md"))
    conn.commit()
    return repo, conn


def _add_ref(conn, page_slug, proj, entity_slug, ref_type) -> None:
    conn.execute(
        "INSERT INTO page_entity_refs (vault_id,page_slug,page_project,entity_slug,ref_type) "
        "VALUES ('vtest',?,?,?,?)", (page_slug, proj, entity_slug, ref_type))
    conn.commit()


def test_inverse_skips_ambiguous_cross_project_slug(tmp_path: Path) -> None:
    """vdd-multi MED-1: a target slug shared across projects → NO inverse derived
    (the project-less forward edge can't disambiguate → never a phantom on the
    wrong page)."""
    repo, conn = _repo_with_pages(tmp_path, [("intro", "p1"), ("intro", "p2"), ("dec", "p3")])
    try:
        _add_ref(conn, "dec", "p3", "intro", "implements")  # ambiguous: intro@p1 + intro@p2
        _derive_inverse_edges(conn, "vtest")
        conn.commit()
        inv = conn.execute(
            "SELECT page_slug,page_project FROM page_entity_refs WHERE vault_id='vtest' "
            "AND ref_type='implemented-by'").fetchall()
        assert inv == []  # no phantom inverse on either intro
    finally:
        repo.close()


def test_inverse_derived_for_unambiguous_target(tmp_path: Path) -> None:
    """Control for MED-1: a UNIQUE target slug DOES get its inverse."""
    repo, conn = _repo_with_pages(tmp_path, [("req", "p1"), ("dec", "p3")])
    try:
        _add_ref(conn, "dec", "p3", "req", "implements")
        _derive_inverse_edges(conn, "vtest")
        conn.commit()
        inv = conn.execute(
            "SELECT page_slug,page_project,entity_slug FROM page_entity_refs "
            "WHERE vault_id='vtest' AND ref_type='implemented-by'").fetchall()
        assert [tuple(r) for r in inv] == [("req", "p1", "dec")]
    finally:
        repo.close()


def test_self_loop_edge_row_cleaned(tmp_path: Path) -> None:
    """vdd-multi LOW-1: a self-loop typed-edge row (e.g. produced by AM-3 alias
    canonicalization, post-extraction) is dropped by the inverse pass."""
    repo, conn = _repo_with_pages(tmp_path, [("a", "_vault_")])
    try:
        _add_ref(conn, "a", "_vault_", "a", "implements")  # self-loop
        _derive_inverse_edges(conn, "vtest")
        conn.commit()
        rows = conn.execute(
            "SELECT 1 FROM page_entity_refs WHERE vault_id='vtest' AND page_slug='a' "
            "AND entity_slug='a'").fetchall()
        assert rows == []
    finally:
        repo.close()
