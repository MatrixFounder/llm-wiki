"""TASK 008 / bead 008-07 — `wiki-verify-multi apply` index-side (R-8.4/8.6).

strict-TDD. Self-index the verdict page via DIRECT DAL (upsert_page +
replace_refs on one connection — no manifest N+1); write the `verifies` ref;
record verify-state; fire one `verify` log event. The load-bearing property is
**byte-identity**: the apply-written `pages` row + `verifies` ref equal a
`wiki-reindex --full` rebuild (the UC-26 §D8 symmetry 008-09 leans on).
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

VAULT_ID = "test-vault"
QSLUG = "how-hermes-routes"
VSLUG = "verify-how-hermes-routes"  # the distinct verdict-page slug (no PK collision)


def _write(vault: Path, rel: str, fm: str, body: str) -> None:
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\n{fm}\n---\n\n{body}\n", encoding="utf-8")


def _seed(tmp_path: Path) -> tuple[Path, Path]:
    vault, db = tmp_path / "vault", tmp_path / "g.db"
    _write(vault, "_sources/foo.md",
           "type: summary\ntitle: Foo\ndate: 2026-05-29\ntags: [t]",
           "# Foo\n\nHermes routes via the bus.")
    _write(vault, f"_queries/{QSLUG}.md",
           "type: query\ntitle: Q\ndate: 2026-05-29\ntags: [query]\n"
           "question: How does Hermes route?\ncites: ['_vault_/foo']",
           "# Answer\n\nHermes routes via the bus.")
    repo = SQLiteRepository(db)
    repo.apply_schema()
    repo.register_vault(Vault(vault_id=VAULT_ID, name="v", root_path=vault,
                              schema_version="5.0",
                              registered_at=datetime(2026, 5, 29)))
    reindex_full(repo, VAULT_ID)
    repo.close()
    return vault, db


def _prepare(vault: Path, db: Path) -> dict:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        wiki_verify_multi.main(["prepare", QSLUG, "--vault", VAULT_ID,
                                "--vault-root", str(vault), "--db-path", str(db)])
    return json.loads(buf.getvalue())


def _apply(vault: Path, db: Path, verdict: dict, *extra: str) -> tuple[int, dict]:
    prep = _prepare(vault, db)
    (vault / "verdict.json").write_text(json.dumps(verdict), encoding="utf-8")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = wiki_verify_multi.main(
            ["apply", "--vault", VAULT_ID, "--vault-root", str(vault),
             "--db-path", str(db), "--verification-slug", prep["verification_slug"],
             "--query-slug", QSLUG, "--answer-hash", prep["answer_hash"],
             "--verdict-file", str(vault / "verdict.json"), *extra])
    return code, json.loads(buf.getvalue())


def _refs(db: Path) -> set[tuple[str, str, str]]:
    repo = SQLiteRepository(db)
    try:
        return {
            (r["page_slug"], r["entity_slug"], r["ref_type"])
            for r in repo._connect().execute(
                "SELECT page_slug, entity_slug, ref_type FROM page_entity_refs "
                "WHERE vault_id = ? AND page_slug = ?", (VAULT_ID, VSLUG)).fetchall()
        }
    finally:
        repo.close()


_PASS = {"verdict": "pass", "critics": ["factual"],
         "findings": [{"lens": "factual", "severity": "low", "claim": "ok",
                       "source": "_vault_/foo", "note": "supported"}]}
_FAIL = {"verdict": "fail", "critics": ["security"],
         "findings": [{"lens": "security", "severity": "high", "claim": "x",
                       "source": "_vault_/foo", "note": "n"}]}


def test_verdict_page_indexed(tmp_path: Path) -> None:
    vault, db = _seed(tmp_path)
    code, env = _apply(vault, db, _PASS)
    assert code == 0 and env["page_indexed"] is True
    repo = SQLiteRepository(db)
    try:
        row = repo.get_page(VAULT_ID, VSLUG, "_vault_")
    finally:
        repo.close()
    assert row is not None and row.type == "verification"


def test_query_page_row_survives_verification(tmp_path: Path) -> None:
    """Regression for the found-in-dev PK-collision (operator STOP): filing a
    verdict must NOT overwrite the audited query page's `pages` row. Both rows
    coexist because the verdict page has a distinct `verify-<slug>` slug."""
    vault, db = _seed(tmp_path)
    _apply(vault, db, _PASS)
    repo = SQLiteRepository(db)
    try:
        q = repo.get_page(VAULT_ID, QSLUG, "_vault_")
        v = repo.get_page(VAULT_ID, VSLUG, "_vault_")
    finally:
        repo.close()
    assert q is not None and q.type == "query", "verifying overwrote the query page row"
    assert v is not None and v.type == "verification"


def test_verifies_ref_written(tmp_path: Path) -> None:
    vault, db = _seed(tmp_path)
    _apply(vault, db, _PASS)
    assert (VSLUG, QSLUG, "verifies") in _refs(db)


def test_verify_log_event_with_provenance(tmp_path: Path) -> None:
    vault, db = _seed(tmp_path)
    _apply(vault, db, _PASS, "--orchestrator-id", "ci-bot")
    repo = SQLiteRepository(db)
    try:
        rows = repo._connect().execute(
            "SELECT event_type, subject, details_json FROM log_events "
            "WHERE vault_id=? AND event_type='verify'", (VAULT_ID,)).fetchall()
    finally:
        repo.close()
    assert len(rows) == 1
    assert rows[0]["subject"] == VSLUG
    assert "ci-bot" in rows[0]["details_json"]


def test_verify_state_recorded_then_unchanged(tmp_path: Path) -> None:
    vault, db = _seed(tmp_path)
    _apply(vault, db, _PASS)
    assert _prepare(vault, db)["is_unchanged"] is True  # state armed by apply


def test_fail_still_indexes(tmp_path: Path) -> None:
    vault, db = _seed(tmp_path)
    code, env = _apply(vault, db, _FAIL)
    assert code == 6 and env["page_indexed"] is True
    assert (VSLUG, QSLUG, "verifies") in _refs(db)


def test_rearm_verify_state_when_state_absent(tmp_path: Path) -> None:
    """vdd-multi L-2: if the verdict page exists but its verify-state row is
    absent (e.g. a prior apply crashed after the write, before record), a re-run
    (content unchanged) must RE-ARM the state so `prepare` short-circuits —
    rather than re-running the four-critic audit forever."""
    vault, db = _seed(tmp_path)
    _apply(vault, db, _PASS)
    # simulate the crash window: wipe the verify-state row but keep the file
    repo = SQLiteRepository(db)
    repo._connect().execute(
        "DELETE FROM source_state WHERE vault_id=? AND source_kind='verification'",
        (VAULT_ID,))
    repo._connect().commit()
    repo.close()
    # re-apply: content-hash skip (unchanged) but state must be re-recorded
    _code, env = _apply(vault, db, _PASS)
    assert env["action"] == "unchanged"
    # prepare now short-circuits (state re-armed)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        wiki_verify_multi.main(["prepare", QSLUG, "--vault", VAULT_ID,
                                "--vault-root", str(vault), "--db-path", str(db)])
    assert json.loads(buf.getvalue())["is_unchanged"] is True


def test_byte_identity_with_reindex_rebuild(tmp_path: Path) -> None:
    """The §D8 symmetry keystone: the apply-written refs equal a full-reindex
    rebuild from the Class A markdown alone."""
    vault, db = _seed(tmp_path)
    _apply(vault, db, _PASS)
    apply_refs = _refs(db)
    assert (VSLUG, QSLUG, "verifies") in apply_refs

    # drop DB → re-seed schema + vault → reindex_full → compare the ref set
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(db) + suffix)
        if p.exists():
            p.unlink()
    repo = SQLiteRepository(db)
    repo.apply_schema()
    repo.register_vault(Vault(vault_id=VAULT_ID, name="v", root_path=vault,
                              schema_version="5.0",
                              registered_at=datetime(2026, 5, 29)))
    reindex_full(repo, VAULT_ID)
    repo.close()
    assert _refs(db) == apply_refs, "apply-written refs differ from reindex rebuild"
