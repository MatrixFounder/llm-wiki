"""TASK 007 / bead 007-06 — `wiki-query apply` index-side (R-6.4 / R-6.6).

Self-index the filed query page via DIRECT `upsert_page` + `replace_refs` (NOT
the manifest/`main(argv)` N+1), write `cited` backlinks, record idempotency
state, and fire one `query` log event. Closes the compounding loop.
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


def _write(vault: Path, rel: str, fm: str, body: str) -> None:
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\n{fm}\n---\n\n{body}\n", encoding="utf-8")


def _seed(tmp_path: Path) -> tuple[Path, Path]:
    vault, db = tmp_path / "vault", tmp_path / "g.db"
    _write(vault, "_sources/routing-note.md",
           "type: summary\ntitle: Routing Note\ndate: 2026-05-29\ntags: [t]",
           "# Routing\n\nHermes routes messages between trading agents.")
    repo = SQLiteRepository(db)
    repo.apply_schema()
    repo.register_vault(Vault(vault_id="test-vault", name="v", root_path=vault,
                              schema_version="4.0",
                              registered_at=datetime(2026, 5, 29)))
    reindex_full(repo, "test-vault")
    repo.close()
    return vault, db


def _run(argv: list[str]) -> tuple[int, dict]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = wiki_query.main(argv)
    return code, json.loads(buf.getvalue())


def _file_query(tmp_path: Path) -> tuple[Path, Path, dict, dict]:
    """Seed, prepare, then apply a query page. Returns (vault, db, prep, applied)."""
    vault, db = _seed(tmp_path)
    _c, prep = _run(["prepare", "Hermes routing", "--vault", "test-vault",
                     "--vault-root", str(vault), "--db-path", str(db)])
    (vault / "answer.md").write_text("Hermes routes via the message bus.",
                                     encoding="utf-8")
    (vault / "cites.json").write_text(json.dumps(["_vault_/routing-note"]),
                                      encoding="utf-8")
    _c2, applied = _run([
        "apply", "--vault", "test-vault", "--vault-root", str(vault),
        "--db-path", str(db), "--query-slug", prep["query_slug"],
        "--question", "Hermes routing", "--question-hash", prep["question_hash"],
        "--answer-file", str(vault / "answer.md"),
        "--citations-file", str(vault / "cites.json")])
    return vault, db, prep, applied


def _refs(db: Path) -> set[tuple[str, str, str]]:
    repo = SQLiteRepository(db)
    try:
        return {(r["page_slug"], r["entity_slug"], r["ref_type"])
                for r in repo._connect().execute(
                    "SELECT page_slug, entity_slug, ref_type FROM page_entity_refs "
                    "WHERE vault_id='test-vault'").fetchall()}
    finally:
        repo.close()


def test_query_page_self_indexed_and_searchable(tmp_path: Path) -> None:
    vault, db, prep, applied = _file_query(tmp_path)
    assert applied["page_indexed"] is True and applied["action"] == "filed"
    repo = SQLiteRepository(db)
    row = repo._connect().execute(
        "SELECT type FROM pages WHERE vault_id='test-vault' AND slug=? "
        "AND project='_vault_'", (prep["query_slug"],)).fetchone()
    repo.close()
    assert row is not None and row["type"] == "query"
    # FTS-searchable (compounding): a search returns the filed query page.
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        wiki_search.main(["Hermes", "--vaults", "test-vault", "--db-path", str(db)])
    hits = json.loads(buf.getvalue())["hits"]
    assert any(h["slug"] == prep["query_slug"] and h["type"] == "query" for h in hits)


def test_cited_backlinks_written(tmp_path: Path) -> None:
    _vault, db, prep, _applied = _file_query(tmp_path)
    refs = _refs(db)
    assert (prep["query_slug"], "routing-note", "cited") in refs
    # Q-A9 dual-ref: the body `## Sources [[routing-note]]` also yields a
    # `mentioned` ref to the SAME slug (PK-distinct), matching the reindex rebuild.
    assert (prep["query_slug"], "routing-note", "mentioned") in refs


def test_query_log_event_fired(tmp_path: Path) -> None:
    _vault, db, prep, _applied = _file_query(tmp_path)
    repo = SQLiteRepository(db)
    rows = repo._connect().execute(
        "SELECT event_type, subject FROM log_events "
        "WHERE vault_id='test-vault' AND event_type='query'").fetchall()
    repo.close()
    assert len(rows) == 1 and rows[0]["subject"] == prep["query_slug"]


def test_idempotency_state_recorded(tmp_path: Path) -> None:
    vault, db, prep, _applied = _file_query(tmp_path)
    repo = SQLiteRepository(db)
    assert repo.check_query_state("test-vault", prep["query_slug"]) == prep["question_hash"]
    repo.close()
    # a subsequent prepare of the same question on the unchanged corpus → unchanged
    _c, prep2 = _run(["prepare", "Hermes routing", "--vault", "test-vault",
                      "--vault-root", str(vault), "--db-path", str(db)])
    assert prep2["is_unchanged"] is True


def test_idempotency_holds_at_scale_above_limit(tmp_path: Path) -> None:
    """vdd-multi HIGH regression: with >`limit` matching non-query pages, the
    self-indexed query page must NOT evict a real hit from the top-`limit`
    window — so a same-question re-prepare stays `is_unchanged=True`. This fails
    if the type=query exclusion is a POST-LIMIT Python filter (it would let the
    query page consume a slot and drop a genuine hit); it holds because the
    exclusion is pushed into the SQL (exclude_types) BEFORE the LIMIT."""
    vault, db = tmp_path / "vault", tmp_path / "g.db"
    # 15 matching source pages (> the default --limit 10) + 1 concept.
    _write(vault, "_concepts/hermes-agent.md",
           "type: concept\nslug: hermes-agent\ntitle: Hermes Agent\n"
           "date: 2026-05-29\ntags: [concept]", "# Hermes Agent\n\nHermes routes.")
    for i in range(15):
        _write(vault, f"_sources/note-{i:02d}.md",
               f"type: summary\ntitle: Note {i}\ndate: 2026-05-29\ntags: [t]",
               "# Note\n\nHermes routes messages between trading agents.")
    repo = SQLiteRepository(db)
    repo.apply_schema()
    repo.register_vault(Vault(vault_id="test-vault", name="v", root_path=vault,
                              schema_version="4.0",
                              registered_at=datetime(2026, 5, 29)))
    reindex_full(repo, "test-vault")
    repo.close()

    _c, prep = _run(["prepare", "Hermes", "--vault", "test-vault",
                     "--vault-root", str(vault), "--db-path", str(db)])
    assert prep["retrieved_count"] == 10  # hits the default limit

    (vault / "answer.md").write_text("Hermes routes via the bus.", encoding="utf-8")
    (vault / "cites.json").write_text(json.dumps(["_vault_/hermes-agent"]),
                                      encoding="utf-8")
    _run(["apply", "--vault", "test-vault", "--vault-root", str(vault),
          "--db-path", str(db), "--query-slug", prep["query_slug"],
          "--question", "Hermes", "--question-hash", prep["question_hash"],
          "--answer-file", str(vault / "answer.md"),
          "--citations-file", str(vault / "cites.json")])

    # re-prepare the SAME question on the now-larger (query page added) corpus:
    # the query page is excluded in SQL before the LIMIT, so the top-10 non-query
    # hits + hash are unchanged → idempotent.
    _c2, prep2 = _run(["prepare", "Hermes", "--vault", "test-vault",
                       "--vault-root", str(vault), "--db-path", str(db)])
    assert prep2["retrieved_count"] == 10
    assert prep2["question_hash"] == prep["question_hash"]
    assert prep2["is_unchanged"] is True
    # and an apply re-run carrying the original hash is NOT spuriously rejected
    _c3, out3 = _run(["apply", "--vault", "test-vault", "--vault-root", str(vault),
                      "--db-path", str(db), "--query-slug", prep["query_slug"],
                      "--question", "Hermes", "--question-hash", prep["question_hash"],
                      "--answer-file", str(vault / "answer.md"),
                      "--citations-file", str(vault / "cites.json"), "--force"])
    assert out3.get("action") == "filed"  # no spurious QUESTION_CHANGED


def test_no_manifest_n_plus_one_path(tmp_path: Path, monkeypatch: object) -> None:
    """Self-index must NOT route through the manifest/`main(argv)` N+1
    (H-PERF-3): patch `index_from_manifest` to explode — apply must still
    succeed via the direct `upsert_page` + `replace_refs` path."""
    import scripts.wiki_skills._manifest_consumer as mc

    def _boom(*_a: object, **_k: object) -> object:
        raise AssertionError("apply must not use index_from_manifest (N+1)")

    monkeypatch.setattr(mc, "index_from_manifest", _boom)  # type: ignore[attr-defined]
    _vault, _db, _prep, applied = _file_query(tmp_path)
    assert applied["page_indexed"] is True
