"""TASK 007 / bead 007-09 — end-to-end + compounding acceptance (UC-16..21).

Drives the real `bin/`-equivalent CLI (`wiki_query.main`) on a throwaway /tmp
vault. Synthesis is constructed in-test (no real LLM — `tdd-stub-first` §3).
Citations target a concept ENTITY (`hermes-agent`) so the Q-A9(b) consumer-
safety assertions (backlinks resolve, no false orphan) are clean.
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
from scripts.wiki_skills import wiki_query, wiki_search

VAULT_ID = "test-vault"


def _write(vault: Path, rel: str, fm: str, body: str) -> None:
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\n{fm}\n---\n\n{body}\n", encoding="utf-8")


def _run(argv: list[str]) -> tuple[int, dict]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = wiki_query.main(argv)
    return code, json.loads(buf.getvalue())


def _seed(tmp_path: Path) -> tuple[Path, Path]:
    vault, db = tmp_path / "vault", tmp_path / "g.db"
    _write(vault, "_concepts/hermes-agent.md",
           "type: concept\nslug: hermes-agent\ntitle: Hermes Agent\n"
           "date: 2026-05-29\ntags: [concept]",
           "# Hermes Agent\n\nHermes routes messages between trading agents.")
    _write(vault, "_sources/routing-note.md",
           "type: summary\ntitle: Routing Note\ndate: 2026-05-29\ntags: [t]",
           "# Routing\n\nThe routing note discusses [[hermes-agent]] and the bus.")
    repo = SQLiteRepository(db)
    repo.apply_schema()
    repo.register_vault(Vault(vault_id=VAULT_ID, name="v", root_path=vault,
                              schema_version="4.0",
                              registered_at=datetime(2026, 5, 29)))
    reindex_full(repo, VAULT_ID)
    repo.close()
    return vault, db


def _prepare(vault: Path, db: Path, q: str = "Hermes", *extra: str) -> dict:
    _c, env = _run(["prepare", q, "--vault", VAULT_ID, "--vault-root", str(vault),
                    "--db-path", str(db), *extra])
    return env


def _apply(vault: Path, db: Path, prep: dict, citations: list[str],
           answer: str = "Hermes routes via the bus.", *extra: str) -> tuple[int, dict]:
    (vault / "answer.md").write_text(answer, encoding="utf-8")
    (vault / "cites.json").write_text(json.dumps(citations), encoding="utf-8")
    return _run(["apply", "--vault", VAULT_ID, "--vault-root", str(vault),
                 "--db-path", str(db), "--query-slug", prep["query_slug"],
                 "--question", prep["question"], "--question-hash", prep["question_hash"],
                 "--answer-file", str(vault / "answer.md"),
                 "--citations-file", str(vault / "cites.json"), *extra])


def _search(db: Path, q: str, *extra: str) -> list[dict]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        wiki_search.main([q, "--vaults", VAULT_ID, "--db-path", str(db), *extra])
    return json.loads(buf.getvalue())["hits"]


# --------------------------------------------------------------------------- #
def test_uc16_ask_then_cited_answer_page(tmp_path: Path) -> None:
    vault, db = _seed(tmp_path)
    prep = _prepare(vault, db)
    code, out = _apply(vault, db, prep, ["_vault_/hermes-agent"])
    assert code == 0 and out["action"] == "filed" and out["page_indexed"] is True
    page = (vault / "_queries" / f"{prep['query_slug']}.md").read_text()
    assert "type: query" in page and "_vault_/hermes-agent" in page


def test_uc17_idempotent_rerun_and_force(tmp_path: Path) -> None:
    vault, db = _seed(tmp_path)
    prep = _prepare(vault, db)
    _apply(vault, db, prep, ["_vault_/hermes-agent"])
    # re-prepare the same question on the unchanged corpus → is_unchanged
    prep2 = _prepare(vault, db)
    assert prep2["is_unchanged"] is True
    # re-apply identical content → unchanged (content-hash skip); --force re-files
    _c, out_same = _apply(vault, db, prep, ["_vault_/hermes-agent"])
    assert out_same["action"] == "unchanged"
    _c2, out_force = _apply(vault, db, prep, ["_vault_/hermes-agent"], "Hermes routes via the bus.", "--force")
    assert out_force["action"] == "filed"


def test_uc18_no_context_writes_nothing(tmp_path: Path) -> None:
    vault, db = _seed(tmp_path)
    code, env = _run(["prepare", "quantumchromodynamics", "--vault", VAULT_ID,
                      "--vault-root", str(vault), "--db-path", str(db)])
    assert code == 2 and env["error"] == "NO_CONTEXT"
    # nothing written, no query page row created
    assert not (vault / "_queries").exists() or not any((vault / "_queries").glob("*.md"))
    repo = SQLiteRepository(db)
    n = repo._connect().execute(
        "SELECT COUNT(*) AS n FROM pages WHERE vault_id=? AND type='query'",
        (VAULT_ID,)).fetchone()["n"]
    repo.close()
    assert n == 0


def test_uc19_compounding_search_backlinks_and_consumer_safety(tmp_path: Path) -> None:
    vault, db = _seed(tmp_path)
    prep = _prepare(vault, db)
    _apply(vault, db, prep, ["_vault_/hermes-agent"])
    slug = prep["query_slug"]

    # a later search finds the filed query page
    assert any(h["slug"] == slug and h["type"] == "query"
               for h in _search(db, "Hermes"))
    # --types query filters TO query pages; excluding it drops the query page
    assert all(h["type"] == "query" for h in _search(db, "Hermes", "--types", "query"))
    assert not any(h["slug"] == slug
                   for h in _search(db, "Hermes", "--types", "concept,summary"))

    repo = SQLiteRepository(db)
    try:
        # cited backlink: the query page → hermes-agent
        backlink_pages = {r.page_slug for r in repo.get_backlinks(VAULT_ID, "hermes-agent")}
        assert slug in backlink_pages
        # Q-A9(b) consumer-safety: the cited entity target is NOT a false orphan
        orphan_targets = {o.target_slug for o in repo.find_orphan_links(VAULT_ID)}
        assert "hermes-agent" not in orphan_targets
    finally:
        repo.close()


def test_uc21_grounding_violation_refused(tmp_path: Path) -> None:
    vault, db = _seed(tmp_path)
    prep = _prepare(vault, db)
    code, out = _apply(vault, db, prep, ["_vault_/not-a-real-hit"])
    assert code == 4 and out["error"] == "CITATION_NOT_RETRIEVED"
    assert not (vault / "_queries" / f"{prep['query_slug']}.md").exists()
