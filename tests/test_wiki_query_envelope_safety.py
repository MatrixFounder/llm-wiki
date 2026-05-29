"""TASK 007 / bead 007-10 — `wiki-query` error envelopes never echo content.

Extends the CWE-117/209 "envelope never echoes operator-supplied content"
invariant (TASK 003 v3.1 / TASK 005) to the wiki-query surfaces: question,
answer, citation. Envelopes carry `{error, field?, reason}` only.
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

VAULT_ID = "test-vault"
CANARY = "canary-zzz-do-not-echo"


def _run(argv: list[str]) -> tuple[int, str]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = wiki_query.main(argv)
    return code, buf.getvalue()


def _seed(tmp_path: Path) -> tuple[Path, Path]:
    vault, db = tmp_path / "vault", tmp_path / "g.db"
    (vault / "_sources").mkdir(parents=True, exist_ok=True)
    (vault / "_sources" / "routing-note.md").write_text(
        "---\ntype: summary\ntitle: Routing\ndate: 2026-05-29\ntags: [t]\n---\n\n"
        "Hermes routes messages.\n", encoding="utf-8")
    repo = SQLiteRepository(db)
    repo.apply_schema()
    repo.register_vault(Vault(vault_id=VAULT_ID, name="v", root_path=vault,
                              schema_version="4.0",
                              registered_at=datetime(2026, 5, 29)))
    reindex_full(repo, VAULT_ID)
    repo.close()
    return vault, db


def test_no_context_envelope_omits_question(tmp_path: Path) -> None:
    vault, db = _seed(tmp_path)
    code, out = _run(["prepare", CANARY + "-nomatch", "--vault", VAULT_ID,
                      "--vault-root", str(vault), "--db-path", str(db)])
    assert code == 2 and "NO_CONTEXT" in out
    assert CANARY not in out


def test_citation_not_retrieved_envelope_omits_citation(tmp_path: Path) -> None:
    vault, db = _seed(tmp_path)
    _c, prep_out = _run(["prepare", "Hermes", "--vault", VAULT_ID,
                         "--vault-root", str(vault), "--db-path", str(db)])
    prep = json.loads(prep_out)
    (vault / "answer.md").write_text("ans", encoding="utf-8")
    (vault / "cites.json").write_text(json.dumps([f"_vault_/{CANARY}"]),
                                      encoding="utf-8")
    code, out = _run(["apply", "--vault", VAULT_ID, "--vault-root", str(vault),
                      "--db-path", str(db), "--query-slug", prep["query_slug"],
                      "--question", "Hermes", "--question-hash", prep["question_hash"],
                      "--answer-file", str(vault / "answer.md"),
                      "--citations-file", str(vault / "cites.json")])
    assert code == 4 and "CITATION_NOT_RETRIEVED" in out
    assert CANARY not in out  # the un-grounded citation value is NOT echoed


def test_invalid_citations_envelope_omits_value(tmp_path: Path) -> None:
    vault, db = _seed(tmp_path)
    _c, prep_out = _run(["prepare", "Hermes", "--vault", VAULT_ID,
                         "--vault-root", str(vault), "--db-path", str(db)])
    prep = json.loads(prep_out)
    (vault / "answer.md").write_text("ans", encoding="utf-8")
    # malformed: not a project/slug, carries the canary
    (vault / "cites.json").write_text(json.dumps([CANARY]), encoding="utf-8")
    code, out = _run(["apply", "--vault", VAULT_ID, "--vault-root", str(vault),
                      "--db-path", str(db), "--query-slug", prep["query_slug"],
                      "--question", "Hermes", "--question-hash", prep["question_hash"],
                      "--answer-file", str(vault / "answer.md"),
                      "--citations-file", str(vault / "cites.json")])
    assert code == 4 and "INVALID_CITATIONS" in out
    assert CANARY not in out


def test_question_changed_envelope_omits_question(tmp_path: Path) -> None:
    vault, db = _seed(tmp_path)
    (vault / "answer.md").write_text("ans", encoding="utf-8")
    (vault / "cites.json").write_text(json.dumps(["_vault_/routing-note"]),
                                      encoding="utf-8")
    code, out = _run(["apply", "--vault", VAULT_ID, "--vault-root", str(vault),
                      "--db-path", str(db), "--query-slug", "q",
                      "--question", "Hermes " + CANARY, "--question-hash", "0" * 64,
                      "--answer-file", str(vault / "answer.md"),
                      "--citations-file", str(vault / "cites.json")])
    assert code == 2 and "QUESTION_CHANGED" in out
    assert CANARY not in out  # the question is not echoed back
