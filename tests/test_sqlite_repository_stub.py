"""Stub tests for scripts/wiki_index/sqlite_repository.py (task-001-04).

Covers:
- TC-E2E-01: Instantiation succeeds, db_path stored, NO sqlite file opened.
- TC-UNIT-01: Every abstract method raises NotImplementedError with the
  implementing-task forward-pointer.

Phase 3a (Stub stage) — the harness uses controlled NotImplementedError as
the "Red" state of TDD; task-001-15..19 turn the lights green method by method.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from scripts.wiki_index.models import LogEvent, Page, PageRef, Vault
from scripts.wiki_index.sqlite_repository import SQLiteRepository


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def repo(tmp_path):
    """A stub repository pointing at a file that DOES NOT exist yet."""
    return SQLiteRepository(tmp_path / "test.db")


@pytest.fixture
def vault():
    return Vault(
        vault_id="trade-agents",
        name="Trade Agents",
        root_path=Path("/tmp/trade-agents"),
        schema_version="2.0",
        registered_at=datetime(2026, 5, 26, 14, 0, 0),
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
        date=None,
        last_modified=datetime(2026, 5, 25, 10, 0, 0),
        file_hash="abc123",
        frontmatter_json={"tags": ["agent"]},
        body_excerpt="body",
        tags=["agent"],
    )


@pytest.fixture
def page_ref():
    return PageRef(
        vault_id="trade-agents",
        page_slug="hermes-agent",
        page_project="_vault_",
        entity_slug="sharpe-score",
        ref_type="mentioned",
    )


@pytest.fixture
def log_event():
    return LogEvent(
        vault_id="trade-agents",
        event_ts=datetime(2026, 5, 26, 14, 30, 0),
        event_type="ingest",
        pages_created_json=[],
        pages_updated_json=[],
        details_json={},
    )


# =============================================================================
# TC-E2E-01 — instantiation succeeds, no DB opened
# =============================================================================


def test_e2e_01_instantiate_does_not_open_db(tmp_path):
    """Constructing the stub stores db_path but does not create the file."""
    db_path = tmp_path / "not-yet-created.db"
    assert not db_path.exists()
    repo = SQLiteRepository(db_path)
    assert repo.db_path == db_path
    # CRITICAL: the file must NOT have been opened/created by __init__.
    # Connection management is deferred to task-001-15.
    assert not db_path.exists(), (
        "SQLiteRepository.__init__ must NOT open the DB; connection deferred "
        "to task-001-15"
    )


def test_e2e_01b_subclasses_indexrepository(repo):
    """SQLiteRepository is a proper IndexRepository subclass."""
    from scripts.wiki_index.repository import IndexRepository

    assert isinstance(repo, IndexRepository)


# =============================================================================
# TC-UNIT-01 — every abstract method raises NotImplementedError with task ref
# =============================================================================


# (method_name, impl_task, args_kwargs)
# args_kwargs is a tuple of (positional_args, keyword_args).
# Built lazily per-test so fixtures can be resolved.
ABSTRACT_METHODS: list[tuple[str, str]] = [
    # vault registry — task-001-15 IMPLEMENTED, tests moved to test_vaults_crud.py
    # pages + refs — task-001-16 IMPLEMENTED, tests moved to test_pages_upsert.py
    # search — task-001-17 IMPLEMENTED, tests moved to test_search_pages.py
    # lint — task-001-18 IMPLEMENTED, tests moved to test_lint_queries.py
    # log_events + batch_runs — task-001-19 IMPLEMENTED, tests moved to test_log_events.py
]


def _call_with_dummy_args(repo, method_name, vault, page, page_ref, log_event):
    """Invoke a method with minimal args sufficient to reach the stub body."""
    method = getattr(repo, method_name)
    if method_name == "register_vault":
        return method(vault)
    if method_name in {"get_vault", "list_vaults"}:
        return method("trade-agents") if method_name == "get_vault" else method()
    if method_name == "rename_vault":
        return method("old", "new")
    if method_name == "upsert_page":
        return method(page)
    if method_name in {"get_page", "delete_page"}:
        return method("v", "s", "_vault_")
    if method_name == "upsert_refs":
        return method([page_ref])
    if method_name == "replace_refs":
        return method("v", "s", "_vault_", [page_ref])
    if method_name == "get_backlinks":
        return method("v", "e")
    if method_name == "search_pages":
        return method("query")
    if method_name == "find_orphan_links":
        return method()
    if method_name == "find_pages_missing_in_index":
        return method("v", Path("/tmp"))
    if method_name == "check_drift":
        return method("v")
    if method_name == "find_cross_vault_concept_duplicates":
        return method()
    if method_name == "append_log_event":
        return method(log_event)
    if method_name == "update_log_event_offset":
        return method(1, 1234)
    if method_name == "query_log_events":
        return method("v")
    if method_name == "begin_batch_run":
        return method("v", "full")
    if method_name == "finish_batch_run":
        return method(1, "success")
    if method_name == "last_batch_run":
        return method("v")
    raise AssertionError(f"no dispatch entry for {method_name!r}")


@pytest.mark.parametrize("method_name, impl_task", ABSTRACT_METHODS)
def test_unit_01_method_raises_notimplemented(
    repo, vault, page, page_ref, log_event, method_name, impl_task
):
    """Each stub method raises NotImplementedError mentioning its impl task."""
    with pytest.raises(NotImplementedError) as exc_info:
        _call_with_dummy_args(repo, method_name, vault, page, page_ref, log_event)
    msg = str(exc_info.value)
    assert method_name in msg, f"error message must reference method: {msg}"
    assert impl_task in msg, (
        f"error message must point to implementing task {impl_task}: {msg}"
    )


# =============================================================================
# resolve_entity — implemented in TASK 005 / R-4.5 (Epic 7 stub retired)
# =============================================================================


def test_resolve_entity_implemented_returns_none_on_miss(repo):
    """`resolve_entity` is implemented as of TASK 005 (R-4.5): it resolves a
    slug or alias to an Entity, or returns None on a miss — it no longer raises
    the Epic-7 NotImplementedError stub. Full behaviour is covered in
    tests/test_entity_resolution_dal.py::TestResolveEntity."""
    repo.apply_schema()
    repo.register_vault(Vault(
        vault_id="test-vault", name="v", root_path=repo.db_path.parent,
        schema_version="3.0", registered_at=datetime(2026, 5, 29),
    ))
    assert repo.resolve_entity("test-vault", "nope") is None


# =============================================================================
# Coverage sanity: every abstract method declared on IndexRepository is in our
# parametrized list (i.e., we don't silently miss a method).
# =============================================================================


def test_unit_01b_all_listed_methods_are_abstract_on_parent():
    """Sanity-check: every entry in ABSTRACT_METHODS is still @abstractmethod
    on the parent ABC (no spurious or stale entries). As Stage 2 implements
    methods, they are removed from ABSTRACT_METHODS but stay @abstractmethod
    on the parent — this test ensures the list doesn't lie about coverage."""
    from scripts.wiki_index.repository import IndexRepository

    inherited_abstracts = {
        name
        for name in dir(IndexRepository)
        if getattr(getattr(IndexRepository, name), "__isabstractmethod__", False)
    }
    listed = {name for name, _ in ABSTRACT_METHODS}
    spurious_in_list = listed - inherited_abstracts
    assert not spurious_in_list, (
        f"ABSTRACT_METHODS has entries not declared abstract on parent: "
        f"{sorted(spurious_in_list)}"
    )
