"""Tests for ManualSourceAdapter real impl (task-001-24)."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.wiki_index.security import PathTraversalError
from scripts.wiki_source.base import SourceItem
from scripts.wiki_source.manual import ManualSourceAdapter
from scripts.wiki_source.parsing import (
    compute_file_hash,
    derive_slug,
    extract_wiki_links,
)


@pytest.fixture
def adapter():
    return ManualSourceAdapter()


def test_e2e_01_ingest_minimal_vault_alpha(adapter, minimal_vault: Path):
    """Ingest `alpha.md` from minimal-vault fixture."""
    item = SourceItem(
        kind="manual",
        source_path=minimal_vault / "_sources" / "alpha.md",
        vault_root=minimal_vault,
        vault_id="minimal-test",
    )
    out = adapter.fetch(item)
    assert out.page_slug == "alpha"
    assert out.project == "_vault_"
    assert out.trust_level == "high"
    assert out.frontmatter["type"] == "summary"
    assert out.frontmatter["title"] == "Alpha source"
    # alpha.md links to [[example-concept]] and [[dangling-link]]
    targets = {r.entity_slug for r in out.refs}
    assert "example-concept" in targets
    assert "dangling-link" in targets
    assert all(r.trust_level == "high" for r in out.refs)


def test_e2e_02_path_traversal_rejected(adapter, minimal_vault: Path, tmp_path):
    """A source path outside vault_root → PathTraversalError."""
    outside = tmp_path / "evil.md"
    outside.write_text("---\ntype: summary\ntitle: x\ndate: 2026-01-01\n---\n")
    item = SourceItem(
        kind="manual",
        source_path=outside,
        vault_root=minimal_vault,
        vault_id="minimal-test",
    )
    with pytest.raises(PathTraversalError):
        adapter.fetch(item)


def test_unit_01_extract_wiki_links():
    body = (
        "First line\n"
        "Mentions [[foo]] here.\n"
        "And [[bar|display]] there with alias.\n"
        "Blank line and [[baz]] [[qux]].\n"
    )
    links = extract_wiki_links(body)
    targets = [t for t, _, _ in links]
    assert targets == ["foo", "bar", "baz", "qux"]


def test_unit_02_compute_file_hash_deterministic():
    assert compute_file_hash("abc") == compute_file_hash("abc")
    assert compute_file_hash("abc") != compute_file_hash("abd")


def test_unit_02b_adapter_hashes_full_file_not_body(tmp_path):
    """Regression for adversarial HIGH issue: adapter must hash FULL file
    (frontmatter + body), not body-only. Otherwise frontmatter-only edits
    (added tag, fixed title) produce same hash → upsert_page short-circuits
    as 'unchanged' → DB never sees the edit."""
    from scripts.wiki_source.base import SourceItem
    from scripts.wiki_source.manual import ManualSourceAdapter

    vault = tmp_path / "v"
    (vault / "_sources").mkdir(parents=True)
    body = "lesson body text"
    src = vault / "_sources" / "x.md"

    src.write_text(f"---\ntype: summary\ntitle: A\n---\n{body}\n")
    item = SourceItem(kind="manual", source_path=src, vault_root=vault,
                      vault_id="v")
    out1 = ManualSourceAdapter().fetch(item)

    # Edit ONLY frontmatter (different tag), keep body identical
    src.write_text(f"---\ntype: summary\ntitle: B\n---\n{body}\n")
    out2 = ManualSourceAdapter().fetch(item)
    assert out1.file_hash != out2.file_hash, (
        "frontmatter-only edit produced same hash → upsert would silently drop it"
    )


def test_unit_03_derive_slug_vault_root(tmp_path):
    vault = tmp_path / "v"
    (vault / "_sources").mkdir(parents=True)
    p = vault / "_sources" / "alpha.md"
    p.touch()
    slug, project = derive_slug(p, vault)
    assert (slug, project) == ("alpha", "_vault_")


def test_unit_04_derive_slug_course_local(tmp_path):
    vault = tmp_path / "v"
    course_dir = vault / "Lessons" / "ZeroOne Systems"
    course_dir.mkdir(parents=True)
    p = course_dir / "lesson-01.md"
    p.touch()
    slug, project = derive_slug(p, vault)
    assert slug == "lesson-01"
    assert project == "zeroone-systems"


def test_unit_06_all_refs_trust_level_high(adapter, minimal_vault: Path):
    """R-15.3: every ref produced by manual adapter has trust_level='high'."""
    item = SourceItem(
        kind="manual",
        source_path=minimal_vault / "_sources" / "alpha.md",
        vault_root=minimal_vault,
        vault_id="minimal-test",
    )
    out = adapter.fetch(item)
    assert all(r.trust_level == "high" for r in out.refs)


def test_dedup_state_key_stable(adapter, minimal_vault: Path):
    item = SourceItem(
        kind="manual",
        source_path=minimal_vault / "_sources" / "alpha.md",
        vault_root=minimal_vault,
        vault_id="v",
    )
    k1 = adapter.dedup_state_key(item)
    k2 = adapter.dedup_state_key(item)
    assert k1 == k2
    assert len(k1) == 16
