"""Tests for log_events + batch_runs CRUD (task-001-19)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from scripts.wiki_index.models import LogEvent, Vault
from scripts.wiki_index.sqlite_repository import SQLiteRepository


@pytest.fixture
def repo(tmp_path):
    r = SQLiteRepository(tmp_path / "t.db")
    r.apply_schema()
    r.register_vault(Vault(
        vault_id="trade-agents", name="t", root_path=tmp_path,
        schema_version="2.0", registered_at=datetime(2026, 5, 26),
    ))
    yield r
    r.close()


def _event(ts: datetime, etype: str = "ingest", subject: str = "src") -> LogEvent:
    return LogEvent(
        vault_id="trade-agents",
        event_ts=ts,
        event_type=etype,
        subject=subject,
        pages_created_json=["a", "b"],
        pages_updated_json=["c"],
        details_json={"k": "v"},
    )


def test_e2e_01_append_then_query(repo):
    eid = repo.append_log_event(_event(datetime(2026, 5, 26, 10)))
    assert eid > 0
    events = repo.query_log_events("trade-agents")
    assert len(events) == 1
    assert events[0].subject == "src"
    assert events[0].pages_created_json == ["a", "b"]


def test_e2e_02_query_since_filter(repo):
    repo.append_log_event(_event(datetime(2026, 5, 25, 10), subject="early"))
    repo.append_log_event(_event(datetime(2026, 5, 27, 10), subject="late"))
    events = repo.query_log_events("trade-agents", since=datetime(2026, 5, 26))
    assert [e.subject for e in events] == ["late"]


def test_e2e_03_batch_run_lifecycle(repo):
    rid = repo.begin_batch_run("trade-agents", "full")
    assert rid > 0
    repo.finish_batch_run(rid, "success", notes="ok")
    last = repo.last_batch_run("trade-agents")
    assert last is not None
    assert last.id == rid
    assert last.status == "success"
    assert last.notes == "ok"
    assert last.finished_at is not None


def test_unit_01_json_round_trip(repo):
    repo.append_log_event(_event(datetime(2026, 5, 26, 10)))
    events = repo.query_log_events("trade-agents")
    assert events[0].pages_created_json == ["a", "b"]
    assert events[0].details_json == {"k": "v"}


def test_unit_02_event_type_check_constraint(repo):
    with pytest.raises(sqlite3.IntegrityError):
        repo.append_log_event(_event(datetime(2026, 5, 26), etype="bogus-type"))


def test_unit_03_fk_violation_on_unknown_vault(repo):
    bad = LogEvent(
        vault_id="ghost-vault",
        event_ts=datetime(2026, 5, 26),
        event_type="ingest",
        pages_created_json=[], pages_updated_json=[], details_json={},
    )
    with pytest.raises(sqlite3.IntegrityError):
        repo.append_log_event(bad)


def test_unit_04_event_types_filter(repo):
    repo.append_log_event(_event(datetime(2026, 5, 26, 10), etype="ingest"))
    repo.append_log_event(_event(datetime(2026, 5, 26, 11), etype="lint"))
    repo.append_log_event(_event(datetime(2026, 5, 26, 12), etype="reindex"))
    events = repo.query_log_events("trade-agents", event_types=["ingest", "reindex"])
    assert {e.event_type for e in events} == {"ingest", "reindex"}


def test_unit_05_last_batch_run_none_when_empty(repo):
    assert repo.last_batch_run("trade-agents") is None


def test_update_log_event_offset(repo):
    eid = repo.append_log_event(_event(datetime(2026, 5, 26, 10)))
    repo.update_log_event_offset(eid, 4827)
    events = repo.query_log_events("trade-agents")
    assert events[0].log_md_byte_offset == 4827
