"""TASK 036 / R-15 (Slice A2) — `wiki-health coverage` CLI (read-only, always exit 0)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from scripts.wiki_index.layout_config import resolve_layout_config
from scripts.wiki_index.models import Vault
from scripts.wiki_index.sqlite_repository import SQLiteRepository
from scripts.wiki_skills.wiki_health import main as health_main
from tests._health_fixtures import build_cybos_vault, build_health_vault


def _run(capsys, argv: list[str]) -> tuple[int, dict]:
    rc = health_main(argv)
    out = capsys.readouterr().out.strip().splitlines()[-1]
    return rc, json.loads(out)


def _db(tmp_path: Path) -> str:
    repo, _ = build_health_vault(tmp_path)
    repo.close()  # CLI opens its own connection to the db file
    return str(tmp_path / "h.db")


def test_coverage_all(tmp_path: Path, capsys) -> None:
    db = _db(tmp_path)
    rc, env = _run(capsys, ["coverage", "--vault", "hvault", "--db-path", db])
    assert rc == 0 and env["action"] == "coverage"            # a gap is data → exit 0
    assert env["total_gaps"] == 4
    assert env["by_class"] == {"requirement": 1, "capability": 1, "fact": 2}
    missing = {(g["slug"], g["kind"], g["missing"]) for g in env["gaps"]}
    assert ("req-uncovered", "edge", "implemented-by") in missing
    assert ("cap-orphan", "edge", "implemented-by") in missing
    assert ("fact-nosrc", "field", "source") in missing
    assert ("fact-missing", "field", "source") in missing


def test_coverage_controls_not_gaps(tmp_path: Path, capsys) -> None:
    db = _db(tmp_path)
    _, env = _run(capsys, ["coverage", "--vault", "hvault", "--db-path", db])
    slugs = {g["slug"] for g in env["gaps"]}
    assert "req-covered" not in slugs       # forward implemented-by present
    assert "fact-withsrc" not in slugs      # non-empty source


def test_coverage_class_filter(tmp_path: Path, capsys) -> None:
    db = _db(tmp_path)
    rc, env = _run(capsys, ["coverage", "--vault", "hvault",
                            "--class", "fact", "--db-path", db])
    assert rc == 0
    assert {g["slug"] for g in env["gaps"]} == {"fact-nosrc", "fact-missing"}
    assert env["by_class"] == {"fact": 2}


def test_coverage_invalid_class_no_echo(tmp_path: Path, capsys) -> None:
    db = _db(tmp_path)
    rc, env = _run(capsys, ["coverage", "--vault", "hvault",
                            "--class", "bogus' OR 1=1--", "--db-path", db])
    assert rc == 2 and env["error"] == "INVALID_CLASS"
    assert "bogus" not in json.dumps(env)                      # no echo of the offending value
    assert set(env["valid"]) == {"requirement", "capability", "fact"}


def test_coverage_vault_not_found(tmp_path: Path, capsys) -> None:
    db = _db(tmp_path)
    rc, env = _run(capsys, ["coverage", "--vault", "nope", "--db-path", db])
    assert rc == 6 and env["error"] == "VAULT_NOT_FOUND"


def test_empty_container_source_is_gap(tmp_path: Path) -> None:
    # vdd-multi critic-logic MED: an empty-container source (`source: []`) is "no value" →
    # a gap, like an empty string; a non-empty source is covered.
    repo, root = build_cybos_vault(tmp_path, {
        "facts/f-empty.md": "---\ntype: fact\ntitle: FE\nsource: []\n---\nb\n",
        "facts/f-ok.md": "---\ntype: fact\ntitle: FO\nsource: \"cite\"\n---\nb\n",
    })
    rules = list(resolve_layout_config(root).coverage_rules)
    gaps = {g.page_slug for g in repo.find_coverage_gaps("mini", rules)}
    assert "f-empty" in gaps
    assert "f-ok" not in gaps
    repo.close()


def test_coverage_no_rules_note(tmp_path: Path, capsys) -> None:
    # vdd-multi critic-logic LOW: a layout with no coverage rules (karpathy) yields an
    # empty report WITH an explicit note (not a silent "0 gaps = healthy").
    root = tmp_path / "kvault"
    root.mkdir()  # no WIKI_SCHEMA → defaults to karpathy → no coverage rules
    repo = SQLiteRepository(tmp_path / "kvault.db")
    repo.apply_schema()
    repo.register_vault(Vault(vault_id="kvault", name="kvault", root_path=root,
                              schema_version="2.0", registered_at=datetime(2026, 6, 16)))
    repo.close()
    rc, env = _run(capsys, ["coverage", "--vault", "kvault",
                            "--db-path", str(tmp_path / "kvault.db")])
    assert rc == 0 and env["rules"] == 0 and env["total_gaps"] == 0
    assert "note" in env
