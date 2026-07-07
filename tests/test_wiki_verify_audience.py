"""TASK 049 (R-5) — `wiki-verify-multi --audience`: least-privilege critics.

An out-of-tier cited source is excluded from the examined set (its body never
read), counted in `restricted_count` (never named), symmetric across
prepare/apply; the field is absent under OFF (NFR-1).
"""

from __future__ import annotations

import contextlib
import io
import json
from datetime import datetime
from pathlib import Path

from scripts.wiki_index.models import Vault
from scripts.wiki_index.reindex import reindex_full
from scripts.wiki_index.sqlite_repository import SQLiteRepository
from scripts.wiki_skills import wiki_verify_multi

VID = "audv-vault"


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
    _write(vault, "_sources/pub-src.md",
           "type: summary\ntitle: Pub Src\ndate: 2026-07-01\ntags: [t]",
           "Public source body about hermes.")
    _write(vault, "_sources/sec-src.md",
           "type: summary\ntitle: Sec Src\ndate: 2026-07-01\ntags: [t]\n"
           "classification: restricted",
           "SECRET-MARKER body about hermes.")
    _write(vault, "_queries/audit-q.md",
           "type: query\nquestion: what is hermes\ndate: 2026-07-01\n"
           "cites: ['_vault_/pub-src', '_vault_/sec-src']\ntags: [query]",
           "Answer citing both sources.")
    db = tmp_path / "g.db"
    repo = SQLiteRepository(db)
    repo.apply_schema()
    repo.register_vault(Vault(
        vault_id=VID, name="v", root_path=vault,
        schema_version="7.0", registered_at=datetime(2026, 7, 1)))
    reindex_full(repo, VID)
    repo.close()
    return vault, db


def _prepare(vault: Path, db: Path, *extra: str) -> tuple[int, dict]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = wiki_verify_multi.main(
            ["prepare", "audit-q", "--vault", VID,
             "--vault-root", str(vault), "--db-path", str(db), *extra])
    return code, json.loads(buf.getvalue())


def test_off_examines_both_no_restricted_key(tmp_path):
    vault, db = _seed(tmp_path)
    code, env = _prepare(vault, db)
    assert code == 0
    assert env["examined_count"] == 2
    assert "restricted_count" not in env       # NFR-1: OFF envelope unchanged
    assert "audience" not in env


def test_audience_excludes_restricted_source_count_only(tmp_path):
    vault, db = _seed(tmp_path)
    code, env = _prepare(vault, db, "--audience", "internal")
    assert code == 0
    assert env["examined_count"] == 1
    assert env["examined"][0]["slug"] == "pub-src"
    assert env["restricted_count"] == 1
    assert env["audience"] == "internal"
    # The excluded source is never NAMED anywhere and its body never leaks.
    dumped = json.dumps(env)
    assert "sec-src" not in dumped
    assert "SECRET-MARKER" not in dumped
    assert "sec-src" not in env["missing_cites"]


def test_verify_hash_differs_between_scopes_but_stable_within(tmp_path):
    vault, db = _seed(tmp_path)
    _, off1 = _prepare(vault, db)
    _, off2 = _prepare(vault, db)
    _, low = _prepare(vault, db, "--audience", "internal")
    assert off1["verify_hash"] == off2["verify_hash"]
    assert low["verify_hash"] != off1["verify_hash"]


def test_all_cites_restricted_refuses_no_sources(tmp_path):
    vault, db = _seed(tmp_path)
    _write(vault, "_queries/only-secret.md",
           "type: query\nquestion: secret only\ndate: 2026-07-01\n"
           "cites: ['_vault_/sec-src']\ntags: [query]",
           "Answer citing only the secret source.")
    repo = SQLiteRepository(db)
    reindex_full(repo, VID)
    repo.close()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = wiki_verify_multi.main(
            ["prepare", "only-secret", "--vault", VID,
             "--vault-root", str(vault), "--db-path", str(db),
             "--audience", "internal"])
    env = json.loads(buf.getvalue())
    assert code == 2
    assert env["error"] == "NO_SOURCES"


def test_bad_audience_rejected(tmp_path):
    vault, db = _seed(tmp_path)
    code, env = _prepare(vault, db, "--audience", "NOPE!")
    assert code == 2
    assert env["error"] == "INVALID_AUDIENCE"
    assert "NOPE!" not in json.dumps(env)


def test_verify_hash_gate_catches_audience_drift(tmp_path):
    """vdd-multi logic-MED: apply --verify-hash (from prepare) rejects a
    prepare/apply audience mismatch as VERIFY_CONTEXT_CHANGED — a verdict can
    never file under a different scope than the critics saw."""
    vault, db = _seed(tmp_path)
    code, env = _prepare(vault, db, "--audience", "restricted")
    assert code == 0 and env["restricted_count"] == 0
    verdict = json.dumps({"verdict": "pass", "critics": ["c1"], "findings": []})
    vfile = vault / "verdict.json"
    vfile.write_text(verdict)

    def _apply(*extra: str) -> tuple[int, dict]:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = wiki_verify_multi.main(
                ["apply", "--vault", VID, "--vault-root", str(vault),
                 "--db-path", str(db),
                 "--verification-slug", env["verification_slug"],
                 "--query-slug", "audit-q",
                 "--answer-hash", env["answer_hash"],
                 "--verify-hash", env["verify_hash"],
                 "--verdict-file", str(vfile), *extra])
        return code, json.loads(buf.getvalue())

    # audience drift (prepare@restricted, apply@internal) → loud exit 2.
    code, out = _apply("--audience", "internal")
    assert code == 2
    assert out["error"] == "VERIFY_CONTEXT_CHANGED"
    # symmetric audience → files cleanly.
    code, out = _apply("--audience", "restricted")
    assert code == 0
    assert out["action"] == "filed"
