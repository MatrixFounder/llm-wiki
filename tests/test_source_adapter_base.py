"""Smoke tests for scripts/wiki_source/base.py (task-001-06)."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from scripts.wiki_source.base import SourceAdapter, SourceItem, SourceOutput


def test_e2e_01_source_adapter_is_abstract():
    """SourceAdapter cannot be instantiated directly (Python ABC)."""
    with pytest.raises(TypeError, match=r"abstract"):
        SourceAdapter()  # type: ignore[abstract]


def test_source_item_frozen():
    """SourceItem is frozen."""
    item = SourceItem(
        kind="manual",
        source_path=Path("/tmp/a.md"),
        vault_root=Path("/tmp"),
        vault_id="trade-agents",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        item.kind = "transcript"  # type: ignore[misc]


def test_source_item_default_extra():
    """SourceItem.extra defaults to {} via dataclasses.field(default_factory=dict)."""
    item = SourceItem(
        kind="manual",
        source_path=Path("/tmp/a.md"),
        vault_root=Path("/tmp"),
        vault_id="v",
    )
    assert item.extra == {}


def test_source_output_frozen():
    """SourceOutput is frozen."""
    out = SourceOutput(
        page_slug="foo",
        project="_vault_",
        output_path=Path("/tmp/a.md"),
        file_hash="abc",
        trust_level="high",
        frontmatter={},
        body_text="",
        refs=[],
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        out.page_slug = "bar"  # type: ignore[misc]


def test_incomplete_subclass_cannot_instantiate():
    """A subclass missing required abstracts cannot be instantiated."""

    class IncompleteAdapter(SourceAdapter):
        def authenticate(self, config):  # type: ignore[override]
            pass

    with pytest.raises(TypeError, match=r"abstract"):
        IncompleteAdapter()  # type: ignore[abstract]
