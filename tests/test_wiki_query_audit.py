"""TASK 050 (R-1/R-2/R-6b) — the read-side audit spine.

`wiki-query apply` logs on EVERY success (cited slugs + action + audience? +
actor?); `actor_id()` env identity; Class-C DB-only audit rows survive
`wiki-reindex --full`.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

from scripts.wiki_index.models import LogEvent, Vault
from scripts.wiki_index.reindex import reindex_full
from scripts.wiki_index.sqlite_repository import SQLiteRepository
from scripts.wiki_skills import wiki_query
from scripts.wiki_skills._common import actor_id

VID = "audit-vault"


# =============================================================================
# 050-01 — actor_id()
# =============================================================================

@pytest.mark.parametrize("val,expected", [
    ("critic-security", "critic-security"),
    ("user.a:b@c_x", "user.a:b@c_x"),            # underscore IS in the shape
    ("user.a:b@c-x", "user.a:b@c-x"),
    ("UPPER", None),
    ("x" * 65, None),
    ("", None),
])
def test_actor_id_shape_matrix(monkeypatch, val, expected):
    monkeypatch.setenv("WIKI_ACTOR_ID", val)
    assert actor_id() == expected


def test_actor_id_unset(monkeypatch):
    monkeypatch.delenv("WIKI_ACTOR_ID", raising=False)
    assert actor_id() is None


# =============================================================================
# 050-02 — apply audit completeness (e2e)
# =============================================================================

def _write(vault: Path, rel: str, fm: str, body: str) -> None:
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\n{fm}\n---\n\n{body}\n", encoding="utf-8")


def _seed(tmp_path: Path) -> tuple[Path, Path]:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "WIKI_SCHEMA.md").write_text(
        f"---\nname: WIKI_SCHEMA\nvault_id: {VID}\n"
        "schema_version: '2.0'\nlanguage: en\nlayout: karpathy\n---\n\n# s\n")
    _write(vault, "_sources/src-note.md",
           "type: summary\ntitle: Src\ndate: 2026-07-07\ntags: [t]",
           "Hermes audit demo body.")
    db = tmp_path / "g.db"
    repo = SQLiteRepository(db)
    repo.apply_schema()
    repo.register_vault(Vault(
        vault_id=VID, name=VID, root_path=vault,
        schema_version="7.0", registered_at=datetime(2026, 7, 7)))
    reindex_full(repo, VID)
    repo.close()
    return vault, db


def _run(vault: Path, db: Path, argv: list[str], stdin: str | None = None) -> tuple[int, dict]:
    buf = io.StringIO()
    if stdin is not None:
        old = sys.stdin
        sys.stdin = io.TextIOWrapper(io.BytesIO(stdin.encode()), encoding="utf-8")
    try:
        with contextlib.redirect_stdout(buf):
            code = wiki_query.main(argv + ["--vault", VID, "--vault-root",
                                           str(vault), "--db-path", str(db)])
    finally:
        if stdin is not None:
            sys.stdin = old
    return code, json.loads(buf.getvalue())


def _apply_once(vault: Path, db: Path) -> tuple[int, dict]:
    code, env = _run(vault, db, ["prepare", "hermes audit demo"])
    assert code == 0
    (vault / "c.json").write_text(json.dumps([f"_vault_/src-note"]))
    return _run(vault, db, [
        "apply", "--query-slug", env["query_slug"],
        "--question", "hermes audit demo",
        "--question-hash", env["question_hash"],
        "--answer-stdin", "--citations-file", str(vault / "c.json")],
        stdin="Answer citing the source.")


def _events(db: Path) -> list[dict]:
    import sqlite3
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT event_type, subject, details_json, log_md_byte_offset "
        "FROM log_events WHERE vault_id = ? ORDER BY id", (VID,)).fetchall()
    conn.close()
    return [{"type": r["event_type"], "subject": r["subject"],
             "details": json.loads(r["details_json"] or "{}"),
             "offset": r["log_md_byte_offset"]} for r in rows]


def test_apply_logs_filed_and_unchanged(tmp_path, monkeypatch):
    monkeypatch.delenv("WIKI_ACTOR_ID", raising=False)
    vault, db = _seed(tmp_path)
    code, out = _apply_once(vault, db)
    assert code == 0 and out["action"] == "filed"
    code, out = _apply_once(vault, db)
    assert code == 0 and out["action"] == "unchanged"
    evs = [e for e in _events(db) if e["type"] == "query"]
    assert len(evs) == 2                                  # NFR-1: delta ≡ D1 events
    assert evs[0]["details"]["action"] == "filed"
    assert evs[1]["details"]["action"] == "unchanged"
    for e in evs:
        assert e["details"]["cited"] == ["_vault_/src-note"]
        assert e["details"]["cites"] == 1                 # back-compat count
        assert "actor" not in e["details"]
        assert "audience" not in e["details"]
        assert e["offset"] is None                        # Class-C DB-only
    assert not (vault / "log.md").exists()                # no log.md spam


def test_apply_logs_actor_and_audience(tmp_path, monkeypatch):
    monkeypatch.setenv("WIKI_ACTOR_ID", "auditor-1")
    vault, db = _seed(tmp_path)
    # activate a policy profile via the vault block
    schema = vault / "WIKI_SCHEMA.md"
    schema.write_text(schema.read_text().replace(
        "layout: karpathy\n",
        "layout: karpathy\npolicy:\n  levels: [public, internal]\n"
        "  default_audience: internal\n"))
    code, out = _apply_once(vault, db)
    assert code == 0
    ev = [e for e in _events(db) if e["type"] == "query"][-1]
    assert ev["details"]["actor"] == "auditor-1"
    assert ev["details"]["audience"] == "internal"


# =============================================================================
# 050-04 — Class-C audit rows survive reindex --full (R-6b)
# =============================================================================

def test_db_only_audit_rows_survive_full_rebuild(tmp_path):
    vault, db = _seed(tmp_path)
    repo = SQLiteRepository(db)
    # a DB-only audit row (offset NULL) + a mirrored row (offset set)
    repo.append_log_event(LogEvent(
        vault_id=VID, event_ts=datetime(2026, 7, 7), event_type="query",
        subject="audit-probe", pages_created_json=[], pages_updated_json=[],
        details_json={"access": True}))
    from scripts.wiki_index.logfile import (
        append_atomic, render_event_line, rotate_log_path)
    mirrored = LogEvent(
        vault_id=VID, event_ts=datetime(2026, 7, 7, 10), event_type="ingest",
        subject="mirrored-probe", pages_created_json=[], pages_updated_json=[],
        details_json={})
    log_md = rotate_log_path(vault, datetime(2026, 7, 7, 10))
    offset = append_atomic(log_md, render_event_line(mirrored))
    mid = repo.append_log_event(mirrored)
    repo.update_log_event_offset(mid, offset)
    reindex_full(repo, VID)
    try:
        subjects = {(e["subject"], e["offset"] is None) for e in _events(db)}
        assert ("audit-probe", True) in subjects          # Class-C survived
        # mirrored row wiped + re-parsed from log.md exactly once (no dupes)
        mirrored = [e for e in _events(db) if e["subject"] == "mirrored-probe"]
        assert len(mirrored) == 1
    finally:
        repo.close()


# =============================================================================
# vdd-multi review fixes
# =============================================================================

def test_read_events_do_not_advance_delta_cutoff(tmp_path, monkeypatch):
    """logic-MED: a --log-retrieval/--log-access telemetry event (or an
    unchanged-apply trail) must NOT advance the --delta cutoff — a file edit
    just before the read-log must still be ingested."""
    from datetime import timedelta
    from scripts.wiki_index.reindex import reindex_delta
    monkeypatch.delenv("WIKI_ACTOR_ID", raising=False)
    vault, db = _seed(tmp_path)
    # Edit the source file NOW (mtime = now, after the seed reindex event).
    src = vault / "_sources" / "src-note.md"
    src.write_text(src.read_text().replace("demo body", "demo body EDITED"))
    # Telemetry with a FUTURE event_ts — deterministically after the edit.
    repo = SQLiteRepository(db)
    repo.append_log_event(LogEvent(
        vault_id=VID, event_ts=datetime.now() + timedelta(hours=1),
        event_type="query", subject="telemetry-probe",
        pages_created_json=[], pages_updated_json=[],
        details_json={"access": True, "retrieved": []}))
    try:
        result = reindex_delta(repo, VID)
        assert result["touched"] >= 1, (
            "read-telemetry advanced the delta cutoff and masked a file edit")
        page = repo.get_page(VID, "src-note", "_vault_")
        assert "EDITED" in (page.body_excerpt or "")
    finally:
        repo.close()


def test_actor_threaded_into_verify_appendlog_ingest(tmp_path, monkeypatch):
    """reviewer MED-1: the three other knowledge-write event writers carry
    details.actor when WIKI_ACTOR_ID is set (and omit it when unset)."""
    import sqlite3 as _sq
    from scripts.wiki_skills import wiki_append_log
    monkeypatch.setenv("WIKI_ACTOR_ID", "writer-x")
    vault, db = _seed(tmp_path)
    # wiki-append-log (mirrored event)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = wiki_append_log.main(
            ["--vault", VID, "--event-type", "ingest", "--subject", "probe",
             "--vault-root", str(vault), "--db-path", str(db)])
    assert code == 0
    conn = _sq.connect(db)
    conn.row_factory = _sq.Row
    row = conn.execute(
        "SELECT details_json FROM log_events WHERE subject='probe'").fetchone()
    conn.close()
    assert json.loads(row["details_json"])["actor"] == "writer-x"
    # _manifest_consumer ingest event
    from scripts.wiki_skills._manifest_consumer import index_from_manifest
    manifest = {
        "vault_id": VID, "created": [], "touched": [], "written": [],
        "log_event": {"event_type": "ingest", "subject": "manifest-probe"},
        "source": {"slug": "s", "hash": "h"},
    }
    repo = SQLiteRepository(db)
    try:
        index_from_manifest(manifest, vault_id=VID, vault_root=vault, repo=repo)
    finally:
        repo.close()
    conn = _sq.connect(db)
    conn.row_factory = _sq.Row
    row = conn.execute(
        "SELECT details_json FROM log_events "
        "WHERE subject='manifest-probe'").fetchone()
    conn.close()
    assert json.loads(row["details_json"])["actor"] == "writer-x"
