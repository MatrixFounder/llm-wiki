"""TASK 007 / bead 007-08 — §D8 durability round-trip for query pages (UC-20).

The binding acceptance gate: a query page filed by `wiki-query apply`
reconstructs FROM CLASS A MARKDOWN ALONE after a full DB rebuild — the page is
rediscovered (`type=query`) and its `cited` refs are re-materialised from the
`cites:` frontmatter by the R-6.5e reindex read-side, NOT lost and NOT degraded
to `mentioned`. Also asserts apply-written ≡ reindex-rebuilt (the byte-identical
symmetry the durability promise rests on).

AM-3 alias canonicalization of `cited` targets is covered by
`tests/test_reindex_cites.py::test_e2e_02_*` — not re-tested here.
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


def _run(argv: list[str]) -> dict:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        wiki_query.main(argv)
    return json.loads(buf.getvalue())


def _refs(db: Path) -> set[tuple[str, str, str]]:
    repo = SQLiteRepository(db)
    try:
        return {(r["page_slug"], r["entity_slug"], r["ref_type"])
                for r in repo._connect().execute(
                    "SELECT page_slug, entity_slug, ref_type FROM page_entity_refs "
                    "WHERE vault_id=?", (VAULT_ID,)).fetchall()}
    finally:
        repo.close()


def _rebuild_db(db: Path, vault: Path) -> None:
    """Delete the DB and rebuild from Class A markdown alone (§D8)."""
    if db.exists():
        db.unlink()
        for suffix in ("-wal", "-shm"):
            p = Path(str(db) + suffix)
            if p.exists():
                p.unlink()
    repo = SQLiteRepository(db)
    repo.apply_schema()
    repo.register_vault(Vault(vault_id=VAULT_ID, name="v", root_path=vault,
                              schema_version="4.0",
                              registered_at=datetime(2026, 5, 29)))
    reindex_full(repo, VAULT_ID)
    repo.close()


def _file_a_query(tmp_path: Path) -> tuple[Path, Path, str]:
    """Seed → prepare → apply; return (vault, db, query_slug)."""
    vault, db = tmp_path / "vault", tmp_path / "g.db"
    _write(vault, "_sources/routing-note.md",
           "type: summary\ntitle: Routing Note\ndate: 2026-05-29\ntags: [t]",
           "# Routing\n\nHermes routes messages between trading agents.")
    repo = SQLiteRepository(db)
    repo.apply_schema()
    repo.register_vault(Vault(vault_id=VAULT_ID, name="v", root_path=vault,
                              schema_version="4.0",
                              registered_at=datetime(2026, 5, 29)))
    reindex_full(repo, VAULT_ID)
    repo.close()
    prep = _run(["prepare", "Hermes routing", "--vault", VAULT_ID,
                 "--vault-root", str(vault), "--db-path", str(db)])
    (vault / "answer.md").write_text("Hermes routes via the message bus.",
                                     encoding="utf-8")
    (vault / "cites.json").write_text(json.dumps(["_vault_/routing-note"]),
                                      encoding="utf-8")
    _run(["apply", "--vault", VAULT_ID, "--vault-root", str(vault),
          "--db-path", str(db), "--query-slug", prep["query_slug"],
          "--question", "Hermes routing", "--question-hash", prep["question_hash"],
          "--answer-file", str(vault / "answer.md"),
          "--citations-file", str(vault / "cites.json")])
    return vault, db, prep["query_slug"]


def test_uc20_query_page_and_cited_refs_survive_full_reindex(tmp_path: Path) -> None:
    vault, db, slug = _file_a_query(tmp_path)

    # Snapshot the apply-written state.
    before = _refs(db)
    assert (slug, "routing-note", "cited") in before

    # §D8: delete the DB, rebuild from markdown alone.
    _rebuild_db(db, vault)
    after = _refs(db)

    # 1. The query page row is rediscovered as type=query (proves _queries ∈
    #    PAGE_SUBDIRS, 007-01).
    repo = SQLiteRepository(db)
    row = repo._connect().execute(
        "SELECT type FROM pages WHERE vault_id=? AND slug=? AND project='_vault_'",
        (VAULT_ID, slug)).fetchone()
    repo.close()
    assert row is not None and row["type"] == "query"

    # 2. The `cited` ref is reconstructed from cites: frontmatter alone, as
    #    'cited' — NOT lost (R-6.5e). The ref_types reaching `routing-note` from
    #    the query page must INCLUDE 'cited' (not degraded to only 'mentioned').
    reftypes_to_target = {rt for (s, e, rt) in after
                          if s == slug and e == "routing-note"}
    assert "cited" in reftypes_to_target, (
        f"cited ref lost/degraded on reindex; got {reftypes_to_target}")
    # The body `## Sources [[routing-note]]` yields a coexisting 'mentioned' ref
    # (Q-A9 dual-ref) — both survive, PK-distinct.
    assert "mentioned" in reftypes_to_target

    # 3. apply-written ≡ reindex-rebuilt for the query page's refs (the
    #    byte-identical symmetry the durability promise rests on).
    before_q = {r for r in before if r[0] == slug}
    after_q = {r for r in after if r[0] == slug}
    assert before_q == after_q, f"apply vs reindex ref drift: {before_q} != {after_q}"


def test_uc20_query_page_searchable_after_reindex(tmp_path: Path) -> None:
    vault, db, slug = _file_a_query(tmp_path)
    _rebuild_db(db, vault)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        wiki_search.main(["Hermes", "--vaults", VAULT_ID, "--db-path", str(db)])
    hits = json.loads(buf.getvalue())["hits"]
    assert any(h["slug"] == slug and h["type"] == "query" for h in hits)
