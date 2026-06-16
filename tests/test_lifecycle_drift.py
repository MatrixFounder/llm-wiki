"""TASK 036 / R-15 (Slice A1) — lifecycle-drift: DAL + wiki-lint integration +
the `--strict` CLI gate (the D-036 decision: drift rides wiki-lint and gates --strict)."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.wiki_index.layout_config import resolve_layout_config
from scripts.wiki_index.lint import run_all_checks
from scripts.wiki_skills.wiki_lint import main as lint_main
from tests._health_fixtures import build_cybos_vault, build_health_vault


def test_find_lifecycle_drift_dal(tmp_path: Path) -> None:
    repo, root = build_health_vault(tmp_path)
    rules = list(resolve_layout_config(root).drift_rules)
    hits = repo.find_lifecycle_drift("hvault", rules)
    by_slug = {h.page_slug: h for h in hits}
    # exactly the 4 contradictions, nothing else
    assert set(by_slug) == {"dec-stale", "dec-old2", "dec-voided", "wf-stale"}
    # forward-authored AND inverse-derived superseded-by both caught
    assert by_slug["dec-stale"].edge == "superseded-by"
    assert by_slug["dec-old2"].edge == "superseded-by"   # inverse of dec-new's `supersedes`
    assert by_slug["dec-stale"].status == "accepted"
    assert by_slug["dec-stale"].expected == "status == superseded"
    # invalidated decision still live → forbidden-status branch
    assert by_slug["dec-voided"].edge == "invalidated-by"
    assert "proposed" in by_slug["dec-voided"].expected
    repo.close()


def test_drift_controls_not_flagged(tmp_path: Path) -> None:
    repo, root = build_health_vault(tmp_path)
    rules = list(resolve_layout_config(root).drift_rules)
    slugs = {h.page_slug for h in repo.find_lifecycle_drift("hvault", rules)}
    # correctly-marked, NULL-status, terminal-rejected, edge-less → never drift
    assert slugs.isdisjoint(
        {"dec-new", "dec-correct", "dec-nostatus", "dec-voided-ok", "dec-plain", "wf-new"})
    repo.close()


def test_lint_reports_lifecycle_drift(tmp_path: Path) -> None:
    repo, _ = build_health_vault(tmp_path)
    issues = run_all_checks(repo, vaults=["hvault"])
    drift = [i for i in issues if i.category == "lifecycle-drift"]
    assert len(drift) == 4
    assert all(i.severity == "warning" for i in drift)            # advisory by default
    strict = [i for i in run_all_checks(repo, vaults=["hvault"], strict=True)
              if i.category == "lifecycle-drift"]
    assert len(strict) == 4
    assert all(i.severity == "error" for i in strict)             # escalated under --strict
    repo.close()


def _run_lint(capsys, argv: list[str]) -> tuple[int, dict]:
    rc = lint_main(argv)
    out = capsys.readouterr().out.strip().splitlines()[-1]
    return rc, json.loads(out)


def test_lint_cli_strict_gates_on_drift(tmp_path: Path, capsys) -> None:
    repo, _ = build_health_vault(tmp_path)
    repo.close()  # CLI opens its own connection to the db file
    db = str(tmp_path / "h.db")
    rc, env = _run_lint(capsys, ["--vault", "hvault", "--db-path", db])
    assert rc == 0                                                 # advisory: exit 0
    assert env["by_category"]["lifecycle-drift"] == 4
    rc2, _ = _run_lint(capsys, ["--vault", "hvault", "--strict", "--db-path", db])
    assert rc2 == 1                                                # --strict gates non-zero


def test_list_valued_status_not_drift(tmp_path: Path) -> None:
    # vdd-multi critic-logic MED: a NON-scalar status (`status: [superseded]`) must NOT be
    # phantom-flagged by an expect_status rule (the json_type guard restricts to scalar text).
    repo, root = build_cybos_vault(tmp_path, {
        "decisions/d.md": "---\ntype: decision\ntitle: D\nstatus: [superseded]\nsuperseded_by: [[e]]\n---\nb\n",
        "decisions/e.md": "---\ntype: decision\ntitle: E\nstatus: accepted\n---\nb\n",
    })
    rules = list(resolve_layout_config(root).drift_rules)
    assert repo.find_lifecycle_drift("mini", rules) == []     # non-scalar status → never drift
    repo.close()


def test_drift_exists_uses_refs_index(tmp_path: Path) -> None:
    # vdd-multi critic-performance: the EXISTS correlation on
    # (vault_id, page_slug, page_project) must be an INDEX SEARCH (here the PK covering
    # auto-index), NOT a full per-outer-row SCAN of page_entity_refs (guards a future
    # schema/index regression).
    repo, _ = build_health_vault(tmp_path)
    plan = repo._connect().execute(
        "EXPLAIN QUERY PLAN SELECT p.slug FROM pages p WHERE p.vault_id = ? "
        "AND EXISTS (SELECT 1 FROM page_entity_refs r WHERE r.vault_id = p.vault_id "
        "AND r.page_slug = p.slug AND r.page_project = p.project AND r.ref_type = ?)",
        ["hvault", "superseded-by"]).fetchall()
    text = " ".join(str(row[-1]) for row in plan)
    assert "SEARCH r USING" in text and "SCAN page_entity_refs" not in text
    repo.close()
