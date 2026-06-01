"""TASK 012-00 — Golden byte-identity snapshot harness (the regression anchor).

GOLDEN — captured against the pre-TASK-012 (hardcoded) layout engine; must not
drift (ADR-002 §D8 rebuildability / R-X1 byte-identity invariant). The literals
below ARE the contract: the config-driven rewrite (012-01..07) must reproduce
them bit-for-bit (modulo `last_modified`/`file_hash`/`id`, which are stripped).

The golden vault is built in-test and deliberately exercises every byte-identity
surface so a later bead cannot drift a shape the snapshot never saw:
  - every `PAGE_SUBDIRS` member (_sources, _concepts, _entities, _queries,
    _verifications) at the root tier;
  - the `Lessons/<Course>/` course tier, including a NESTED sub-dir page
    (rglob recursion);
  - TYPE_MAPPING tag-injection (`external` → tag, `lesson-summary` → tag);
  - all three reindex ref read-sides: `mentioned` ([[wikilink]]), `cited`
    (R-6.5e `cites:` frontmatter), `verifies` (R-8.5e `verifies:` frontmatter).

This module must stay GREEN at every bead boundary of TASK 012. A red here during
012-01..07 means a byte-identity regression — stop and fix before proceeding.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

from scripts.wiki_index.layout import PAGE_SUBDIRS
from scripts.wiki_index.models import Vault
from scripts.wiki_index.reindex import discover_pages, reindex_full
from scripts.wiki_index.sqlite_repository import SQLiteRepository


class _Snapshot(NamedTuple):
    discover: list[tuple[str, str, str]]
    pages: list[tuple[str, str, str, tuple[str, ...], str]]
    refs: list[tuple[str, str, str, str]]

# --------------------------------------------------------------------------- #
# Golden vault builder
# --------------------------------------------------------------------------- #


def _write(vault: Path, rel: str, fm: str, body: str) -> None:
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\n{fm}\n---\n\n{body}\n", encoding="utf-8")


def _build_golden_vault(root: Path) -> None:
    (root / "WIKI_SCHEMA.md").write_text(
        '---\nname: WIKI_SCHEMA\nvault_id: golden-vault\nschema_version: "2.0"\n'
        'language: en\nlayout: per-project\ndescription: "byte-identity golden"\n---\n',
        encoding="utf-8",
    )
    # Root tier — every PAGE_SUBDIRS member.
    _write(root, "_sources/src-one.md",
           "type: summary\ntitle: Source One\ndate: 2026-01-01",
           "Body of source one. Mentions [[Shadow AI]].")
    _write(root, "_concepts/shadow-ai.md",
           "type: concept\ntitle: Shadow AI\ndate: 2026-01-02",
           "A concept. See [[src-one]].")
    _write(root, "_entities/acme-corp.md",
           "type: external\ntitle: Acme Corp\ndate: 2026-01-03",
           "An entity page.")
    _write(root, "_queries/what-is-shadow-ai.md",
           "type: query\ntitle: What is Shadow AI?\ndate: 2026-01-04\n"
           "cites:\n  - _vault_/shadow-ai",
           "A filed query answer citing [[shadow-ai]].")
    _write(root, "_verifications/verify-what-is-shadow-ai.md",
           "type: verification\ntitle: Verdict\ndate: 2026-01-05\n"
           "verifies: _vault_/what-is-shadow-ai\nverdict: pass",
           "A verdict page.")
    # Course tier — nested sub-dir to exercise rglob recursion.
    _write(root, "Lessons/Course-X/_sources/lesson-src.md",
           "type: lesson-summary\ntitle: Lesson Source\ndate: 2026-01-06",
           "Course-local source.")
    _write(root, "Lessons/Course-X/_concepts/nested/deep-concept.md",
           "type: concept\ntitle: Deep Concept\ndate: 2026-01-07",
           "Nested course concept.")


def _snapshot(repo: SQLiteRepository, root: Path, vault_id: str) -> _Snapshot:
    """Normalize the engine output to its content-only projection (strip
    volatile columns: last_modified / file_hash / id / registered_at)."""
    discover = sorted(
        (p.relative_to(root).as_posix(), slug, project)
        for (p, slug, project) in discover_pages(root)
    )
    reindex_full(repo, vault_id)
    conn = repo._connect()
    pages = sorted(
        (
            str(r["slug"]), str(r["project"]), str(r["type"]),
            tuple(sorted(json.loads(r["frontmatter_json"]).get("tags", []))),
            str(r["file_path"]),
        )
        for r in conn.execute(
            "SELECT slug, project, type, frontmatter_json, file_path "
            "FROM pages WHERE vault_id = ?", (vault_id,)
        ).fetchall()
    )
    refs = sorted(
        (str(r["page_slug"]), str(r["page_project"]),
         str(r["entity_slug"]), str(r["ref_type"]))
        for r in conn.execute(
            "SELECT page_slug, page_project, entity_slug, ref_type "
            "FROM page_entity_refs WHERE vault_id = ?", (vault_id,)
        ).fetchall()
    )
    return _Snapshot(discover=discover, pages=pages, refs=refs)


# --------------------------------------------------------------------------- #
# Frozen golden (the contract). Captured 2026-06-01 against the pre-TASK-012 engine.
# --------------------------------------------------------------------------- #

GOLDEN_DISCOVER: list[tuple[str, str, str]] = [
    ("Lessons/Course-X/_concepts/nested/deep-concept.md", "deep-concept", "course-x"),
    ("Lessons/Course-X/_sources/lesson-src.md", "lesson-src", "course-x"),
    ("_concepts/shadow-ai.md", "shadow-ai", "_vault_"),
    ("_entities/acme-corp.md", "acme-corp", "_vault_"),
    ("_queries/what-is-shadow-ai.md", "what-is-shadow-ai", "_vault_"),
    ("_sources/src-one.md", "src-one", "_vault_"),
    ("_verifications/verify-what-is-shadow-ai.md", "verify-what-is-shadow-ai", "_vault_"),
]

GOLDEN_PAGES: list[tuple[str, str, str, tuple[str, ...], str]] = [
    ("acme-corp", "_vault_", "concept", ("external",), "_entities/acme-corp.md"),
    ("deep-concept", "course-x", "concept", (), "Lessons/Course-X/_concepts/nested/deep-concept.md"),
    ("lesson-src", "course-x", "summary", ("lesson-summary",), "Lessons/Course-X/_sources/lesson-src.md"),
    ("shadow-ai", "_vault_", "concept", (), "_concepts/shadow-ai.md"),
    ("src-one", "_vault_", "summary", (), "_sources/src-one.md"),
    ("verify-what-is-shadow-ai", "_vault_", "verification", (), "_verifications/verify-what-is-shadow-ai.md"),
    ("what-is-shadow-ai", "_vault_", "query", (), "_queries/what-is-shadow-ai.md"),
]

GOLDEN_REFS: list[tuple[str, str, str, str]] = [
    ("shadow-ai", "_vault_", "src-one", "mentioned"),
    ("src-one", "_vault_", "Shadow AI", "mentioned"),
    ("verify-what-is-shadow-ai", "_vault_", "what-is-shadow-ai", "verifies"),
    ("what-is-shadow-ai", "_vault_", "shadow-ai", "cited"),
    ("what-is-shadow-ai", "_vault_", "shadow-ai", "mentioned"),
]


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


def _make(tmp_path: Path) -> tuple[SQLiteRepository, Path]:
    root = tmp_path / "golden-vault"
    root.mkdir()
    _build_golden_vault(root)
    repo = SQLiteRepository(tmp_path / "g.db")
    repo.apply_schema()
    repo.register_vault(Vault(
        vault_id="golden-vault", name="golden-vault", root_path=root,
        schema_version="2.0", registered_at=datetime(2026, 5, 26),
    ))
    return repo, root


def test_fixture_covers_all_page_subdirs_and_nested_course(tmp_path: Path) -> None:
    """Precondition (plan-review MINOR-1): the golden vault exercises every
    PAGE_SUBDIRS member AND ≥1 nested course-tier page, so the byte-identity
    contract's COVERAGE is pinned, not assumed."""
    root = tmp_path / "golden-vault"
    root.mkdir()
    _build_golden_vault(root)
    for sub in PAGE_SUBDIRS:
        assert (root / sub).is_dir(), f"golden vault missing PAGE_SUBDIRS member {sub}"
    nested = root / "Lessons" / "Course-X" / "_concepts" / "nested" / "deep-concept.md"
    assert nested.is_file(), "golden vault missing a nested course-tier page"


def test_discover_pages_snapshot_stable(tmp_path: Path) -> None:
    """discover_pages output (as a set AND a sorted list) is byte-identical to
    the frozen golden. Both forms are pinned so 012-02's stable sort is tolerated."""
    repo, root = _make(tmp_path)
    try:
        got = sorted(
            (p.relative_to(root).as_posix(), slug, project)
            for (p, slug, project) in discover_pages(root)
        )
        assert got == GOLDEN_DISCOVER
        assert set(got) == set(GOLDEN_DISCOVER)
    finally:
        repo.close()


def test_reindex_full_rows_snapshot_stable(tmp_path: Path) -> None:
    """reindex_full pages + refs rows (content-only projection) are byte-identical
    to the frozen golden — covers TYPE_MAPPING tag-injection + the mentioned/cited/
    verifies ref read-sides."""
    repo, root = _make(tmp_path)
    try:
        snap = _snapshot(repo, root, "golden-vault")
        assert snap.pages == GOLDEN_PAGES
        assert snap.refs == GOLDEN_REFS
        # discover re-checked inside the snapshot for completeness
        assert snap.discover == GOLDEN_DISCOVER
    finally:
        repo.close()
