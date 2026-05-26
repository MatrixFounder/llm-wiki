"""Smoke tests for scripts/wiki_index/models.py + repository.py (task-001-03).

Covers:
- TC-E2E-01: cannot instantiate IndexRepository directly (ABC enforcement)
- TC-UNIT-01: all dataclasses are frozen
- (TC-UNIT-02 mypy --strict is a separate CI check, not a pytest test —
  invoking mypy from pytest adds a heavy dependency for marginal benefit.
  The acceptance criterion is verified by running `mypy --strict
  scripts/wiki_index/` from the developer terminal.)
"""

from __future__ import annotations

import dataclasses
from datetime import date, datetime
from pathlib import Path

import pytest

from scripts.wiki_index.models import (
    BatchRun,
    DriftReport,
    Entity,
    LogEvent,
    OrphanLink,
    Page,
    PageHit,
    PageRef,
    Vault,
)
from scripts.wiki_index.repository import IndexRepository


# =============================================================================
# Fixtures — minimal valid instances of every model
# =============================================================================


@pytest.fixture
def vault():
    return Vault(
        vault_id="trade-agents",
        name="Trade Agents",
        root_path=Path("/tmp/trade-agents"),
        schema_version="2.0",
        registered_at=datetime(2026, 5, 26, 14, 0, 0),
        config_json={"layout": "per-project"},
        notes=None,
    )


@pytest.fixture
def page():
    return Page(
        vault_id="trade-agents",
        slug="hermes-agent",
        project="_vault_",
        type="concept",
        title="Hermes Agent",
        file_path="_concepts/hermes-agent.md",
        date=date(2026, 5, 25),
        last_modified=datetime(2026, 5, 25, 10, 0, 0),
        file_hash="abc123",
        frontmatter_json={"tags": ["agent", "trading"]},
        body_excerpt="Hermes Agent is a self-learning autonomous trading framework.",
        tags=["agent", "trading"],
        tldr="Self-learning",
        is_frozen=False,
    )


@pytest.fixture
def entity():
    return Entity(
        vault_id="trade-agents",
        slug="hermes-agent",
        type="concept",
        name="Hermes Agent",
        aliases=["Hermes"],
        description="Self-learning trading framework",
        is_external=False,
    )


@pytest.fixture
def page_ref():
    return PageRef(
        vault_id="trade-agents",
        page_slug="hermes-agent",
        page_project="_vault_",
        entity_slug="sharpe-score",
        ref_type="mentioned",
        trust_level="medium",
        line_start=10,
        line_end=10,
        source_quote="mentions Sharpe Score as a key metric",
    )


@pytest.fixture
def log_event():
    return LogEvent(
        vault_id="trade-agents",
        event_ts=datetime(2026, 5, 26, 14, 30, 0),
        event_type="ingest",
        pages_created_json=["foo"],
        pages_updated_json=["bar"],
        details_json={"key": "value"},
        subject="Test Source",
    )


@pytest.fixture
def orphan_link():
    return OrphanLink(
        vault_id="trade-agents",
        source_page_slug="hermes-agent",
        source_page_project="_vault_",
        target_slug="non-existent-concept",
    )


@pytest.fixture
def batch_run():
    return BatchRun(
        vault_id="trade-agents",
        mode="full",
        started_at=datetime(2026, 5, 26, 12, 0, 0),
    )


@pytest.fixture
def drift_report():
    return DriftReport(
        missing_in_db=[Path("_concepts/foo.md")],
        missing_on_disk=[("bar", "_vault_")],
        hash_mismatch=[("baz", "_vault_")],
        type_mismatch=[("qux", "_vault_", "lecture-notes", "summary")],
    )


# =============================================================================
# TC-E2E-01 — IndexRepository is abstract, cannot be instantiated directly
# =============================================================================


def test_e2e_01_repository_is_abstract():
    """Direct instantiation of IndexRepository raises TypeError (Python ABC)."""
    with pytest.raises(TypeError, match=r"abstract"):
        IndexRepository()  # type: ignore[abstract]


def test_e2e_01b_minimal_subclass_must_override_all_abstracts():
    """A subclass missing required abstracts cannot be instantiated either."""

    class IncompleteRepo(IndexRepository):
        # Intentionally implements only one method — others stay abstract.
        def get_vault(self, vault_id: str):  # type: ignore[override]
            return None

    with pytest.raises(TypeError, match=r"abstract"):
        IncompleteRepo()  # type: ignore[abstract]


# =============================================================================
# TC-UNIT-01 — all dataclasses are frozen
# =============================================================================


@pytest.mark.parametrize(
    "fixture_name, attr, new_value",
    [
        ("vault", "vault_id", "different"),
        ("page", "slug", "different"),
        ("entity", "name", "different"),
        ("page_ref", "trust_level", "high"),
        ("log_event", "event_type", "lint"),
        ("orphan_link", "target_slug", "different"),
        ("batch_run", "mode", "delta"),
        ("drift_report", "missing_in_db", []),
    ],
)
def test_unit_01_dataclass_is_frozen(request, fixture_name, attr, new_value):
    """Assigning to any attribute on a frozen dataclass raises FrozenInstanceError."""
    instance = request.getfixturevalue(fixture_name)
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(instance, attr, new_value)


# =============================================================================
# Construction sanity — every model accepts its documented args
# =============================================================================


def test_vault_construction(vault):
    assert vault.vault_id == "trade-agents"
    assert vault.root_path == Path("/tmp/trade-agents")


def test_page_construction_with_optional_fields(page):
    assert page.type == "concept"
    assert page.is_frozen is False
    assert page.tldr == "Self-learning"


def test_page_minimal_construction():
    """Page accepts only the required fields (no defaults missing)."""
    p = Page(
        vault_id="v",
        slug="s",
        project="_vault_",
        type="summary",
        title="t",
        file_path="_sources/s.md",
        date=None,
        last_modified=datetime(2026, 1, 1),
        file_hash="h",
        frontmatter_json={},
        body_excerpt="",
        tags=[],
    )
    assert p.tldr is None
    assert p.is_frozen is False


def test_page_hit_wraps_page(page):
    hit = PageHit(page=page, bm25_score=4.21, snippet="<b>Hermes</b>")
    assert hit.page.slug == "hermes-agent"
    assert hit.bm25_score == 4.21


def test_entity_with_empty_aliases():
    e = Entity(vault_id="v", slug="s", type="concept", name="S", aliases=[])
    assert e.aliases == []
    assert e.is_external is False


def test_page_ref_default_trust_level():
    """trust_level defaults to 'medium' per R-15.3."""
    r = PageRef(
        vault_id="v",
        page_slug="p",
        page_project="_vault_",
        entity_slug="e",
        ref_type="mentioned",
    )
    assert r.trust_level == "medium"


def test_log_event_pre_insert_has_no_id(log_event):
    """A LogEvent constructed for INSERT has id=None and byte_offset=None."""
    assert log_event.id is None
    assert log_event.log_md_byte_offset is None


def test_drift_report_construction(drift_report):
    assert drift_report.missing_in_db == [Path("_concepts/foo.md")]
    assert drift_report.type_mismatch[0] == ("qux", "_vault_", "lecture-notes", "summary")
