"""TASK 049 (R-4) — `wiki-query --audience` e2e: the risky slice.

Covers: retrieval filtering (FTS + edge expansion), the only-when-active hash
fold (OFF stability + prepare/apply mismatch → QUESTION_CHANGED), the
grounding gate on an out-of-tier citation, and the full round-trip under a
profile.
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
from scripts.wiki_skills import wiki_query

VID = "audq-vault"


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
    _write(vault, "_sources/open-note.md",
           "type: summary\ntitle: Open Note\ndate: 2026-07-01\ntags: [t]\n"
           "relates_to: [secret-note]",
           "Hermes routes public messages between agents.")
    _write(vault, "_sources/secret-note.md",
           "type: summary\ntitle: Secret Note\ndate: 2026-07-01\ntags: [t]\n"
           "classification: restricted",
           "Hermes secret salary table.")
    db = tmp_path / "g.db"
    repo = SQLiteRepository(db)
    repo.apply_schema()
    repo.register_vault(Vault(
        vault_id=VID, name="v", root_path=vault,
        schema_version="7.0", registered_at=datetime(2026, 7, 1)))
    reindex_full(repo, VID)
    repo.close()
    return vault, db


def _run(vault: Path, db: Path, argv: list[str]) -> tuple[int, dict]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = wiki_query.main(argv + ["--vault", VID, "--vault-root",
                                       str(vault), "--db-path", str(db)])
    return code, json.loads(buf.getvalue())


def _prepare(vault, db, *extra: str) -> tuple[int, dict]:
    return _run(vault, db, ["prepare", "hermes routing messages", *extra])


def test_prepare_filters_and_echoes_audience(tmp_path):
    vault, db = _seed(tmp_path)
    code, env = _prepare(vault, db, "--audience", "internal")
    assert code == 0
    slugs = {h["slug"] for h in env["hits"]}
    assert "secret-note" not in slugs and "open-note" in slugs
    assert env["audience"] == "internal"


def test_off_no_audience_key_and_hash_stable(tmp_path):
    vault, db = _seed(tmp_path)
    code1, env1 = _prepare(vault, db)
    code2, env2 = _prepare(vault, db)
    assert code1 == code2 == 0
    assert "audience" not in env1
    assert env1["question_hash"] == env2["question_hash"]
    assert {h["slug"] for h in env1["hits"]} == {"open-note", "secret-note"}


def test_audience_folds_into_hash_only_when_active(tmp_path):
    """Same retrieval set (audience at ladder top sees everything) — but the
    fold makes the hash differ from the OFF hash."""
    vault, db = _seed(tmp_path)
    _, env_off = _prepare(vault, db)
    _, env_top = _prepare(vault, db, "--audience", "restricted")
    assert {h["slug"] for h in env_off["hits"]} == \
           {h["slug"] for h in env_top["hits"]}
    assert env_off["question_hash"] != env_top["question_hash"]


def test_follow_edges_gate_blocks_restricted_neighbor(tmp_path):
    vault, db = _seed(tmp_path)
    # Retrieval narrowed so only the open note matches; the secret note is
    # reachable ONLY via the relates_to edge.
    q = ["prepare", "public messages agents"]
    code, env = _run(vault, db, q + ["--follow-edges"])
    assert code == 0
    assert {h["slug"] for h in env["hits"]} == {"open-note", "secret-note"}
    code, env = _run(vault, db, q + ["--follow-edges", "--audience", "internal"])
    assert code == 0
    assert {h["slug"] for h in env["hits"]} == {"open-note"}


def test_apply_audience_mismatch_fails_question_changed(tmp_path):
    vault, db = _seed(tmp_path)
    code, env = _prepare(vault, db, "--audience", "restricted")
    assert code == 0
    code, out = _run(vault, db, [
        "apply", "--query-slug", env["query_slug"],
        "--question", "hermes routing messages",
        "--question-hash", env["question_hash"],
        "--answer-stdin", "--citations-file", "does-not-matter.json"])
    # no --audience on apply → hash recomputed WITHOUT the fold → mismatch.
    assert code == 2
    assert out["error"] == "QUESTION_CHANGED"


def test_round_trip_under_profile_and_out_of_tier_citation(tmp_path):
    import sys
    vault, db = _seed(tmp_path)
    code, env = _prepare(vault, db, "--audience", "internal")
    assert code == 0
    cit_path = vault / "citations.json"

    def _apply(cites: list[str]) -> tuple[int, dict]:
        cit_path.write_text(json.dumps(cites))
        stdin_backup = sys.stdin
        sys.stdin = io.TextIOWrapper(io.BytesIO(b"Grounded answer."),
                                     encoding="utf-8")
        try:
            return _run(vault, db, [
                "apply", "--query-slug", env["query_slug"],
                "--question", "hermes routing messages",
                "--question-hash", env["question_hash"],
                "--audience", "internal",
                "--answer-stdin", "--citations-file", str(cit_path)])
        finally:
            sys.stdin = stdin_backup

    # Out-of-tier citation: the restricted page never entered the hit set.
    code, out = _apply(["_vault_/secret-note"])
    assert code == 4
    assert out["error"] == "CITATION_NOT_RETRIEVED"
    # Visible citation files cleanly; envelope echoes the audience.
    code, out = _apply(["_vault_/open-note"])
    assert code == 0
    assert out["action"] == "filed"
    assert out["audience"] == "internal"
    filed = (vault / "_queries" / f"{env['query_slug']}.md").read_text()
    assert "secret" not in filed.lower()
