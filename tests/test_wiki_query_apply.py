"""TASK 007 / bead 007-05 — `wiki-query apply` write-side (R-6.3 / R-6.7).

The anti-hallucination grounding gate + TOCTOU hash-check + Class A write.
DB self-indexing is bead 007-06 (here `page_indexed` is False — the seam).
"""
from __future__ import annotations

import json
import contextlib
import io
from datetime import datetime
from pathlib import Path

from scripts.wiki_index.models import Vault
from scripts.wiki_index.reindex import reindex_full
from scripts.wiki_index.sqlite_repository import SQLiteRepository
from scripts.wiki_skills import wiki_query


def _write(vault: Path, rel: str, fm: str, body: str) -> None:
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\n{fm}\n---\n\n{body}\n", encoding="utf-8")


def _seed(tmp_path: Path) -> tuple[Path, Path]:
    vault = tmp_path / "vault"
    db = tmp_path / "g.db"
    _write(
        vault, "_sources/routing-note.md",
        "type: summary\ntitle: Routing Note\ndate: 2026-05-29\ntags: [t]",
        "# Routing\n\nHermes routes messages between trading agents.",
    )
    repo = SQLiteRepository(db)
    repo.apply_schema()
    repo.register_vault(Vault(
        vault_id="test-vault", name="v", root_path=vault,
        schema_version="4.0", registered_at=datetime(2026, 5, 29),
    ))
    reindex_full(repo, "test-vault")
    repo.close()
    return vault, db


def _run(argv: list[str]) -> tuple[int, dict]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = wiki_query.main(argv)
    return code, json.loads(buf.getvalue())


def _prepare(vault: Path, db: Path, question: str) -> dict:
    _code, env = _run(["prepare", question, "--vault", "test-vault",
                       "--vault-root", str(vault), "--db-path", str(db)])
    return env


def _apply(
    vault: Path, db: Path, slug: str, question: str, qhash: str,
    answer: str, citations: list[str], *extra: str,
) -> tuple[int, dict]:
    (vault / "answer.md").write_text(answer, encoding="utf-8")
    (vault / "cites.json").write_text(json.dumps(citations), encoding="utf-8")
    return _run([
        "apply", "--vault", "test-vault", "--vault-root", str(vault),
        "--db-path", str(db), "--query-slug", slug, "--question", question,
        "--question-hash", qhash,
        "--answer-file", str(vault / "answer.md"),
        "--citations-file", str(vault / "cites.json"), *extra,
    ])


def test_happy_write(tmp_path: Path) -> None:
    vault, db = _seed(tmp_path)
    env = _prepare(vault, db, "Hermes routing")
    code, out = _apply(
        vault, db, env["query_slug"], "Hermes routing", env["question_hash"],
        "Hermes routes via the message bus.", ["_vault_/routing-note"])
    assert code == 0
    assert out["action"] == "filed"
    assert out["page_indexed"] is True  # self-indexed by 007-06
    page = (vault / "_queries" / f"{env['query_slug']}.md").read_text()
    assert "type: query" in page
    assert "cites:" in page and "_vault_/routing-note" in page
    assert "Hermes routes via the message bus." in page


def test_question_changed_on_hash_mismatch(tmp_path: Path) -> None:
    vault, db = _seed(tmp_path)
    env = _prepare(vault, db, "Hermes routing")
    wrong = "0" * 64
    code, out = _apply(vault, db, env["query_slug"], "Hermes routing", wrong,
                       "ans", ["_vault_/routing-note"])
    assert code == 2 and out["error"] == "QUESTION_CHANGED"
    assert not (vault / "_queries" / f"{env['query_slug']}.md").exists()


def test_invalid_question_hash_format(tmp_path: Path) -> None:
    vault, db = _seed(tmp_path)
    code, out = _apply(vault, db, "qslug", "Hermes routing", "NOTHEX",
                       "ans", ["_vault_/routing-note"])
    assert code == 2 and out["error"] == "INVALID_QUESTION_HASH"


def test_grounding_violation_refused(tmp_path: Path) -> None:
    """UC-21: a citation not in the retrieved hit set is refused at the Python
    boundary; nothing is written; the value is not echoed."""
    vault, db = _seed(tmp_path)
    env = _prepare(vault, db, "Hermes routing")
    code, out = _apply(
        vault, db, env["query_slug"], "Hermes routing", env["question_hash"],
        "ans", ["_vault_/not-retrieved"])
    assert code == 4 and out["error"] == "CITATION_NOT_RETRIEVED"
    assert "not-retrieved" not in json.dumps(out)  # CWE-117/209: no echo
    assert not (vault / "_queries" / f"{env['query_slug']}.md").exists()


def test_cross_project_slug_not_grounded(tmp_path: Path) -> None:
    """The grounding key is the full project/slug tuple: a same-slug cite in a
    different project is NOT grounded."""
    vault, db = _seed(tmp_path)
    env = _prepare(vault, db, "Hermes routing")
    code, out = _apply(
        vault, db, env["query_slug"], "Hermes routing", env["question_hash"],
        "ans", ["other-course/routing-note"])
    assert code == 4 and out["error"] == "CITATION_NOT_RETRIEVED"


def _query_page_rows(db: Path) -> int:
    repo = SQLiteRepository(db)
    try:
        with repo._connect() as conn:  # test-only introspection
            return int(conn.execute(
                "SELECT COUNT(*) FROM pages WHERE type='query'").fetchone()[0])
    finally:
        repo.close()


