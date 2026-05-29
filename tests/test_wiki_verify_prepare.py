"""TASK 008 / bead 008-05 — `wiki-verify-multi prepare` (R-8.1).

Assembles the verification envelope from a filed query page + its cited source
bodies, reading every body via the STORED `pages.file_path` (layout-agnostic,
C-8/NFR-7 — enforced by the grep guard here). No LLM call.
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


def _write(vault: Path, rel: str, fm: str, body: str) -> None:
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\n{fm}\n---\n\n{body}\n", encoding="utf-8")


def _run(argv: list[str]) -> tuple[int, dict]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = wiki_verify_multi.main(argv)
    return code, json.loads(buf.getvalue())


def _seed(tmp_path: Path, cites: str = '["_vault_/foo"]') -> tuple[Path, Path]:
    """A vault with a filed query page (cites: foo) + the foo source, indexed."""
    vault, db = tmp_path / "vault", tmp_path / "g.db"
    _write(vault, "_sources/foo.md",
           "type: summary\ntitle: Foo Source\ndate: 2026-05-29\ntags: [t]",
           "# Foo\n\nHermes routes messages between agents via the bus.")
    _write(vault, "_queries/how-hermes-routes.md",
           "type: query\ntitle: How Hermes routes\ndate: 2026-05-29\n"
           f"tags: [query]\nquestion: How does Hermes route?\ncites: {cites}",
           "# Answer\n\nHermes routes via the bus, per the source.")
    repo = SQLiteRepository(db)
    repo.apply_schema()
    repo.register_vault(Vault(vault_id=VAULT_ID, name="v", root_path=vault,
                              schema_version="5.0",
                              registered_at=datetime(2026, 5, 29)))
    reindex_full(repo, VAULT_ID)
    repo.close()
    return vault, db


def _prepare(vault: Path, db: Path, slug: str = "how-hermes-routes", *extra: str) -> tuple[int, dict]:
    return _run(["prepare", slug, "--vault", VAULT_ID, "--vault-root", str(vault),
                 "--db-path", str(db), *extra])


def test_envelope_happy_path(tmp_path: Path) -> None:
    vault, db = _seed(tmp_path)
    code, env = _prepare(vault, db)
    assert code == 0
    assert env["examined_count"] == 1
    assert env["examined"][0]["slug"] == "foo"
    assert env["examined"][0]["body_excerpt"]  # body read via pages.file_path
    assert len(env["answer_hash"]) == 64
    assert env["verification_slug"] == "verify-how-hermes-routes"  # distinct from query slug (no PK collision)
    assert env["question"] == "How does Hermes route?"
    assert env["is_unchanged"] is False
    assert env["missing_cites"] == []


def test_query_not_found(tmp_path: Path) -> None:
    vault, db = _seed(tmp_path)
    code, env = _prepare(vault, db, "does-not-exist")
    assert code == 2 and env["error"] == "QUERY_NOT_FOUND"


def test_non_query_page_is_not_found(tmp_path: Path) -> None:
    """`prepare` on a concept slug (not type=query) → QUERY_NOT_FOUND."""
    vault, db = _seed(tmp_path)
    code, env = _prepare(vault, db, "foo")  # foo is a summary source, not a query
    assert code == 2 and env["error"] == "QUERY_NOT_FOUND"


def test_no_sources(tmp_path: Path) -> None:
    vault, db = _seed(tmp_path, cites="[]")
    code, env = _prepare(vault, db)
    assert code == 2 and env["error"] == "NO_SOURCES"


def test_is_unchanged_after_record(tmp_path: Path) -> None:
    """Recording the prepare-emitted verify_hash → a re-prepare reports unchanged."""
    vault, db = _seed(tmp_path)
    _code, env = _prepare(vault, db)
    repo = SQLiteRepository(db)
    repo.record_verify_state(VAULT_ID, env["verification_slug"], env["verify_hash"])
    repo.close()
    _code2, env2 = _prepare(vault, db)
    assert env2["is_unchanged"] is True


def test_missing_cite_excluded_and_reported(tmp_path: Path) -> None:
    """A cited slug with no `pages` row is excluded from examined + reported."""
    vault, db = _seed(tmp_path, cites='["_vault_/foo", "_vault_/ghost"]')
    _code, env = _prepare(vault, db)
    assert env["examined_count"] == 1  # only foo
    assert "_vault_/ghost" in env["missing_cites"]


def test_all_cites_missing_is_no_sources(tmp_path: Path) -> None:
    """vdd-multi L-3: non-empty `cites:` but every entry is absent/malformed →
    examined is empty → NO_SOURCES (refuse a vacuous verification), not a pass."""
    vault, db = _seed(tmp_path, cites='["_vault_/ghost1", "_vault_/ghost2"]')
    code, env = _prepare(vault, db)
    assert code == 2 and env["error"] == "NO_SOURCES"


def test_invalid_slug(tmp_path: Path) -> None:
    vault, db = _seed(tmp_path)
    code, env = _prepare(vault, db, "Not A Slug")
    assert code == 2 and env["error"] == "INVALID_SLUG"


def test_grep_guard_no_page_subdir_literal() -> None:
    """C-8/NFR-7 (binding): the skill MUST NOT contain a literal page-subdir
    string — all layout access goes through `pages.file_path` + `layout.*`
    constants. This is the operator-mandated layout-agnostic enforcement."""
    src = Path(wiki_verify_multi.__file__).read_text(encoding="utf-8")
    for literal in ('"_sources"', "'_sources'", '"_concepts"', "'_concepts'",
                    '"_entities"', "'_entities'", '"_queries"', "'_queries'",
                    '"_verifications"', "'_verifications'"):
        assert literal not in src, f"layout-coupling: {literal} in wiki_verify_multi.py"


def test_help_exits_zero(capsys) -> None:
    import pytest
    with pytest.raises(SystemExit) as e:
        wiki_verify_multi.main(["--help"])
    assert e.value.code == 0
