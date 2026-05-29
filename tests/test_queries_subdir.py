"""TASK 007 / bead 007-01 — `_queries/` is a first-class page-bearing subdir.

Asserts the layout registration (constant + PAGE_SUBDIRS/SCAFFOLD_DIRS/
HOST_ONLY_SUBDIRS membership), the `_PATH_TYPE_FALLBACK` type inference, and
that `discover_pages` walks `_queries/` at both the vault and course tiers.
This is the durability prerequisite for the R-6.5e reindex read-side (007-02):
a query page is no good if reindex never re-discovers it.
"""
from __future__ import annotations

from pathlib import Path

from scripts.wiki_index import layout
from scripts.wiki_index.normalization import (
    _infer_type_from_path,
    normalize_frontmatter,
)
from scripts.wiki_index.reindex import discover_pages


def test_queries_subdir_registered() -> None:
    """TC-UNIT-01: the constant exists and is wired into the host subdir sets."""
    assert layout.QUERIES_SUBDIR == "_queries"
    assert layout.QUERIES_SUBDIR in layout.PAGE_SUBDIRS
    assert layout.QUERIES_SUBDIR in layout.SCAFFOLD_DIRS
    assert layout.QUERIES_SUBDIR in layout.HOST_ONLY_SUBDIRS
    # NOT part of the vendored-ingest shared contract.
    assert layout.QUERIES_SUBDIR not in layout.INGEST_SHARED_SUBDIRS


def test_infer_type_from_queries_path() -> None:
    """TC-UNIT-02: a `_queries/` path infers `query` when `type:` is absent."""
    assert _infer_type_from_path(Path("/v/_queries/foo.md")) == "query"


def test_normalize_frontmatter_query_path_fallback() -> None:
    """TC-UNIT-03: `normalize_frontmatter` with no `type:` but a `_queries/`
    source path resolves db_type == 'query'."""
    _updated, db_type = normalize_frontmatter(
        {}, source_path=Path("/v/_queries/foo.md"),
    )
    assert db_type == "query"


def _write(p: Path, body: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


def test_discover_pages_walks_queries_subdir(tmp_path: Path) -> None:
    """TC-E2E-01: `discover_pages` yields `_queries/*.md` at the vault tier and
    the course tier (it was previously invisible to reindex)."""
    vault = tmp_path / "vlt"
    _write(vault / "_queries" / "q1.md", "---\ntype: query\n---\nbody\n")
    _write(vault / "_sources" / "s1.md", "---\ntype: summary\n---\nbody\n")
    _write(
        vault / "Lessons" / "Course A" / "_queries" / "cq.md",
        "---\ntype: query\n---\nbody\n",
    )

    found = discover_pages(vault)
    slugs = {(slug, project) for _path, slug, project in found}

    assert ("q1", layout.VAULT_TIER_PROJECT) in slugs
    assert ("cq", "course-a") in slugs  # course-tier _queries walked too
    # sanity: the source page is still discovered (no regression)
    assert ("s1", layout.VAULT_TIER_PROJECT) in slugs
