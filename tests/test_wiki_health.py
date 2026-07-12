"""TASK 036 / R-15 (Slice A2) — `wiki-health coverage` CLI (read-only, always exit 0).

TASK 061 / R-061-1 (bead 061-02) — the envelope now carries the DENOMINATORS, so
`{"total_gaps": 0}` can no longer be mistaken for a clean bill of health (TC-02-*).
"""

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


# --- TASK 061 (bead 061-02): invariant checkers, read from the JSON ENVELOPE ALONE ---
# (a consumer of the CLI has nothing else; if the invariant is not checkable from the
# envelope, the envelope did not actually report what it examined).

def _assert_coverage_invariant(env: dict) -> None:
    """`∀ coverage rule r: gaps_r ≤ matched_r ≤ pages_examined`.

    NOT asserted: `total_gaps ≤ pages_examined`. That TOTAL form is FALSE on correct
    data — the schema permits two rules on one class (cybos's own `drift_rules` ship
    exactly that for `decision`), so one page can gap under both rules and the total can
    legitimately exceed the population. RTM constraint 3: invariants are PER RULE,
    against that rule's own family denominator.
    """
    for stat in env["by_rule"]:
        for count in stat["findings"].values():
            assert count <= stat["matched"] <= env["pages_examined"], stat


def _assert_ontology_invariant(env: dict) -> None:
    """`∀ edge rule e: domain_e ≤ matched_e AND range_e ≤ matched_e AND matched_e ≤
    edges_examined`; `∀ property rule p: property_p ≤ matched_p ≤ property_pages_examined`.

    NOT asserted: any SUM over kinds (P-061-A) — ONE examined ref row can be BOTH a domain
    and a range violation, so `domain_e + range_e` can exceed `matched_e` on correct data.
    Each rule is bound to its OWN family's denominator: an edge rule against
    `edges_examined`, a property rule against `property_pages_examined` — never one shared
    noun (C6: the two populations are disjoint).
    """
    for stat in env["by_rule"]:
        denom = (env["edges_examined"] if stat["kind"] == "edge"
                 else env["property_pages_examined"])
        for count in stat["findings"].values():
            assert count <= stat["matched"], stat
        assert stat["matched"] <= denom, stat


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
    assert env["note"] == "no coverage rules configured for this layout"
    # TASK 061: the no-RULES note is a DIFFERENT (already-honest) condition from the
    # no-POPULATION note — it must not be replaced by it.
    assert "nothing was examined" not in env["note"]
    assert env["pages_examined"] == 0 and env["by_rule"] == []


# ===========================================================================
# TASK 061 / R-061-1 (bead 061-02) — the envelopes carry the denominators.
# ===========================================================================

def _untyped_db(tmp_path: Path) -> str:
    """A cybos vault (⇒ rules ARE configured and DO run) whose pages carry no rule-bound
    `$.type` — a `concept` page is a real class, but NOT one any coverage/ontology rule
    binds to. This is the LIVE-vault state (713 concepts, 0 examined) inside CI."""
    repo, _root = build_cybos_vault(tmp_path, {
        "notes/untyped.md": "---\ntitle: No Type At All\n---\nbody\n",
        "_concepts/some-concept.md": "---\ntype: concept\ntitle: Some Concept\n---\nb\n",
    }, vault_id="vacuous")
    repo.close()
    return str(tmp_path / "vacuous.db")


# --- TC-02-1: typed vault, coverage — denominators present, invariant holds ---

def test_tc_02_1_coverage_denominators_typed(tmp_path: Path, capsys) -> None:
    db = _db(tmp_path)
    rc, env = _run(capsys, ["coverage", "--vault", "hvault", "--db-path", db])
    assert rc == 0                                    # ADR-006: always exit 0
    # 2 requirements + 1 capability + 3 facts (the classes cybos's coverage_rules bind to)
    assert env["pages_examined"] == 6
    assert {s["class"] for s in env["by_rule"]} == {"requirement", "capability", "fact"}
    assert all("matched" in s and "findings" in s for s in env["by_rule"])
    assert "note" not in env                          # rules ran on a real population
    _assert_coverage_invariant(env)


# --- TC-02-2 (VACUITY): rules configured, population empty ⇒ the note ---------

def test_tc_02_2_coverage_vacuous_note(tmp_path: Path, capsys) -> None:
    rc, env = _run(capsys, ["coverage", "--vault", "vacuous",
                            "--db-path", _untyped_db(tmp_path)])
    assert rc == 0
    assert env["rules"] == 3            # rules ARE configured...
    assert env["total_gaps"] == 0       # ...and the OLD envelope said only this
    assert env["pages_examined"] == 0   # ...while THIS says why: nothing was examined
    assert env["note"] == (
        "coverage rules are configured, but NO page carries an authored $.type in those "
        "classes — nothing was examined (this is not a clean bill of health)")
    # every rule ran and matched nothing — the denominator is not a proxy for "no rules"
    assert [s["matched"] for s in env["by_rule"]] == [0, 0, 0]
    _assert_coverage_invariant(env)


