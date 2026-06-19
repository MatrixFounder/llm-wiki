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


def test_obsidian_personal_indexes_summary_types(tmp_path: Path) -> None:
    """Q-019-9: obsidian-personal type_mapping must map the AI/meeting/lesson
    summary types its vaults actually produce. Before the fix, a note carrying
    ``type: lesson-summary`` (etc.) raised UnmappedTypeError and was silently
    dropped into ``skipped`` — the compounding-knowledge loop was dead for exactly
    the content this layout exists to capture. This pins the regression."""
    vault = tmp_path / "sv"
    _wiki_schema(vault, "sum-vault", "obsidian-personal")
    # raw_type → (expected db_type, expected marker tag)
    cases = {
        "summary":         ("summary", None),
        "lesson-summary":  ("summary", "lesson"),
        "meeting-summary": ("summary", "meeting"),
        "webinar-summary": ("summary", "webinar"),
        "moc":             ("summary", "moc"),
        # TASK 025 / R-3: the rest of the common summary family (additive, tag-only).
        "tutorial-summary": ("summary", "tutorial"),
        "article-summary":  ("summary", "article"),
        "book-summary":     ("summary", "book"),
        "video-summary":    ("summary", "video"),
        "podcast-summary":  ("summary", "podcast"),
        "course-summary":   ("summary", "course"),
    }
    for i, raw_type in enumerate(cases):
        p = vault / "03 - Learning" / "Course" / f"{i:02d}-note.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            f"---\ntype: {raw_type}\ntitle: {raw_type} note\n---\n\nbody\n",
            encoding="utf-8")
    repo = SQLiteRepository(tmp_path / "g.db")
    repo.apply_schema()
    _register(repo, "sum-vault", vault)
    try:
        result = reindex_full(repo, "sum-vault")
        # every summary note indexed — NONE dropped via UnmappedTypeError
        assert result["pages"] == len(cases)
        assert result["skipped"] == []
        import json as _json
        rows = {r["title"]: (r["type"], _json.loads(r["frontmatter_json"]).get("tags") or [])
                for r in repo._connect().execute(
                    "SELECT title, type, frontmatter_json FROM pages "
                    "WHERE vault_id='sum-vault'").fetchall()}
        for raw_type, (db_type, marker) in cases.items():
            db_t, tags = rows[f"{raw_type} note"]
            assert db_t == db_type, f"{raw_type} → db_type {db_t!r} (want {db_type!r})"
            if marker is not None:
                assert marker in tags, f"{raw_type} missing marker tag {marker!r} in {tags}"
    finally:
        repo.close()


def test_obsidian_personal_ignores_raw_and_staging(tmp_path: Path) -> None:
    """TASK 025 / R-4: the obsidian-personal built-in must keep the wiki-sync scratch
    trees (`_raw/`, `.staging/`) OUT of the search index — raw imports and the convert
    staging area are not distilled knowledge. A distilled note beside them IS indexed."""
    vault = tmp_path / "rv"
    _wiki_schema(vault, "raw-vault", "obsidian-personal")
    files = {
        "03 - Learning/Course/_raw/dump.md": "# raw dump\nundistilled\n",
        "03 - Learning/Course/.staging/converted.md": "# staged\nconverted\n",
        "03 - Learning/Course/real-note.md": "# Real note\ndistilled knowledge\n",
    }
    for rel, body in files.items():
        p = vault / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    repo = SQLiteRepository(tmp_path / "g.db")
    repo.apply_schema()
    _register(repo, "raw-vault", vault)
    try:
        reindex_full(repo, "raw-vault")
        slugs = {r["slug"] for r in repo._connect().execute(
            "SELECT slug FROM pages WHERE vault_id='raw-vault'").fetchall()}
        assert slugs == {"real-note"}, f"scratch trees leaked into the index: {slugs}"
    finally:
        repo.close()