def test_empty_citations_refused(tmp_path: Path) -> None:
    """TASK 072 P1a — an EMPTY citations array must be refused, not filed.

    ★ THE GATE USED TO PASS VACUOUSLY. The shape check bounds citations ABOVE only
    (`len(citations) > _MAX_CITATIONS`) and never below, so `[]` satisfies
    `isinstance(..., list)`, satisfies `all(isinstance(c, str) ...)` vacuously, satisfies the
    per-entry `"/" in c` check vacuously, and makes the grounding gate
    `any(c not in retrieved_keys for c in citations)` **False** — so
    `CITATION_NOT_RETRIEVED`, the anti-hallucination mechanism itself, passed on nothing.
    `_render_query_page`'s `if citations:` guard then skipped `## Sources` and a `cites: []`
    page was filed AND self-indexed at exit 0.

    Measured on `main` before the fix: exit 0, envelope
    `{"query_slug": "hermes-routing", "cites": [], "page_indexed": true, "action": "filed"}`.
    """
    vault, db = _seed(tmp_path)
    env = _prepare(vault, db, "Hermes routing")
    # NON-VACUITY CONTROL (TASK 061): exercise the floor over a corpus where the grounding
    # gate CAN fire. A retrieval that returned nothing would make this test pass for the
    # wrong reason — see the sibling test for that case, deliberately kept separate.
    assert env["retrieved_count"] >= 1

    code, out = _apply(
        vault, db, env["query_slug"], "Hermes routing", env["question_hash"], "ans", [])

    # Assert the ENVELOPE, not merely the exit code: exit 4 is shared with
    # CITATION_NOT_RETRIEVED / INVALID_CITATIONS / ANSWER_TOO_LARGE, so a bare `code == 4`
    # could not tell this refusal from any other and would survive the wrong fix.
    assert code == 4
    assert out["error"] == "NO_CITATIONS"
    assert out["field"] == "citations"
    assert not (vault / "_queries" / f"{env['query_slug']}.md").exists()
    assert _query_page_rows(db) == 0


def test_min_hits_zero_cannot_file_an_ungrounded_page(tmp_path: Path) -> None:
    """The composite path: `--min-hits 0` is accepted on `prepare` (`len(hits) < 0` is never
    true), so `NO_CONTEXT` never fires and `apply` — which has no `--min-hits` at all —
    reproduces `_question_hash(question, [])` identically, so `QUESTION_CHANGED` does not
    catch it either. Together with the missing floor that was a complete exit-0 path to a
    filed, indexed, zero-grounding answer page.

    BOTH branches must now refuse: with an empty retrieval the key set is empty, so a
    non-empty citation list fails `CITATION_NOT_RETRIEVED` and an empty one fails
    `NO_CITATIONS`. One condition closes both."""
    vault, db = _seed(tmp_path)
    question = "zzz nothing whatsoever matches this qqq"
    code, env = _run(["prepare", question, "--vault", "test-vault",
                      "--vault-root", str(vault), "--db-path", str(db), "--min-hits", "0"])
    assert code == 0
    assert env["retrieved_count"] == 0  # the vacuous-retrieval precondition, asserted

    empty_code, empty_out = _apply(
        vault, db, env["query_slug"], question, env["question_hash"], "ans", [])
    assert empty_code == 4 and empty_out["error"] == "NO_CITATIONS"

    cited_code, cited_out = _apply(
        vault, db, env["query_slug"], question, env["question_hash"], "ans",
        ["_vault_/routing-note"])
    assert cited_code == 4 and cited_out["error"] == "CITATION_NOT_RETRIEVED"

    assert not (vault / "_queries" / f"{env['query_slug']}.md").exists()
    assert _query_page_rows(db) == 0


def test_invalid_citations_shape(tmp_path: Path) -> None:
    vault, db = _seed(tmp_path)
    env = _prepare(vault, db, "Hermes routing")
    # not a project/slug (no slash)
    code, out = _apply(vault, db, env["query_slug"], "Hermes routing",
                       env["question_hash"], "ans", ["routingnote"])
    assert code == 4 and out["error"] == "INVALID_CITATIONS"


def test_idempotent_skip_and_force(tmp_path: Path) -> None:
    vault, db = _seed(tmp_path)
    env = _prepare(vault, db, "Hermes routing")
    a = ("Hermes routes via the message bus.", ["_vault_/routing-note"])
    c1, o1 = _apply(vault, db, env["query_slug"], "Hermes routing",
                    env["question_hash"], *a)
    assert o1["action"] == "filed"
    c2, o2 = _apply(vault, db, env["query_slug"], "Hermes routing",
                    env["question_hash"], *a)
    assert o2["action"] == "unchanged"  # content-hash skip
    c3, o3 = _apply(vault, db, env["query_slug"], "Hermes routing",
                    env["question_hash"], *a, "--force")
    assert o3["action"] == "filed"  # --force overrides the skip


def test_answer_body_sanitised(tmp_path: Path) -> None:
    """The synthesised answer is sanitised on egress (R-6.3d): injection
    sequences are neutralised in the written Class A body."""
    vault, db = _seed(tmp_path)
    env = _prepare(vault, db, "Hermes routing")
    _code, _out = _apply(
        vault, db, env["query_slug"], "Hermes routing", env["question_hash"],
        "Danger [[inject]] and <script>alert(1)</script>", ["_vault_/routing-note"])
    page = (vault / "_queries" / f"{env['query_slug']}.md").read_text()
    assert "[[inject]]" not in page  # wikilink injection neutralised
    assert "<script>" not in page    # HTML neutralised
    assert "&lt;script&gt;" in page
