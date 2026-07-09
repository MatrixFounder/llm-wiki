"""TASK 054 / R-19 — formal ontology contract: DAL `find_ontology_violations` +
`wiki-lint` `ontology-violation` category + `wiki-health ontology` subcommand.

A focused cybos vault (build_cybos_vault) exercising each read-side violation family
+ the non-violating controls:
  domain   — risk-bad (`implements` a resolvable req; risk ∉ from) AND risk-orphan
             (`implements` a DANGLING target; domain fires independent of target — the
             critic-logic MAJOR fix).
  range    — dec-badtarget `implements` an incident (incident ∉ to).
  property — dec-badstatus `status: done` (∉ the decision enum).
Controls (never flagged): dec-ok, dec-nostatus, req-target, inc-target, and dec-orphan
(decision ∈ from AND its target is orphan → no domain, no range).

(closed_types yields NO read-side violation — an out-of-roster `$.type` is a hard reindex
SKIP, enforced at index time; see Q-054. A type-less quick-capture also escapes the checks —
test_typeless_note_escapes_checks codifies that known `$.type`-keying limitation.)
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.wiki_index.layout_config import resolve_layout_config
from tests._health_fixtures import build_cybos_vault

_ONT_FILES = {
    # --- violations ---
    "risks/risk-bad.md":
        "---\ntype: risk\ntitle: Risk Bad\nstatus: open\nimplements: [[req-target]]\n---\nb\n",
    "decisions/dec-badtarget.md":
        "---\ntype: decision\ntitle: Dec BadTarget\nstatus: accepted\nimplements: [[inc-target]]\n---\nb\n",
    "decisions/dec-badstatus.md":
        "---\ntype: decision\ntitle: Dec BadStatus\nstatus: done\n---\nb\n",
    # --- controls (never flagged) ---
    "decisions/dec-ok.md":
        "---\ntype: decision\ntitle: Dec OK\nstatus: accepted\nimplements: [[req-target]]\n---\nb\n",
    "decisions/dec-nostatus.md":
        "---\ntype: decision\ntitle: Dec NoStatus\nimplements: [[req-target]]\n---\nb\n",
    "risks/risk-orphan.md":  # risk ∉ from, but target is an orphan → JOIN skips it
        "---\ntype: risk\ntitle: Risk Orphan\nstatus: open\nimplements: [[ghost-req]]\n---\nb\n",
    "decisions/dec-orphan.md":  # edge to an orphan target → skipped
        "---\ntype: decision\ntitle: Dec Orphan\nstatus: accepted\nimplements: [[ghost-req]]\n---\nb\n",
    "requirements/req-target.md":
        "---\ntype: requirement\ntitle: Req Target\nstatus: draft\n---\nb\n",
    "incidents/inc-target.md":
        "---\ntype: incident\ntitle: Inc Target\nstatus: resolved\n---\nb\n",
}


def _build(tmp_path: Path):
    repo, root = build_cybos_vault(tmp_path, _ONT_FILES, vault_id="ontv")
    cfg = resolve_layout_config(root)
    assert cfg.ontology is not None
    return repo, root, cfg


# --- DAL --------------------------------------------------------------------

def test_find_ontology_violations_dal(tmp_path: Path) -> None:
    repo, _root, cfg = _build(tmp_path)
    viols = repo.find_ontology_violations("ontv", cfg.ontology)
    by = {(v.page_slug, v.kind) for v in viols}
    assert by == {
        ("risk-bad", "domain"),
        ("risk-orphan", "domain"),   # domain fires even when the target is dangling (B fix)
        ("dec-badtarget", "range"),
        ("dec-badstatus", "property"),
    }


def test_domain_fires_on_orphan_target(tmp_path: Path) -> None:
    # critic-logic MAJOR: a domain violation is independent of whether the edge target
    # resolves — risk-orphan `implements [[ghost-req]]` (risk ∉ from) is still flagged, and
    # its target_slug is None (dangling). dec-orphan (decision ∈ from) stays unflagged.
    repo, _root, cfg = _build(tmp_path)
    viols = {(v.page_slug, v.kind): v for v in
             repo.find_ontology_violations("ontv", cfg.ontology)}
    orphan_dom = viols[("risk-orphan", "domain")]
    assert orphan_dom.ref == "implements" and orphan_dom.target_slug is None
    assert ("dec-orphan", "domain") not in viols  # decision ∈ from → no domain
    assert ("dec-orphan", "range") not in viols    # orphan target → no range


def test_domain_deduped_multi_target(tmp_path: Path) -> None:
    # critic-logic 1d: a page with the SAME edge to TWO targets is ONE domain finding (the
    # target is irrelevant for domain), not two — so total_violations/by_kind never inflate
    # by target cardinality. (Range/property stay per-instance.)
    files = {
        "risks/risk-multi.md":
            "---\ntype: risk\ntitle: Risk Multi\nstatus: open\n"
            "implements:\n  - \"[[req-a]]\"\n  - \"[[cap-b]]\"\n---\nb\n",
        "requirements/req-a.md": "---\ntype: requirement\ntitle: Req A\nstatus: draft\n---\nb\n",
        "capabilities/cap-b.md": "---\ntype: capability\ntitle: Cap B\nstatus: active\n---\nb\n",
    }
    repo, root = build_cybos_vault(tmp_path, files, vault_id="dedupv")
    cfg = resolve_layout_config(root)
    dom = [v for v in repo.find_ontology_violations("dedupv", cfg.ontology)
           if v.kind == "domain"]
    assert len(dom) == 1
    assert dom[0].page_slug == "risk-multi" and dom[0].target_slug is None


def test_ontology_controls_not_flagged(tmp_path: Path) -> None:
    repo, _root, cfg = _build(tmp_path)
    viols = repo.find_ontology_violations("ontv", cfg.ontology)
    flagged = {v.page_slug for v in viols}
    # controls (valid pages + the decision-with-orphan-target) are disjoint from the hit set
    assert flagged.isdisjoint({
        "dec-ok", "dec-nostatus", "req-target", "inc-target", "dec-orphan",
    })


# A cybos vault authored per templates/page-types/*.md conventions (every edge filled with a
# resolvable, correctly-typed target; every status a template-default). If the cybos `ontology:`
# block is consistent with the templates, this yields ZERO violations — the anchor that would
# have caught the `causes`→execution/pattern range drift (execution/pattern author `caused_by`).
_CONFORMANT = {
    "decisions/dec-1.md": "---\ntype: decision\ntitle: D1\nstatus: accepted\n"
        "implements: [\"[[req-1]]\"]\nsupersedes: [\"[[dec-2]]\"]\ncauses: [\"[[inc-1]]\"]\n"
        "invalidated_by: [\"[[inc-1]]\"]\nactivated_by: [\"[[evt-1]]\"]\n---\nb\n",
    "decisions/dec-2.md": "---\ntype: decision\ntitle: D2\nstatus: superseded\n---\nb\n",
    "requirements/req-1.md": "---\ntype: requirement\ntitle: R1\nstatus: approved\n"
        "implemented_by: [\"[[dec-1]]\"]\nsupersedes: [\"[[req-2]]\"]\n---\nb\n",
    "requirements/req-2.md": "---\ntype: requirement\ntitle: R2\nstatus: draft\n---\nb\n",
    "risks/risk-1.md": "---\ntype: risk\ntitle: RK1\nstatus: open\ncaused_by: [\"[[dec-1]]\"]\n---\nb\n",
    "incidents/inc-1.md": "---\ntype: incident\ntitle: I1\nstatus: resolved\n"
        "caused_by: [\"[[dec-1]]\"]\ninvalidates: [\"[[dec-1]]\"]\n---\nb\n",
    "hypotheses/hyp-1.md": "---\ntype: hypothesis\ntitle: H1\nstatus: testing\n---\nb\n",
    "facts/fact-1.md": "---\ntype: fact\ntitle: F1\nsource: \"https://x\"\n---\nb\n",
    "events/evt-1.md": "---\ntype: event\ntitle: E1\n"
        "activates: [\"[[dec-1]]\"]\ncauses: [\"[[inc-1]]\"]\n---\nb\n",
    "workflows/wf-1.md": "---\ntype: workflow\ntitle: W1\nstatus: active\n"
        "supersedes: [\"[[wf-2]]\"]\nowned_by: [\"[[agt-1]]\"]\nuses: [\"[[tool-1]]\"]\n---\nb\n",
    "workflows/wf-2.md": "---\ntype: workflow\ntitle: W2\nstatus: deprecated\n---\nb\n",
    "agents/agt-1.md": "---\ntype: agent\ntitle: A1\nstatus: active\n"
        "uses: [\"[[tool-1]]\"]\nimplements: [\"[[cap-1]]\"]\nowns: [\"[[wf-1]]\"]\n---\nb\n",
    "tools/tool-1.md": "---\ntype: tool\ntitle: T1\nstatus: active\n"
        "used_by: [\"[[agt-1]]\"]\nimplements: [\"[[cap-1]]\"]\n---\nb\n",
    "capabilities/cap-1.md": "---\ntype: capability\ntitle: C1\nstatus: active\n"
        "implemented_by: [\"[[agt-1]]\"]\n---\nb\n",
    "executions/exec-1.md": "---\ntype: execution\ntitle: X1\nstatus: success\n"
        "caused_by: [\"[[evt-1]]\"]\n---\nb\n",
    "patterns/pat-1.md": "---\ntype: pattern\ntitle: P1\nstatus: active\n"
        "caused_by: [\"[[inc-1]]\"]\n---\nb\n",
}


def test_templates_conform_to_ontology(tmp_path: Path) -> None:
    repo, root = build_cybos_vault(tmp_path, _CONFORMANT, vault_id="conform")
    cfg = resolve_layout_config(root)
    viols = repo.find_ontology_violations("conform", cfg.ontology)
    assert viols == [], f"template-conformant vault flagged: {[(v.page_slug, v.kind, v.detail) for v in viols]}"


def test_typeless_note_escapes_checks(tmp_path: Path) -> None:
    # KNOWN LIMITATION (Q-054): the checks key on frontmatter `$.type`; a quick-capture filed
    # under a typed folder with NO `type:` is indexed (class from the path glob) but has a
    # NULL `$.type`, so it escapes every ontology check — even a bad status. Codified so the
    # behaviour is explicit (mirrors the R-15 drift/coverage `$.type` precedent).
    files = {
        # no `type:` frontmatter → class comes from the `decisions/**` glob; $.type is NULL
        "decisions/quick.md": "---\ntitle: Quick Capture\nstatus: totally-invalid\n---\nb\n",
    }
    repo, root = build_cybos_vault(tmp_path, files, vault_id="tlvault")
    cfg = resolve_layout_config(root)
    viols = repo.find_ontology_violations("tlvault", cfg.ontology)
    assert viols == []  # the invalid status is NOT flagged (no authored $.type)


def test_ontology_violation_details(tmp_path: Path) -> None:
    repo, _root, cfg = _build(tmp_path)
    viols = {(v.page_slug, v.kind): v for v in
             repo.find_ontology_violations("ontv", cfg.ontology)}
    dom = viols[("risk-bad", "domain")]
    assert dom.ref == "implements" and dom.page_class == "risk"
    rng = viols[("dec-badtarget", "range")]
    assert rng.ref == "implements" and rng.target_slug == "inc-target"
    prop = viols[("dec-badstatus", "property")]
    assert prop.ref == "status" and "done" in prop.detail


def test_ontology_off_is_noop(tmp_path: Path) -> None:
    # a karpathy vault (no ontology block) → ontology is None → callers never hit the DAL
    root = tmp_path / "k"
    root.mkdir()
    assert resolve_layout_config(root).ontology is None


# --- wiki-lint ontology-violation category ----------------------------------

def test_lint_reports_ontology_violations(tmp_path: Path) -> None:
    from scripts.wiki_index.lint import check_ontology_violations
    repo, root, cfg = _build(tmp_path)
    advisory = check_ontology_violations(repo, "ontv", root, strict=False, config=cfg)
    strict = check_ontology_violations(repo, "ontv", root, strict=True, config=cfg)
    assert {i.category for i in advisory} == {"ontology-violation"}
    assert len(advisory) == 4
    assert all(i.severity == "warning" for i in advisory)
    assert all(i.severity == "error" for i in strict)


def test_lint_ontology_noop_without_block(tmp_path: Path) -> None:
    import dataclasses
    from scripts.wiki_index.lint import check_ontology_violations
    repo, _r = build_cybos_vault(tmp_path, {}, vault_id="empty")  # cybos, no pages
    cfg = resolve_layout_config(_r)
    cfg_none = dataclasses.replace(cfg, ontology=None)
    assert check_ontology_violations(repo, "empty", _r, strict=True, config=cfg_none) == []


# --- wiki-health ontology subcommand ----------------------------------------

def _run_health(capsys, argv):
    from scripts.wiki_skills import wiki_health
    rc = wiki_health.main(argv)
    out = capsys.readouterr().out
    return rc, json.loads(out)


def test_health_ontology_exit_zero(tmp_path: Path, capsys) -> None:
    repo, _root, _cfg = _build(tmp_path)
    repo.close()
    rc, env = _run_health(capsys, [
        "ontology", "--vault", "ontv", "--db-path", str(tmp_path / "ontv.db")])
    assert rc == 0
    assert env["action"] == "ontology"
    assert env["total_violations"] == 4
    assert env["by_kind"] == {"domain": 2, "range": 1, "property": 1}


def test_health_ontology_vault_not_found(tmp_path: Path, capsys) -> None:
    repo, _root, _cfg = _build(tmp_path)
    repo.close()
    rc, env = _run_health(capsys, [
        "ontology", "--vault", "nope", "--db-path", str(tmp_path / "ontv.db")])
    assert rc == 6 and env["error"] == "VAULT_NOT_FOUND"


def test_health_ontology_class_filter(tmp_path: Path, capsys) -> None:
    repo, _root, _cfg = _build(tmp_path)
    repo.close()
    rc, env = _run_health(capsys, [
        "ontology", "--vault", "ontv", "--class", "risk",
        "--db-path", str(tmp_path / "ontv.db")])
    assert rc == 0
    assert {v["class"] for v in env["violations"]} == {"risk"}
