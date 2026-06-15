"""TASK 031 / R-031-1/2 — cybos layout end-to-end.

Builds a cybos vault with one note per typed knowledge class (folder-glob inferred
type, frontmatter-less → H1-synthesised title) and reindexes it, asserting each
note lands with the correct `pages.type` (db_type) + filterable tag, no
`UnmappedTypeError`, no slug collisions. AC-2.2/2.3.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from scripts.wiki_index.models import Vault
from scripts.wiki_index.reindex import reindex_full
from scripts.wiki_index.sqlite_repository import SQLiteRepository

# folder → (note stem, expected db_type, expected tag)
_CLASSES = {
    "decisions": ("use-rabbitmq", "research", "decision"),
    "requirements": ("req-throughput", "brief", "requirement"),
    "risks": ("risk-queue-overflow", "research", "risk"),
    "incidents": ("inc-2026-06-queue", "research", "incident"),
    "hypotheses": ("hyp-polling-slow", "research", "hypothesis"),
    "facts": ("fact-rabbit-amqp", "concept", "fact"),
    "events": ("evt-release-4-3", "summary", "event"),
}


def _cybos_vault(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "WIKI_SCHEMA.md").write_text(
        '---\nvault_id: cybos-vault\nschema_version: "2.0"\nlanguage: en\n'
        'layout: cybos\n---\n', encoding="utf-8")
    for folder, (stem, _dbt, _tag) in _CLASSES.items():
        p = root / folder / f"{stem}.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        # frontmatter-less → type comes from the folder glob; title from H1
        p.write_text(f"# {stem.replace('-', ' ').title()}\n\nbody for {folder}\n",
                     encoding="utf-8")


def _repo(tmp_path: Path, root: Path) -> SQLiteRepository:
    repo = SQLiteRepository(tmp_path / "cybos.db")
    repo.apply_schema()
    repo.register_vault(Vault(
        vault_id="cybos-vault", name="cybos-vault", root_path=root,
        schema_version="2.0", registered_at=datetime(2026, 6, 13)))
    return repo


def _rows(repo: SQLiteRepository) -> dict[str, tuple[str, tuple[str, ...]]]:
    out: dict[str, tuple[str, tuple[str, ...]]] = {}
    for r in repo._connect().execute(
        "SELECT slug, type, frontmatter_json FROM pages WHERE vault_id=?",
        ("cybos-vault",),
    ).fetchall():
        tags = tuple(sorted(json.loads(r["frontmatter_json"]).get("tags") or []))
        out[r["slug"]] = (r["type"], tags)
    return out


def test_cybos_e2e_seven_classes_route(tmp_path: Path) -> None:
    """AC-2.2: each typed-knowledge note reindexes to its mapped db_type + tag;
    no UnmappedTypeError, no slug collisions."""
    root = tmp_path / "vault"
    _cybos_vault(root)
    repo = _repo(tmp_path, root)
    try:
        result = reindex_full(repo, "cybos-vault")
        assert result["skipped"] == [], f"unexpected skips: {result['skipped']}"
        assert result["slug_collisions"] == []
        rows = _rows(repo)
        for _folder, (stem, db_type, tag) in _CLASSES.items():
            assert stem in rows, f"{stem} not indexed (rows: {set(rows)})"
            got_type, got_tags = rows[stem]
            assert got_type == db_type, f"{stem}: type {got_type} != {db_type}"
            assert tag in got_tags, f"{stem}: tag {tag} not in {got_tags}"
    finally:
        repo.close()


def test_cybos_edges_extracted(tmp_path: Path) -> None:
    """TASK 032 (R-032-2): the event-graph edge keys are now EXTRACTED as typed
    FORWARD refs (was inert in TASK 031). A decision page's implements/supersedes/
    caused_by frontmatter → ref_type implements/supersedes/caused-by rows (targets
    slugified via the cybos transliterate strategy). Inverse derivation = 032-02."""
    root = tmp_path / "vault"
    root.mkdir()
    (root / "WIKI_SCHEMA.md").write_text(
        '---\nvault_id: cybos-vault\nschema_version: "2.0"\nlanguage: en\n'
        'layout: cybos\n---\n', encoding="utf-8")
    (root / "decisions").mkdir()
    (root / "decisions" / "d1.md").write_text(
        "---\ntype: decision\ntitle: D1\nimplements: REQ-1\nsupersedes: DEC-0\n"
        "caused_by: INC-9\n---\n\nA decision body with no body links.\n",
        encoding="utf-8")
    repo = _repo(tmp_path, root)
    try:
        result = reindex_full(repo, "cybos-vault")
        assert result["skipped"] == []
        refs = repo._connect().execute(
            "SELECT ref_type FROM page_entity_refs WHERE vault_id=? AND page_slug=?",
            ("cybos-vault", "d1"),
        ).fetchall()
        pairs = {(r["entity_slug"], r["ref_type"]) for r in repo._connect().execute(
            "SELECT entity_slug, ref_type FROM page_entity_refs WHERE vault_id=? "
            "AND page_slug=?", ("cybos-vault", "d1")).fetchall()}
        assert ("req-1", "implements") in pairs
        assert ("dec-0", "supersedes") in pairs
        assert ("inc-9", "caused-by") in pairs
    finally:
        repo.close()


def test_cybos_override_union_and_summary_overlap(tmp_path: Path) -> None:
    """UC-31-5 + arch-review 🟡-2: a per-vault `.wiki/layout.yaml` type_mapping
    override UNIONs with the built-in cybos mapping (adds meeting-summary→summary)
    — the built-in classes STILL map AND the new one works; the event note and the
    meeting-summary note both land in `pages.type=summary` with DISTINCT tags."""
    root = tmp_path / "vault"
    root.mkdir()
    (root / "WIKI_SCHEMA.md").write_text(
        '---\nvault_id: cybos-vault\nschema_version: "2.0"\nlanguage: en\n'
        'layout: cybos\n---\n', encoding="utf-8")
    (root / ".wiki").mkdir()
    (root / ".wiki" / "layout.yaml").write_text(
        "type_mapping:\n  meeting-summary: {db_type: summary, tag: meeting}\n",
        encoding="utf-8")
    (root / "events").mkdir()
    (root / "events" / "release.md").write_text(
        "# Release 4.3 shipped\n\nA milestone occurrence.\n", encoding="utf-8")
    (root / "events" / "standup.md").write_text(
        "---\ntype: meeting-summary\ntitle: Standup\n---\n\nstandup notes\n",
        encoding="utf-8")
    (root / "decisions").mkdir()
    (root / "decisions" / "d.md").write_text("# D\n\nbody\n", encoding="utf-8")
    repo = _repo(tmp_path, root)
    try:
        result = reindex_full(repo, "cybos-vault")
        assert result["skipped"] == []
        rows = _rows(repo)
        # the built-in cybos class STILL routes (override UNIONs, does not replace)
        assert rows["d"] == ("research", ("decision",))
        # event + meeting-summary share db_type=summary but carry distinct tags
        assert rows["release"][0] == "summary" and "event" in rows["release"][1]
        assert rows["standup"][0] == "summary" and "meeting" in rows["standup"][1]
    finally:
        repo.close()
