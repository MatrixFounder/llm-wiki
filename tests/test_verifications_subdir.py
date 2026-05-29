"""TASK 008 / bead 008-02 — `_verifications/` is a first-class page-bearing subdir
AND `verification` is type-mapped.

Asserts the layout registration (constant + PAGE_SUBDIRS/SCAFFOLD_DIRS/
HOST_ONLY_SUBDIRS membership — the second member of the R-X1-forward role-split),
the `TYPE_MAPPING["verification"]` entry (without which `normalize_frontmatter`
raises `UnmappedTypeError` → the verdict page is silently skipped on reindex,
the Arch-M-1 / TASK-007-C-1 "layout.py alone is insufficient" trap), the
`_PATH_TYPE_FALLBACK` inference, and that `discover_pages` walks `_verifications/`.
This is the durability prerequisite for the R-8.5e reindex read-side (008-03).
"""
from __future__ import annotations

from pathlib import Path

from scripts.wiki_index import layout
from scripts.wiki_index.normalization import (
    _infer_type_from_path,
    normalize_frontmatter,
)
from scripts.wiki_index.reindex import discover_pages


def test_verifications_subdir_registered() -> None:
    """TC-UNIT-03 (layout chokepoint): constant wired into the host subdir sets."""
    assert layout.VERIFICATIONS_SUBDIR == "_verifications"
    assert layout.VERIFICATIONS_SUBDIR in layout.PAGE_SUBDIRS
    assert layout.VERIFICATIONS_SUBDIR in layout.SCAFFOLD_DIRS
    assert layout.VERIFICATIONS_SUBDIR in layout.HOST_ONLY_SUBDIRS
    # NOT part of the vendored-ingest shared contract (host-only, like _queries).
    assert layout.VERIFICATIONS_SUBDIR not in layout.INGEST_SHARED_SUBDIRS


def test_type_mapping_admits_verification() -> None:
    """TC-UNIT-01: `normalize_frontmatter` with an explicit `type: verification`
    resolves db_type == 'verification' — NO `UnmappedTypeError` (the load-bearing
    half of the §D8 spine; without it the verdict page is skipped on reindex)."""
    _updated, db_type = normalize_frontmatter({"type": "verification"})
    assert db_type == "verification"


def test_infer_type_from_verifications_path() -> None:
    """TC-UNIT-02: a `_verifications/` path infers `verification` when `type:` absent."""
    assert _infer_type_from_path(Path("/v/_verifications/foo.md")) == "verification"


def test_normalize_frontmatter_verification_path_fallback() -> None:
    """TC-UNIT-02b: `normalize_frontmatter` with no `type:` but a `_verifications/`
    source path resolves db_type == 'verification'."""
    _updated, db_type = normalize_frontmatter(
        {}, source_path=Path("/v/_verifications/foo.md"),
    )
    assert db_type == "verification"


def _write(p: Path, body: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


def test_discover_pages_walks_verifications_subdir(tmp_path: Path) -> None:
    """TC-E2E-01: `discover_pages` yields `_verifications/*.md` at the vault tier
    and the course tier."""
    vault = tmp_path / "vlt"
    _write(vault / "_verifications" / "v1.md", "---\ntype: verification\n---\nbody\n")
    _write(vault / "_sources" / "s1.md", "---\ntype: summary\n---\nbody\n")
    _write(
        vault / "Lessons" / "Course A" / "_verifications" / "cv.md",
        "---\ntype: verification\n---\nbody\n",
    )

    found = discover_pages(vault)
    slugs = {(slug, project) for _path, slug, project in found}

    assert ("v1", layout.VAULT_TIER_PROJECT) in slugs
    assert ("cv", "course-a") in slugs  # course-tier _verifications walked too
    assert ("s1", layout.VAULT_TIER_PROJECT) in slugs  # no regression