def test_karpathy_ignores_sources_raw_no_phantom_or_clobber(tmp_path: Path) -> None:
    """Round-9 HIGH: wiki-import stages its untranslated capture at `_sources/_raw/<slug>.md`.
    Karpathy's RECURSIVE `_sources/**/*.md` glob would otherwise index that as a phantom source
    page — and since the raw and the curated note can share the same title-derived slug, the
    `(vault_id, slug, project)` upsert would non-deterministically clobber the real note's row.
    The `**/_raw/**` ignore must keep `_sources/_raw/` out of the index entirely."""
    vault = tmp_path / "kv"
    _wiki_schema(vault, "kvault", "karpathy")
    # all carry `type: summary` (karpathy _sources needs an explicit type) — so the _raw
    # captures would index + clobber IF they weren't excluded; the ignore is what stops them.
    fm = "---\ntype: summary\n---\n"
    files = {
        "_sources/real-note.md": fm + "# Real note\n\nthe curated, translated summary\n",
        "_sources/_raw/real-note.md": fm + "# Raw original\n\nuntranslated H-6 capture\n",
        "Lessons/C/_sources/lesson.md": fm + "# Lesson\n\ncourse-tier curated note\n",
        "Lessons/C/_sources/_raw/lesson.md": fm + "# Raw\n\ncourse-tier untranslated capture\n",
    }
    for rel, body in files.items():
        p = vault / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    repo = SQLiteRepository(tmp_path / "k.db")
    repo.apply_schema()
    _register(repo, "kvault", vault)
    try:
        reindex_full(repo, "kvault")
        rows = repo._connect().execute(
            "SELECT slug, file_path FROM pages WHERE vault_id='kvault'").fetchall()
        paths = {r["file_path"] for r in rows}
        # the curated notes ARE indexed; NEITHER _raw capture leaked in (no phantom, no clobber)
        assert not any("_raw" in p for p in paths), f"_sources/_raw leaked into the index: {paths}"
        assert "_sources/real-note.md" in paths
        assert "Lessons/C/_sources/lesson.md" in paths
    finally:
        repo.close()


def test_cybos_indexes_wiki_import_concept_pages(tmp_path: Path) -> None:
    """Round-10 HIGH: wiki-import files `<folder>/_concepts/<slug>.md` (type: concept). cybos's
    recursive per-folder globs DISCOVER it; with the added `concept` type_mapping it must INDEX
    as db_type concept (rebuildable by `wiki-reindex --full`) instead of UnmappedTypeError-skip —
    else the Class A concept markdown is not DB-rebuildable (Class A/B invariant breach)."""
    vault = tmp_path / "cv"
    _wiki_schema(vault, "cybvault", "cybos")
    files = {
        "decisions/some-decision.md": "---\ntype: decision\n---\n# D\n\nrationale\n",
        "decisions/_concepts/bonding-curve.md":
            "---\ntype: concept\n---\n# Bonding curve\n\nan AMM pricing curve\n",
    }
    for rel, body in files.items():
        p = vault / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    repo = SQLiteRepository(tmp_path / "c.db")
    repo.apply_schema()
    _register(repo, "cybvault", vault)
    try:
        reindex_full(repo, "cybvault")
        by_slug = {r["slug"]: r["type"] for r in repo._connect().execute(
            "SELECT slug, type FROM pages WHERE vault_id='cybvault'").fetchall()}
        assert by_slug.get("bonding-curve") == "concept", \
            f"wiki-import concept page not indexed/rebuilt on cybos: {by_slug}"
        assert "some-decision" in by_slug
        # and the entity row is rebuilt too (the entity-graph half of the construct path)
        ents = {r["slug"] for r in repo._connect().execute(
            "SELECT slug FROM entities WHERE vault_id='cybvault'").fetchall()}
        assert "bonding-curve" in ents, f"concept entity row not rebuilt on cybos: {ents}"
    finally:
        repo.close()


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