# --- TC-02-3: ontology — TWO denominators, all THREE report exit paths --------

def test_tc_02_3_ontology_denominators_typed(tmp_path: Path, capsys) -> None:
    db = _db(tmp_path)
    rc, env = _run(capsys, ["ontology", "--vault", "hvault", "--db-path", db])
    assert rc == 0
    assert env["edges_examined"] > 0
    assert env["property_pages_examined"] == 14   # decision 8 + incident 1 + workflow 2
    assert {s["kind"] for s in env["by_rule"]} == {"edge", "property"}
    assert "note" not in env
    _assert_ontology_invariant(env)


def test_tc_02_3_ontology_vacuous_note(tmp_path: Path, capsys) -> None:
    rc, env = _run(capsys, ["ontology", "--vault", "vacuous",
                            "--db-path", _untyped_db(tmp_path)])
    assert rc == 0
    assert env["total_violations"] == 0
    assert env["edges_examined"] == 0 and env["property_pages_examined"] == 0
    assert "nothing was examined" in env["note"]
    _assert_ontology_invariant(env)


def test_tc_02_3_ontology_none_early_return_same_keys(tmp_path: Path, capsys) -> None:
    # The `layout.ontology is None` branch is one of the module's THREE report exit paths
    # (`grep -n 'emit(' scripts/wiki_skills/wiki_health.py` → 6 sites; 3 report, 3 error).
    # It must emit the SAME key set as the real report — a consumer must never see a key
    # go missing depending on the vault's config.
    root = tmp_path / "kvault"
    root.mkdir()  # karpathy → layout.ontology is None
    repo = SQLiteRepository(tmp_path / "kvault.db")
    repo.apply_schema()
    repo.register_vault(Vault(vault_id="kvault", name="kvault", root_path=root,
                              schema_version="2.0", registered_at=datetime(2026, 6, 16)))
    repo.close()
    _, early = _run(capsys, ["ontology", "--vault", "kvault",
                             "--db-path", str(tmp_path / "kvault.db")])
    _, real = _run(capsys, ["ontology", "--vault", "vacuous",
                            "--db-path", _untyped_db(tmp_path)])
    assert set(early) == set(real)      # note is present in BOTH (different, honest texts)
    assert early["edges_examined"] == 0 and early["property_pages_examined"] == 0
    assert early["by_rule"] == []
    assert early["note"] == "no ontology contract configured for this layout"
    assert early["note"] != real["note"]   # "no contract" ≠ "contract, empty population"


# --- TC-02-4 (ADDITIVE-ONLY): the pre-061 key set is still a subset ----------

_PRE_061_COVERAGE_KEYS = {"action", "vault", "rules", "total_gaps", "by_class", "gaps"}
_PRE_061_ONTOLOGY_KEYS = {"action", "vault", "total_violations", "by_kind", "by_class",
                          "violations"}


def test_tc_02_4_additive_only_coverage(tmp_path: Path, capsys) -> None:
    db = _db(tmp_path)
    _, env = _run(capsys, ["coverage", "--vault", "hvault", "--db-path", db])
    assert _PRE_061_COVERAGE_KEYS <= set(env)     # nothing renamed, nothing removed
    assert {"pages_examined", "by_rule"} <= set(env)


def test_tc_02_4_additive_only_ontology(tmp_path: Path, capsys) -> None:
    db = _db(tmp_path)
    _, env = _run(capsys, ["ontology", "--vault", "hvault", "--db-path", db])
    assert _PRE_061_ONTOLOGY_KEYS <= set(env)
    assert {"edges_examined", "property_pages_examined", "by_rule"} <= set(env)


# --- TC-02-5: --class still errors 2; the invariant holds on the FILTERED run --

def test_tc_02_5_class_filter_invariant_and_invalid_class(tmp_path: Path, capsys) -> None:
    db = _db(tmp_path)
    # coverage filters the RULES *before* the DAL call ⇒ the denominator scopes to the run
    rc, env = _run(capsys, ["coverage", "--vault", "hvault", "--class", "fact",
                            "--db-path", db])
    assert rc == 0 and env["rules"] == 1
    assert env["pages_examined"] == 3            # the 3 fact pages only (NOT all 6)
    _assert_coverage_invariant(env)
    # ontology filters the VIOLATIONS *after* the call ⇒ the denominators describe the
    # WHOLE run (what the DAL actually examined); by_rule is the DAL's own accounting.
    rc, ont = _run(capsys, ["ontology", "--vault", "hvault", "--class", "decision",
                            "--db-path", db])
    assert rc == 0 and ont["edges_examined"] > 0
    _assert_ontology_invariant(ont)
    # the ERROR envelopes stay error envelopes: exit 2, no denominators (they report a
    # rejected REQUEST, not an examined population — module-docstring emit-census).
    for cmd in ("coverage", "ontology"):
        rc, err = _run(capsys, [cmd, "--vault", "hvault", "--class", "bogus",
                                "--db-path", db])
        assert rc == 2 and err["error"] == "INVALID_CLASS"
        assert "pages_examined" not in err and "edges_examined" not in err
