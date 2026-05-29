"""TASK 008 / bead 008-10 — e2e + compounding + layout-agnostic acceptance.

Drives `wiki_verify_multi.main` (and `wiki_search.main`) on a throwaway vault.
Distinct coverage beyond 008-06/07: UC-25 (a `wiki-search --types verification`
finds the filed verdict — compounding) and UC-28 (a cited source whose
`pages.file_path` is NON-Karpathy is still read by `prepare` — the layout-agnostic
invariant, read via `file_path` not a reconstructed `_sources/<slug>.md`). Verdict
JSON is constructed in-test (no model SDK — Decision-17).
"""
from __future__ import annotations

import contextlib
import io
import json
from datetime import datetime
from pathlib import Path

from scripts.wiki_index.models import Page, Vault
from scripts.wiki_index.reindex import reindex_full
from scripts.wiki_index.sqlite_repository import SQLiteRepository
from scripts.wiki_skills import wiki_search, wiki_verify_multi

VAULT_ID = "test-vault"
QSLUG = "how-hermes-routes"
VSLUG = "verify-how-hermes-routes"


def _write(vault: Path, rel: str, fm: str, body: str) -> None:
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\n{fm}\n---\n\n{body}\n", encoding="utf-8")


def _seed(tmp_path: Path) -> tuple[Path, Path, SQLiteRepository]:
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
                              schema_version="5.0", registered_at=datetime(2026, 5, 29)))
    reindex_full(repo, VAULT_ID)
    return vault, db, repo


def _apply_pass(vault: Path, db: Path) -> tuple[int, dict]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        wiki_verify_multi.main(["prepare", QSLUG, "--vault", VAULT_ID,
                                "--vault-root", str(vault), "--db-path", str(db)])
    prep = json.loads(buf.getvalue())
    (vault / "verdict.json").write_text(json.dumps(
        {"verdict": "pass", "critics": ["factual"],
         "findings": [{"lens": "factual", "severity": "low", "claim": "ok",
                       "source": "_vault_/foo", "note": "supported"}]}), encoding="utf-8")
    buf2 = io.StringIO()
    with contextlib.redirect_stdout(buf2):
        code = wiki_verify_multi.main(
            ["apply", "--vault", VAULT_ID, "--vault-root", str(vault),
             "--db-path", str(db), "--verification-slug", prep["verification_slug"],
             "--query-slug", QSLUG, "--answer-hash", prep["answer_hash"],
             "--verdict-file", str(vault / "verdict.json")])
    return code, json.loads(buf2.getvalue())


def test_uc25_compounding_search_finds_verdict(tmp_path: Path) -> None:
    """A filed verdict page is FTS-searchable and filterable by --types verification."""
    vault, db, repo = _seed(tmp_path)
    repo.close()
    code, _env = _apply_pass(vault, db)
    assert code == 0
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        wiki_search.main(["hermes", "--vaults", VAULT_ID, "--db-path", str(db),
                          "--types", "verification", "--format", "json"])
    hits = json.loads(buf.getvalue())
    slugs = {h["slug"] for h in (hits if isinstance(hits, list) else hits.get("hits", []))}
    assert VSLUG in slugs, f"verdict page not found by --types verification search: {slugs}"


def test_uc28_layout_agnostic_non_karpathy_file_path(tmp_path: Path) -> None:
    """A cited source whose `pages.file_path` is NOT under a Karpathy subdir
    (here `notes/foo2.md`) is still read by `prepare` via the stored file_path —
    proving the read is layout-agnostic, not a reconstructed `_sources/<slug>.md`."""
    vault, db, repo = _seed(tmp_path)
    # a source page indexed with a NON-Karpathy file_path (reindex would never
    # discover notes/; upsert it directly to simulate a non-Karpathy layout).
    (vault / "notes").mkdir(parents=True, exist_ok=True)
    (vault / "notes" / "foo2.md").write_text(
        "---\ntype: summary\ntitle: Foo2\n---\n\n# Foo2\n\nThe bus carries Hermes traffic.\n",
        encoding="utf-8")
    repo.upsert_page(Page(
        vault_id=VAULT_ID, slug="foo2", project="_vault_", type="summary",
        title="Foo2", file_path="notes/foo2.md", date=None,
        last_modified=datetime(2026, 5, 29), file_hash="h",
        frontmatter_json={"type": "summary"}, body_excerpt="bus carries", tags=[]))
    # a query citing the non-Karpathy source
    _write(vault, "_queries/q2.md",
           "type: query\ntitle: Q2\ndate: 2026-05-29\ntags: [query]\n"
           "question: Q2?\ncites: ['_vault_/foo2']", "# Answer\n\nbody.")
    reindex_full(repo, VAULT_ID)  # indexes q2 (foo2 already upserted at notes/)
    repo.upsert_page(Page(  # reindex_full wiped + rebuilt pages → re-add foo2
        vault_id=VAULT_ID, slug="foo2", project="_vault_", type="summary",
        title="Foo2", file_path="notes/foo2.md", date=None,
        last_modified=datetime(2026, 5, 29), file_hash="h",
        frontmatter_json={"type": "summary"}, body_excerpt="bus carries", tags=[]))
    repo.close()

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        wiki_verify_multi.main(["prepare", "q2", "--vault", VAULT_ID,
                                "--vault-root", str(vault), "--db-path", str(db)])
    env = json.loads(buf.getvalue())
    assert env["examined_count"] == 1
    assert env["examined"][0]["slug"] == "foo2"
    assert env["examined"][0]["body_excerpt"], "non-Karpathy source body not read via file_path"


def test_uc23_fail_exit6_over_main(tmp_path: Path) -> None:
    """e2e re-assertion of the FAIL→exit-6 signal over main(argv)."""
    vault, db, repo = _seed(tmp_path)
    repo.close()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        wiki_verify_multi.main(["prepare", QSLUG, "--vault", VAULT_ID,
                                "--vault-root", str(vault), "--db-path", str(db)])
    prep = json.loads(buf.getvalue())
    (vault / "v.json").write_text(json.dumps(
        {"verdict": "fail", "critics": ["security"],
         "findings": [{"lens": "security", "severity": "critical", "claim": "x",
                       "source": "_vault_/foo", "note": "injection"}]}), encoding="utf-8")
    with contextlib.redirect_stdout(io.StringIO()):
        code = wiki_verify_multi.main(
            ["apply", "--vault", VAULT_ID, "--vault-root", str(vault),
             "--db-path", str(db), "--verification-slug", prep["verification_slug"],
             "--query-slug", QSLUG, "--answer-hash", prep["answer_hash"],
             "--verdict-file", str(vault / "v.json")])
    assert code == 6


def test_off_by_default_wiki_query_does_not_invoke_verify() -> None:
    """R-8.10: wiki-verify-multi is off-by-default — `wiki-query` must NOT
    reference / auto-invoke it (it is a separate, deliberate command)."""
    from scripts.wiki_skills import wiki_query
    src = Path(wiki_query.__file__).read_text(encoding="utf-8")
    assert "wiki_verify_multi" not in src and "wiki-verify-multi" not in src


def test_grep_guard_no_page_subdir_literal() -> None:
    """UC-28 (binding) canonical assertion: no PAGE_SUBDIRS literal in the skill."""
    from scripts.wiki_index import layout
    src = Path(wiki_verify_multi.__file__).read_text(encoding="utf-8")
    for sub in layout.PAGE_SUBDIRS:
        assert f'"{sub}"' not in src and f"'{sub}'" not in src, \
            f"layout-coupling: {sub} literal in wiki_verify_multi.py"
