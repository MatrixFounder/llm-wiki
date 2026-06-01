"""TASK 012-05 (PW-N) — per-glob default_tags / extra_tags injection."""

from __future__ import annotations

from pathlib import Path

from scripts.wiki_index.layout_config import LayoutConfig, PathEntry, iter_pages
from scripts.wiki_index.normalization import normalize_frontmatter


def test_iter_pages_surfaces_matched_entry_tags(tmp_path: Path) -> None:
    (tmp_path / "_inbox").mkdir()
    (tmp_path / "_inbox" / "draft.md").write_text("x", encoding="utf-8")
    (tmp_path / "top.md").write_text("x", encoding="utf-8")
    cfg = LayoutConfig(
        schema_version="2.0", layout="t", slug_strategy="identity",
        paths=(
            PathEntry(glob="_inbox/**/*.md", project="_inbox",
                      default_tags=("inbox", "draft"), extra_tags=("note",)),
            PathEntry(glob="*.md", project="_root_"),
        ),
        type_mapping={"note": ("summary", None)},
    )
    by_slug = {d.slug: d.extra_tags for d in iter_pages(tmp_path, cfg)}
    assert by_slug["draft"] == ("inbox", "draft", "note")  # default_tags + extra_tags
    assert by_slug["top"] == ()                            # no tags on the *.md entry


def test_normalize_merges_extra_tags_dedup() -> None:
    fm, _db = normalize_frontmatter(
        {"type": "summary", "title": "X", "tags": ["inbox"]},
        extra_tags=("inbox", "draft", "moc"),
    )
    # existing 'inbox' kept once; new tags appended in order, deduped.
    assert fm["tags"] == ["inbox", "draft", "moc"]


def test_karpathy_extra_tags_empty_is_byte_identical() -> None:
    """No extra_tags (karpathy default) → tags unchanged from the marker/concept path."""
    fm, _db = normalize_frontmatter({"type": "external", "title": "Y"})
    assert fm["tags"] == ["external"]  # only the type-marker, no injected tags
