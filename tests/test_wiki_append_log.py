"""Tests for wiki-append-log + bi-directional sync (task-001-27, M-2)."""

from __future__ import annotations

import io
import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

from scripts.wiki_index.logfile import (
    append_atomic,
    parse_log_md,
    render_event_line,
    rotate_log_path,
)
from scripts.wiki_index.models import LogEvent, Vault
from scripts.wiki_index.sqlite_repository import SQLiteRepository
from scripts.wiki_skills.wiki_append_log import main


@pytest.fixture
def repo(tmp_path):
    r = SQLiteRepository(tmp_path / "db.db")
    r.apply_schema()
    vault_root = tmp_path / "v"
    vault_root.mkdir()
    r.register_vault(Vault(
        vault_id="test-vault", name="t", root_path=vault_root,
        schema_version="2.0", registered_at=datetime(2026, 5, 26),
    ))
    yield r, vault_root
    r.close()


def _run(argv: list[str]) -> tuple[int, dict]:
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        code = main(argv)
    finally:
        sys.stdout = old
    return code, json.loads(buf.getvalue())


def test_e2e_01_round_trip(repo):
    r, vault_root = repo
    code, out = _run([
        "--vault", "test-vault", "--event-type", "ingest",
        "--subject", "Alpha", "--db-path", str(r.db_path),
    ])
    assert code == 0
    assert out["action"] == "logged"
    log_path = vault_root / "00-Vault-Index" / "log" / f"{datetime.now().strftime('%Y-%m')}.md"
    assert log_path.exists()
    # Byte offset points to start of line — re-read from that offset
    with open(log_path, "rb") as f:
        f.seek(out["byte_offset"])
        chunk = f.read()
    assert chunk.startswith(b"## [")
    # DB has matching offset
    events = r.query_log_events("test-vault")
    assert len(events) == 1
    assert events[0].log_md_byte_offset == out["byte_offset"]


def test_unit_01_render_event_line_format():
    e = LogEvent(
        vault_id="v", event_ts=datetime(2026, 5, 26, 14, 55, 0),
        event_type="ingest", subject="Test", pages_created_json=["a", "b"],
        pages_updated_json=["c"], details_json={},
    )
    line = render_event_line(e)
    assert line.startswith("## [2026-05-26 14:55:00] ingest | Test")
    assert "pages_created" in line


def test_unit_02_append_atomic_returns_offset(tmp_path):
    path = tmp_path / "log.md"
    o1 = append_atomic(path, "first line\n")
    o2 = append_atomic(path, "second line\n")
    assert o1 == 0
    assert o2 == len("first line\n")


def test_unit_03_parse_log_md_round_trip(repo):
    r, vault_root = repo
    for i in range(3):
        _run(["--vault", "test-vault", "--event-type", "ingest",
              "--subject", f"S{i}", "--db-path", str(r.db_path)])
    log_path = rotate_log_path(vault_root, datetime.now())
    parsed = parse_log_md(log_path)
    assert len(parsed) == 3
    assert [p[2] for p in parsed] == ["S0", "S1", "S2"]


def test_rotate_log_path_creates_dir(tmp_path):
    vault = tmp_path / "v"
    p = rotate_log_path(vault, datetime(2026, 5, 26))
    assert p.parent.is_dir()
    assert p.name == "2026-05.md"
