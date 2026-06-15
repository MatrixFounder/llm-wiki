"""TASK 032-04 (R-032-5) — wiki-graph CLI (read-only traversal, injection-safe)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.wiki_skills.wiki_graph import main as graph_main
from tests._graph_fixtures import build_graph_vault


def _run(capsys, argv: list[str]) -> tuple[int, dict]:
    rc = graph_main(argv)
    out = capsys.readouterr().out.strip().splitlines()[-1]
    return rc, json.loads(out)


def _db(tmp_path: Path) -> str:
    repo, _ = build_graph_vault(tmp_path)
    repo.close()  # CLI opens its own connection to the db file
    return str(tmp_path / "g.db")


def test_backlinks_kind(tmp_path: Path, capsys) -> None:
    db = _db(tmp_path)
    rc, env = _run(capsys, ["backlinks", "req-1", "--vault", "gvault",
                            "--kind", "implements", "--db-path", db])
    assert rc == 0 and env["action"] == "backlinks"
    assert {b["page_slug"] for b in env["backlinks"]} == {"dec-1"}


def test_neighbors_both(tmp_path: Path, capsys) -> None:
    db = _db(tmp_path)
    rc, env = _run(capsys, ["neighbors", "dec-1", "--vault", "gvault",
                            "--direction", "both", "--db-path", db])
    assert rc == 0
    slugs = {n["entity_slug"] for n in env["neighbors"]} | {n["page_slug"] for n in env["neighbors"]}
    assert {"req-1", "dec-0", "dec-2", "task-1", "inc-1"} <= slugs


def test_chain_supersession(tmp_path: Path, capsys) -> None:
    db = _db(tmp_path)
    rc, env = _run(capsys, ["chain", "dec-2", "--vault", "gvault",
                            "--kind", "supersedes", "--db-path", db])
    assert rc == 0
    assert [(c["slug"], c["depth"]) for c in env["chain"]] == [("dec-1", 1), ("dec-0", 2)]


def test_invalid_kind_no_echo(tmp_path: Path, capsys) -> None:
    db = _db(tmp_path)
    rc, env = _run(capsys, ["backlinks", "x", "--vault", "gvault",
                            "--kind", "bogus' OR 1=1--", "--db-path", db])
    assert rc == 2 and env["error"] == "INVALID_KIND"
    assert "bogus" not in json.dumps(env)  # no echo of the offending value


def test_chain_requires_kind(tmp_path: Path, capsys) -> None:
    db = _db(tmp_path)
    rc, env = _run(capsys, ["chain", "dec-2", "--vault", "gvault", "--db-path", db])
    assert rc == 2 and env["error"] == "MISSING_KIND"


def test_vault_not_found(tmp_path: Path, capsys) -> None:
    db = _db(tmp_path)
    rc, env = _run(capsys, ["backlinks", "x", "--vault", "nope", "--db-path", db])
    assert rc == 6 and env["error"] == "VAULT_NOT_FOUND"
