"""TASK 007 / bead 007-04 — `wiki-query prepare` + shared `_retrieval` helper.

Covers the deterministic retrieval pass (R-6.1): the envelope shape, alias
expansion reuse, the `NO_CONTEXT` grounding refusal (R-6.7-prepare), the
`is_unchanged` short-circuit (R-6.6), and the `project/slug`-sensitive
`question_hash` (Q-A6).
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from scripts.wiki_index.models import Vault
from scripts.wiki_index.reindex import reindex_full
from scripts.wiki_index.sqlite_repository import SQLiteRepository
from scripts.wiki_skills import wiki_query
from scripts.wiki_skills._retrieval import expand_query, fts_quote


def _write(vault: Path, rel: str, fm: str, body: str) -> None:
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\n{fm}\n---\n\n{body}\n", encoding="utf-8")


def _seed(tmp_path: Path) -> tuple[Path, Path]:
    """A registered + indexed vault with one searchable source page."""
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


def _run_prepare(vault: Path, db: Path, question: str, *extra: str) -> tuple[int, dict]:
    """Invoke `prepare` via the public CLI; return (exit_code, parsed_json)."""
    import io
    import contextlib

    buf = io.StringIO()
    argv = ["prepare", question, "--vault", "test-vault",
            "--vault-root", str(vault), "--db-path", str(db), *extra]
    with contextlib.redirect_stdout(buf):
        code = wiki_query.main(argv)
    return code, json.loads(buf.getvalue())


def test_help_exits_zero() -> None:
    with pytest.raises(SystemExit) as e1:
        wiki_query.main(["prepare", "--help"])
    assert e1.value.code == 0
    # no subcommand → argparse error (required=True)
    with pytest.raises(SystemExit) as e2:
        wiki_query.main([])
    assert e2.value.code != 0


def test_prepare_retrieval_envelope(tmp_path: Path) -> None:
    vault, db = _seed(tmp_path)
    code, env = _run_prepare(vault, db, "Hermes routing")
    assert code == 0
    assert env["vault_id"] == "test-vault"
    assert env["retrieved_count"] >= 1
    assert env["query_slug"] == "hermes-routing"
    assert len(env["question_hash"]) == 64
    assert env["is_unchanged"] is False
    h0 = env["hits"][0]
    assert set(h0) == {"vault_id", "slug", "project", "type", "title",
                       "bm25_score", "snippet"}
    assert h0["slug"] == "routing-note"


def test_natural_language_question_retrieves(tmp_path: Path) -> None:
    """dogfood DF-Q1 regression: a real natural-language question (with
    stopwords / question-words) must retrieve via keyword OR-of-terms, NOT fail
    as an implicit-AND phrase. Before the fix this returned 0 hits → NO_CONTEXT."""
    vault, db = _seed(tmp_path)  # body: "Hermes routes messages between trading agents."
    code, env = _run_prepare(vault, db, "How does the Hermes agent route messages?")
    assert code == 0, f"NL question wrongly refused: {env}"
    assert env["retrieved_count"] >= 1
    assert any(h["slug"] == "routing-note" for h in env["hits"])


def test_prepare_no_context_refuses(tmp_path: Path) -> None:
    vault, db = _seed(tmp_path)
    code, env = _run_prepare(vault, db, "quantumchromodynamics")
    assert code == 2
    assert env["error"] == "NO_CONTEXT"


def test_prepare_is_unchanged_short_circuit(tmp_path: Path) -> None:
    vault, db = _seed(tmp_path)
    _code, env1 = _run_prepare(vault, db, "Hermes routing")
    # record the exact hash prepare computed → next prepare reports unchanged
    repo = SQLiteRepository(db)
    repo.record_query_state("test-vault", env1["query_slug"], env1["question_hash"])
    repo.close()
    _code2, env2 = _run_prepare(vault, db, "Hermes routing")
    assert env2["is_unchanged"] is True


def test_prepare_invalid_slug(tmp_path: Path) -> None:
    vault, db = _seed(tmp_path)
    code, env = _run_prepare(vault, db, "Hermes", "--slug", "Not_Kebab")
    assert code == 2
    assert env["error"] == "INVALID_SLUG"


def test_prepare_empty_question(tmp_path: Path) -> None:
    vault, db = _seed(tmp_path)
    code, env = _run_prepare(vault, db, "   ")
    assert code == 2
    assert env["error"] == "INVALID_QUESTION"


def test_derive_query_slug() -> None:
    assert wiki_query._derive_query_slug("How does X work?") == "how-does-x-work"
    assert wiki_query._derive_query_slug("!!!") == "query"  # nothing kebab-able
    long = wiki_query._derive_query_slug("word " * 40)
    assert len(long) <= wiki_query._MAX_SLUG_LEN and not long.endswith("-")


def test_question_hash_sensitivity() -> None:
    """The hash binds question + the ordered retrieved project/slug set (Q-A6):
    stable for identical inputs, different when the hit set differs. Uses a
    lightweight stub since `_question_hash` only reads `h.page.{project,slug}`."""
    from types import SimpleNamespace
    from typing import cast

    from scripts.wiki_index.models import PageHit

    def _hit(slug: str) -> PageHit:
        return cast(PageHit, SimpleNamespace(
            page=SimpleNamespace(project="_vault_", slug=slug)))

    base = wiki_query._question_hash("q", [_hit("a"), _hit("b")])
    assert base == wiki_query._question_hash("q", [_hit("a"), _hit("b")])  # stable
    assert base != wiki_query._question_hash("q", [_hit("a")])  # corpus changed
    assert base != wiki_query._question_hash("q2", [_hit("a"), _hit("b")])  # question changed


def test_shared_retrieval_helpers() -> None:
    """`_retrieval.fts_quote` doubles embedded quotes; `expand_query` is a no-op
    when nothing resolves (the byte-identity guarantee for wiki-search rests on
    these being the same functions both CLIs import)."""
    assert fts_quote('a"b') == '"a""b"'

    class _Repo:
        def list_vaults(self) -> list[object]:
            return []

        def expand_query_aliases(self, vid: str, term: str) -> list[str]:
            return []

    assert expand_query(_Repo(), "term", ["v"]) == "term"
