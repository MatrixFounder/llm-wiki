"""TASK 008 / bead 008-09 — §D8 durability round-trip (UC-26, the binding gate).

strict-TDD. A verdict page filed by `apply` survives a DB drop + rebuild from
Class A markdown alone: rediscovered as `type=verification` (NOT skipped — the
M-1 TYPE_MAPPING guard), its `verifies` ref reconstructed from the `verifies:`
frontmatter (`ref_type='verifies'`, not degraded to `mentioned`, not clobbered),
on BOTH `--full` and `--delta`. The audited query page row also survives (the
PK-collision fix). The SEC-1 re-seed (apply_schema + register_vault after delete)
is mandatory — the `vaults` row is wiped with the DB.
"""
from __future__ import annotations

import contextlib
import io
import json
from datetime import datetime
from pathlib import Path

from scripts.wiki_index.models import Vault
from scripts.wiki_index.reindex import reindex_delta, reindex_full
from scripts.wiki_index.sqlite_repository import SQLiteRepository
from scripts.wiki_skills import wiki_verify_multi

VAULT_ID = "test-vault"
QSLUG = "how-hermes-routes"
VSLUG = "verify-how-hermes-routes"


def _write(vault: Path, rel: str, fm: str, body: str) -> None:
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\n{fm}\n---\n\n{body}\n", encoding="utf-8")


def _seed(tmp_path: Path, registered: datetime = datetime(2026, 5, 29)) -> tuple[Path, Path]:
    vault, db = tmp_path / "vault", tmp_path / "g.db"
    _write(vault, "_sources/foo.md",
           "type: summary\ntitle: Foo\ndate: 2026-05-29\ntags: [t]",
           "# Foo\n\nHermes routes via the bus.")
    _write(vault, f"_queries/{QSLUG}.md",
           "type: query\ntitle: Q\ndate: 2026-05-29\ntags: [query]\n"
           "question: How does Hermes route?\ncites: ['_vault_/foo']",
           "# Answer\n\nHermes routes via the bus.")
    _seed_db(vault, db, registered)
    return vault, db


def _seed_db(vault: Path, db: Path, registered: datetime) -> None:
    repo = SQLiteRepository(db)
    repo.apply_schema()
    repo.register_vault(Vault(vault_id=VAULT_ID, name="v", root_path=vault,
                              schema_version="5.0", registered_at=registered))
    reindex_full(repo, VAULT_ID)
    repo.close()


def _file_verdict(vault: Path, db: Path) -> None:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        wiki_verify_multi.main(["prepare", QSLUG, "--vault", VAULT_ID,
                                "--vault-root", str(vault), "--db-path", str(db)])
    prep = json.loads(buf.getvalue())
    verdict = {"verdict": "pass", "critics": ["factual"],
               "findings": [{"lens": "factual", "severity": "low", "claim": "ok",
                             "source": "_vault_/foo", "note": "supported"}]}
    (vault / "verdict.json").write_text(json.dumps(verdict), encoding="utf-8")
    with contextlib.redirect_stdout(io.StringIO()):
        wiki_verify_multi.main(
            ["apply", "--vault", VAULT_ID, "--vault-root", str(vault),
             "--db-path", str(db), "--verification-slug", prep["verification_slug"],
             "--query-slug", QSLUG, "--answer-hash", prep["answer_hash"],
             "--verdict-file", str(vault / "verdict.json")])


def _drop_db(db: Path) -> None:
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(db) + suffix)
        if p.exists():
            p.unlink()


def _state(db: Path) -> tuple[dict[str, str], set[tuple[str, str, str]], list]:
    repo = SQLiteRepository(db)
    try:
        conn = repo._connect()
        pages = {r["slug"]: r["type"] for r in conn.execute(
            "SELECT slug, type FROM pages WHERE vault_id=?", (VAULT_ID,)).fetchall()}
        refs = {(r["page_slug"], r["entity_slug"], r["ref_type"]) for r in conn.execute(
            "SELECT page_slug, entity_slug, ref_type FROM page_entity_refs "
            "WHERE vault_id=?", (VAULT_ID,)).fetchall()}
        return pages, refs, []
    finally:
        repo.close()


def test_uc26_full_round_trip(tmp_path: Path) -> None:
    vault, db = _seed(tmp_path)
    _file_verdict(vault, db)
    _drop_db(db)
    # SEC-1: re-seed schema + vault (wiped with the DB) BEFORE reindex.
    repo = SQLiteRepository(db)
    repo.apply_schema()
    repo.register_vault(Vault(vault_id=VAULT_ID, name="v", root_path=vault,
                              schema_version="5.0", registered_at=datetime(2026, 5, 29)))
    result = reindex_full(repo, VAULT_ID)
    repo.close()

    pages, refs, _ = _state(db)
    # verdict page rediscovered + indexed (NOT skipped — M-1 TYPE_MAPPING guard)
    assert pages.get(VSLUG) == "verification"
    assert not any(VSLUG in str(s) for s in result.get("skipped", []))
    # verifies ref reconstructed from frontmatter alone, ref_type preserved
    assert (VSLUG, QSLUG, "verifies") in refs
    assert not any(ps == VSLUG and rt == "mentioned" and es == QSLUG
                   for ps, es, rt in refs)  # not degraded to mentioned
    # the audited query page row also survives (PK-collision fix)
    assert pages.get(QSLUG) == "query"


def test_uc26_delta_round_trip(tmp_path: Path) -> None:
    # old registered_at so the file mtime always exceeds the delta cutoff
    vault, db = _seed(tmp_path, registered=datetime(2000, 1, 1))
    _file_verdict(vault, db)
    _drop_db(db)
    repo = SQLiteRepository(db)
    repo.apply_schema()
    repo.register_vault(Vault(vault_id=VAULT_ID, name="v", root_path=vault,
                              schema_version="5.0", registered_at=datetime(2000, 1, 1)))
    reindex_delta(repo, VAULT_ID)
    repo.close()
    _pages, refs, _ = _state(db)
    assert (VSLUG, QSLUG, "verifies") in refs  # delta-symmetry
