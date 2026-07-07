"""TASK 050 (R-3/R-4) — opt-in read logging: `wiki-query prepare
--log-retrieval` + `wiki-search --log-access`. Default OFF ⇒ zero writes;
best-effort (a failed insert reports access_logged: false, never a crash).
"""

from __future__ import annotations

import contextlib
import io
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from scripts.wiki_index.models import Vault
from scripts.wiki_index.reindex import reindex_full
from scripts.wiki_index.sqlite_repository import SQLiteRepository
from scripts.wiki_skills import wiki_query, wiki_search

VID = "readlog-vault"


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
    _write(vault, "_sources/note-a.md",
           "type: summary\ntitle: A\ndate: 2026-07-07\ntags: [t]",
           "Hermes readlog demo body.")
    db = tmp_path / "g.db"
    repo = SQLiteRepository(db)
    repo.apply_schema()
    repo.register_vault(Vault(
        vault_id=VID, name=VID, root_path=vault,
        schema_version="7.0", registered_at=datetime(2026, 7, 7)))
    reindex_full(repo, VID)
    repo.close()
    return vault, db


def _events(db: Path) -> list[dict]:
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT vault_id, event_type, subject, details_json "
        "FROM log_events WHERE event_type = 'query' ORDER BY id").fetchall()
    conn.close()
    return [{"vault": r["vault_id"], "type": r["event_type"],
             "subject": r["subject"],
             "details": json.loads(r["details_json"] or "{}")} for r in rows]


def _search(vault, db, *argv) -> tuple[int, dict]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = wiki_search.main(
            ["hermes", "--vault-root", str(vault), "--db-path", str(db), *argv])
    return code, json.loads(buf.getvalue())


# =============================================================================
# R-3 — wiki-query prepare --log-retrieval
# =============================================================================

def test_log_retrieval_on_off(tmp_path, monkeypatch):
    monkeypatch.setenv("WIKI_ACTOR_ID", "reader-1")
    vault, db = _seed(tmp_path)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = wiki_query.main(
            ["prepare", "hermes readlog", "--vault", VID, "--vault-root",
             str(vault), "--db-path", str(db)])
    env = json.loads(buf.getvalue())
    assert code == 0 and "access_logged" not in env       # OFF: no key, no event
    assert _events(db) == []
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = wiki_query.main(
            ["prepare", "hermes readlog", "--vault", VID, "--vault-root",
             str(vault), "--db-path", str(db), "--log-retrieval"])
    env = json.loads(buf.getvalue())
    assert code == 0 and env["access_logged"] is True
    evs = _events(db)
    assert len(evs) == 1
    assert evs[0]["details"]["access"] is True
    assert evs[0]["details"]["retrieved"] == ["_vault_/note-a"]
    assert evs[0]["details"]["actor"] == "reader-1"


def test_log_retrieval_failure_never_fails_prepare(tmp_path, monkeypatch):
    monkeypatch.delenv("WIKI_ACTOR_ID", raising=False)
    vault, db = _seed(tmp_path)
    # Simulate an insert failure: drop the vault row (FK ON → IntegrityError).
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("DELETE FROM vaults WHERE vault_id = ?", (VID,))
    conn.commit()
    conn.close()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = wiki_query.main(
            ["prepare", "hermes readlog", "--vault", VID, "--vault-root",
             str(vault), "--db-path", str(db), "--log-retrieval"])
    env = json.loads(buf.getvalue())
    assert code == 0                                       # read path unharmed
    assert env["access_logged"] is False


# =============================================================================
# R-4 — wiki-search --log-access
# =============================================================================

def test_log_access_actor_threaded(tmp_path, monkeypatch):
    """reviewer LOW-2: the search audit event carries details.actor."""
    monkeypatch.setenv("WIKI_ACTOR_ID", "searcher-1")
    vault, db = _seed(tmp_path)
    code, env = _search(vault, db, "--vaults", VID, "--log-access")
    assert code == 0 and env["access_logged"] is True
    assert _events(db)[0]["details"]["actor"] == "searcher-1"


def test_log_access_single_vault(tmp_path, monkeypatch):
    monkeypatch.delenv("WIKI_ACTOR_ID", raising=False)
    vault, db = _seed(tmp_path)
    code, env = _search(vault, db, "--vaults", VID)
    assert code == 0 and "access_logged" not in env        # OFF
    assert _events(db) == []
    code, env = _search(vault, db, "--vaults", VID, "--log-access")
    assert code == 0 and env["access_logged"] is True
    evs = _events(db)
    assert len(evs) == 1
    assert evs[0]["vault"] == VID and evs[0]["subject"] == "search"
    assert evs[0]["details"]["hits"] == [f"{VID}:_vault_/note-a"]


def test_log_access_multi_named_goes_global(tmp_path):
    """plan-review MED-1: `--vaults a,b` logs to `_global_`, never to `a`."""
    vault, db = _seed(tmp_path)
    code, env = _search(vault, db, "--vaults", f"{VID},other-x", "--log-access")
    assert code == 0
    evs = _events(db)
    # `_global_` row exists only when wiki-init seeded it; in this fixture it
    # does NOT — so the insert fail-softs. Either way: never attributed to VID.
    if env["access_logged"]:
        assert evs and evs[0]["vault"] == "_global_"
    else:
        assert evs == []


def test_log_access_caps_and_strips_query(tmp_path):
    vault, db = _seed(tmp_path)
    hostile = "\x1b[31mhermes\x07" + "x" * 500
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = wiki_search.main(
            [hostile, "--vaults", VID, "--vault-root", str(vault),
             "--db-path", str(db), "--log-access"])
    assert code == 0
    evs = _events(db)
    q = evs[0]["details"]["q"]
    assert "\x1b" not in q and "\x07" not in q             # CWE-117 strip
    assert len(q) <= 200                                    # cap
