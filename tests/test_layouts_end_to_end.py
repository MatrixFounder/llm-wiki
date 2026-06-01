"""TASK 012-07 — ship dev-project.yaml + obsidian-personal.yaml built-ins, end-to-end.

The R-X1 completion gate: both new built-in layouts validate (schema + ReDoS +
project_pattern), and index their fixtures with correct type-tags / projects /
slugs — no PK collisions, no `.base` leak. Karpathy byte-identity is held by the
golden anchor (separate module).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from scripts.wiki_index.layout_config import load_layout_config
from scripts.wiki_index.models import Vault
from scripts.wiki_index.reindex import reindex_full
from scripts.wiki_index.sqlite_repository import SQLiteRepository


def _register(repo: SQLiteRepository, vault_id: str, root: Path) -> None:
    repo.register_vault(Vault(
        vault_id=vault_id, name=vault_id, root_path=root,
        schema_version="2.0", registered_at=datetime(2026, 5, 26)))


def _wiki_schema(root: Path, vault_id: str, layout: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "WIKI_SCHEMA.md").write_text(
        f'---\nvault_id: {vault_id}\nschema_version: "2.0"\nlanguage: en\n'
        f'layout: {layout}\n---\n', encoding="utf-8")


# --------------------------------------------------------------------------- #
# Both built-ins load + validate + pass the gates
# --------------------------------------------------------------------------- #


def test_builtin_layouts_load_and_validate(tmp_path: Path) -> None:
    root = tmp_path / "v"; root.mkdir()
    for name in ("karpathy", "dev-project", "obsidian-personal"):
        cfg = load_layout_config(root, {"layout": name})  # validates + ReDoS + PW-J checks
        assert cfg.layout == name
        assert len(cfg.paths) >= 1


# --------------------------------------------------------------------------- #
# dev-project: index docs/ + type-tags + search + id-ref
# --------------------------------------------------------------------------- #


def test_dev_project_indexes_and_searches(tmp_path: Path) -> None:
    vault = tmp_path / "dv"
    _wiki_schema(vault, "dev-proj", "dev-project")
    (vault / "adr").mkdir(parents=True)
    (vault / "adr" / "adr-002-layering.md").write_text(
        "# ADR-002: Data Layering\n\nSupersedes ADR-001. See [related](adr-001-x.md).\n",
        encoding="utf-8")  # no frontmatter → glob_type=adr + H1 title
    (vault / "tasks").mkdir(parents=True)
    (vault / "tasks" / "task-012-x.md").write_text(
        "---\ntype: task\ntitle: A Task\n---\n\nbody mentioning ADR-002\n", encoding="utf-8")
    (vault / "ROADMAP.md").write_text("# Roadmap\n\nitems\n", encoding="utf-8")

    repo = SQLiteRepository(tmp_path / "g.db")
    repo.apply_schema()
    _register(repo, "dev-proj", vault)
    try:
        result = reindex_full(repo, "dev-proj")
        assert result["pages"] == 3
        rows = {r["slug"]: (r["type"], r["title"]) for r in repo._connect().execute(
            "SELECT slug, type, title FROM pages WHERE vault_id='dev-proj'").fetchall()}
        # tag-route: adr/roadmap → research, task → brief (zero DDL)
        assert rows["adr-002-layering"] == ("research", "ADR-002: Data Layering")
        assert rows["roadmap"][0] == "research"
        assert rows["task-012-x"][0] == "brief"
        # FTS search finds the ADR (term without the FTS5-special hyphen)
        hits = repo.search_pages("Layering", vaults=["dev-proj"])
        assert any(h.page.slug == "adr-002-layering" for h in hits)
        # dev-project id-ref extraction: "ADR-002" in the task body → a ref row.
        # TASK 014 / R-X1-REF-SLUGIFY: ref targets are now slugified via the
        # layout's slug_strategy (dev-project = transliterate), so "ADR-002"
        # resolves to slug "adr-002" — matching the page slug it links to (the
        # whole point of the fix; an un-slugified "ADR-002" would be a false orphan).
        ref_targets = {r["entity_slug"] for r in repo._connect().execute(
            "SELECT entity_slug FROM page_entity_refs WHERE vault_id='dev-proj'").fetchall()}
        assert "adr-002" in ref_targets   # id-ref rule, transliterated to slug form
        assert "adr-001" in ref_targets   # id-ref rule (from the ADR body)
        assert "adr-001-x" in ref_targets  # markdown-link stem transform
    finally:
        repo.close()


# --------------------------------------------------------------------------- #
# obsidian-personal: deep hierarchy, Cyrillic, system dirs, .base exclusion
# --------------------------------------------------------------------------- #


def _build_obsidian_vault(vault: Path) -> None:
    """Reusable obsidian-personal fixture (TASK 012-02/07): numbered folders +
    deep hierarchy + Cyrillic + system dir + an ignored .base."""
    _wiki_schema(vault, "obs-vault", "obsidian-personal")
    notes = {
        "02 - Personal Home/Household/intake.md": "# Household intake\nbody\n",
        "02 - Personal Home/Purchases/intake.md": "# Purchases intake\nbody\n",
        "02 - Personal Home/Квартиры.md": "# Квартиры\nbody\n",
        "_inbox/draft.md": "# A draft\nbody\n",
        "Top Note.md": "# Top\nbody\n",
    }
    for rel, body in notes.items():
        p = vault / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    (vault / "01 - Inbox (base).base").write_text("not markdown", encoding="utf-8")
    (vault / ".obsidian").mkdir()
    (vault / ".obsidian" / "workspace.json").write_text("{}", encoding="utf-8")


def test_obsidian_personal_indexes_without_collision(tmp_path: Path) -> None:
    vault = tmp_path / "ov"
    _build_obsidian_vault(vault)
    repo = SQLiteRepository(tmp_path / "g.db")
    repo.apply_schema()
    _register(repo, "obs-vault", vault)
    try:
        result = reindex_full(repo, "obs-vault")
        rows = {(r["slug"], r["project"]) for r in repo._connect().execute(
            "SELECT slug, project FROM pages WHERE vault_id='obs-vault'").fetchall()}
        # two same-named intake.md → two distinct projects (no PK collision)
        assert ("intake", "Personal Home/Household") in rows
        assert ("intake", "Personal Home/Purchases") in rows
        # Cyrillic stem under preserve-unicode → lowercased, kept
        assert ("квартиры", "Personal Home") in rows
        # _inbox draft (project from the system-folder glob)
        assert ("draft", "_inbox") in rows
        # standalone root note → preserve-unicode slug + _root_ project
        assert ("top-note", "_root_") in rows
        # NO .base / .obsidian leakage
        assert all(".base" not in slug and "workspace" not in slug for (slug, _) in rows)
        assert result["pages"] == 5
    finally:
        repo.close()
