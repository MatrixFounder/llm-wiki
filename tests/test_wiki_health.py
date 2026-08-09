"""TASK 036 / R-15 (Slice A2) — `wiki-health coverage` CLI (read-only, always exit 0 on success).

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
    binds to. This is the LIVE-vault state (713 concepts, 0 examined) inside CI.

    The page is filed under `facts/_concepts/` because cybos ships **no `_concepts/**`
    glob** (grepped, not assumed): a top-level `_concepts/x.md` is never indexed, and the
    fixture would then pass over an EMPTY `pages` table — a vacuous test of vacuity. The
    assertion below pins that it is really indexed."""
    repo, _root = build_cybos_vault(tmp_path, {
        "facts/_concepts/some-concept.md":
            "---\ntype: concept\ntitle: Some Concept\n---\nb\n",
    }, vault_id="vacuous")
    assert repo._connect().execute(
        "SELECT COUNT(*) FROM pages WHERE vault_id='vacuous' "
        "AND json_extract(frontmatter_json, '$.type') = 'concept'").fetchone()[0] == 1
    repo.close()
    return str(tmp_path / "vacuous.db")


# --- TC-02-1: typed vault, coverage — denominators present, invariant holds ---

def test_tc_02_1_coverage_denominators_typed(tmp_path: Path, capsys) -> None:
    db = _db(tmp_path)
    rc, env = _run(capsys, ["coverage", "--vault", "hvault", "--db-path", db])
    assert rc == 0                          # ADR-006: exit 0 on SUCCESS (DF-072-2 —
    # the non-zero paths are pinned in tests/test_wiki_health_exit_contract.py)
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
    assert "examined NOTHING" in env["note"]
    # ...and it now NAMES both empty populations rather than asserting a bare adjective.
    assert env["vacuous_populations"] == ["edges_examined", "property_pages_examined"]
    assert "`edges_examined` = 0" in env["note"]
    assert "`property_pages_examined` = 0" in env["note"]
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


# =============================================================================
# 061 FIX-LOOP (vdd-multi) — M5 (the --class gate) + the two LOWs
# =============================================================================

_M5_FILES = {
    # The SAME fixture that proves the bug: `fact` ∉ `causes.from` in cybos.yaml, so this
    # page IS a `domain` violation — and its `page_class` is, BY DEFINITION, a class the
    # declared from/to/property lists do not contain.
    "facts/fact-badcauses.md":
        "---\ntype: fact\ntitle: Fact BadCauses\nsource: \"x\"\ncauses: [[wf-target]]\n---\nb\n",
    "workflows/wf-target.md":
        "---\ntype: workflow\ntitle: WF Target\nstatus: active\n---\nb\n",
}


def test_m5_class_filter_accepts_the_class_the_envelope_just_reported(
        tmp_path: Path, capsys) -> None:
    """M5 — the gate REJECTED THE CLASSES MOST LIKELY TO OFFEND. The valid set was built
    from the DECLARED classes (⋃ edge.from ∪ edge.to ∪ property classes), but a `domain`
    violation's class is by definition NOT in that edge's `from`. So the CLI printed
    `by_class: {"fact": 1}` and then answered `--class fact` with INVALID_CLASS + exit 2 —
    rejecting a class it had named ONE LINE EARLIER, IN THE SAME ENVELOPE."""
    repo, _root = build_cybos_vault(tmp_path, _M5_FILES, vault_id="m5v")
    repo.close()
    db = str(tmp_path / "m5v.db")

    rc, env = _run(capsys, ["ontology", "--vault", "m5v", "--db-path", db])
    assert rc == 0
    # ONE ref row, TWO violations (P-061-A: `fact` ∉ causes.from → domain; `workflow` ∉
    # causes.to → range) — both carry `page_class: fact`, the class the old gate rejected.
    assert env["by_class"] == {"fact": 2}            # the CLI names `fact` itself...
    assert env["by_kind"] == {"domain": 1, "range": 1}
    assert env["class_filter"] is None
    # ...and `fact` really is undeclarable-by-the-old-roster: it appears in NO from/to/
    # property list of cybos.yaml (grepped via the config, not believed).
    cfg = resolve_layout_config(_root)
    assert cfg.ontology is not None
    declared = ({c for e in cfg.ontology.edges for c in (*e.frm, *e.to)}
                | {p.page_class for p in cfg.ontology.properties})
    assert "fact" not in declared                   # the OLD roster would have rejected it
    assert "fact" in cfg.type_mapping               # the NEW roster (the load-gate's own)

    rc, filtered = _run(capsys, ["ontology", "--vault", "m5v", "--class", "fact",
                                 "--db-path", db])
    assert rc == 0                                   # NOT exit 2 any more
    assert filtered["class_filter"] == "fact"
    assert filtered["total_violations"] == 2
    assert {v["slug"] for v in filtered["violations"]} == {"fact-badcauses"}
    # the denominators still describe the WHOLE DAL run (the filter is post-hoc) — which is
    # exactly why `class_filter` is in the envelope (fix-loop NIT).
    assert filtered["edges_examined"] == env["edges_examined"] > 0
    _assert_ontology_invariant(filtered)


def test_m5_a_real_typo_is_still_rejected(tmp_path: Path, capsys) -> None:
    """The gate is WIDENED to the layout's CLOSED type roster, not removed: a class that is
    not a `type_mapping` key at all is still INVALID_CLASS + exit 2, still with no echo of
    the offending value (CWE-209)."""
    repo, _root = build_cybos_vault(tmp_path, _M5_FILES, vault_id="m5typo")
    repo.close()
    rc, err = _run(capsys, ["ontology", "--vault", "m5typo", "--class", "bogus' OR 1=1--",
                            "--db-path", str(tmp_path / "m5typo.db")])
    assert rc == 2 and err["error"] == "INVALID_CLASS"
    assert "bogus" not in json.dumps(err)
    # the advertised roster IS the type_mapping roster — a strict SUPERSET of the old one,
    # so nothing that validated before is rejected now.
    cfg = resolve_layout_config(_root)
    assert cfg.ontology is not None
    declared = ({c for e in cfg.ontology.edges for c in (*e.frm, *e.to)}
                | {p.page_class for p in cfg.ontology.properties})
    assert set(err["valid"]) == set(cfg.type_mapping) > declared


def test_low_declared_but_ruleless_ontology_blames_the_config_not_the_data(
        tmp_path: Path, capsys) -> None:
    """LOW — an `ontology: {closed_types: true}` block with NO edges and NO properties is
    SCHEMA-VALID (both default to `[]`). It used to emit NOTE_ONTOLOGY_VACUOUS, which
    blames the VAULT'S DATA ("no page carries an authored $.type…") when the truth is "you
    declared no rules" — sending the operator to author typed pages that would still be
    examined by nothing. Coverage distinguishes the two precisely; ontology now mirrors it.

    Built END-TO-END through a real `.wiki/layout.yaml` override (edges/properties REPLACE
    as whole lists), not by hand-patching a dataclass — the schema-validity claim is the
    whole point of the finding, so the test must exercise the schema."""
    repo, root = build_cybos_vault(tmp_path, {
        "decisions/d1.md": "---\ntype: decision\ntitle: D1\nstatus: accepted\n---\nb\n",
    }, vault_id="ruleless")
    (root / ".wiki").mkdir(parents=True, exist_ok=True)
    (root / ".wiki" / "layout.yaml").write_text(
        "ontology:\n  closed_types: true\n  edges: []\n  properties: []\n",
        encoding="utf-8")
    repo.close()

    cfg = resolve_layout_config(root)
    assert cfg.ontology is not None                       # the block IS declared...
    assert cfg.ontology.edges == () and cfg.ontology.properties == ()   # ...and rule-less

    rc, env = _run(capsys, ["ontology", "--vault", "ruleless",
                            "--db-path", str(tmp_path / "ruleless.db")])
    assert rc == 0
    assert env["total_violations"] == 0 and env["by_rule"] == []
    assert env["note"] == (
        "an ontology block is configured, but it declares NO edges and NO properties — "
        "there are no rules to examine (this is not a clean bill of health)")
    # the three notes stay three DISTINCT statements — "no block" ≠ "no rules" ≠ "no data"
    assert "NO page carries" not in env["note"]
    assert env["note"] != "no ontology contract configured for this layout"


# =============================================================================
# 061 FIX-LOOP iteration-2 — M-2: `ontology` went SILENT on PARTIAL vacuity
# =============================================================================

def test_m2_partial_vacuity_is_not_silent_the_task_062_trigger(
        tmp_path: Path, capsys) -> None:
    """M-2 — THE ORIGINAL BUG, ONE AUTHORED PAGE AWAY FROM RETURNING.

    The note used to fire only when BOTH denominators were zero:

        elif report.edges_examined == 0 and report.property_pages_examined == 0:

    On the live vault both ARE zero today, so the note fired and the fix looked complete.
    Author ONE typed `decision` page with a `status:` — literally the next planned step
    (TASK 062) — and the state becomes `{edges_examined: 0, property_pages_examined: 1}`:
    the `and` SHORT-CIRCUITS, no note is emitted at all, and the envelope reads
    `total_violations: 0` while all SEVEN edge rules examined nothing. The original false
    green, restored, on the non-gating CLI (exit 0 on success) whose entire purpose is reporting — while
    `wiki-lint`, over the SAME two denominators, correctly refused to print the green.

    MUTATION BAR: restore the `and` and this test fails on the missing `note`."""
    repo, _root = build_cybos_vault(tmp_path, {
        # ONE typed page, a valid status, and NOT ONE declared edge type anywhere.
        "decisions/d1.md":
            "---\ntype: decision\ntitle: D1\nstatus: accepted\n---\nbody\n",
    }, vault_id="partial")
    repo.close()
    rc, env = _run(capsys, ["ontology", "--vault", "partial",
                            "--db-path", str(tmp_path / "partial.db")])
    assert rc == 0                          # exit 0 on success, unchanged
    # THE STATE: partially vacuous — one population empty, the other not.
    assert env["edges_examined"] == 0                # ...so the 7 edge rules judged NOTHING
    assert env["property_pages_examined"] == 1       # ...while the property half DID run
    assert env["total_violations"] == 0              # ...and the old envelope said ONLY this
    # THE FIX: the note fires on the PARTIAL case, and NAMES the empty population.
    assert "note" in env, "partial vacuity went SILENT — the `and` short-circuit is back"
    assert "examined NOTHING" in env["note"]
    assert env["vacuous_populations"] == ["edges_examined"]
    assert "`edges_examined` = 0" in env["note"]
    assert "no page_entity_refs row carries a declared edge type" in env["note"]
    # ...and does NOT libel the population that DID examine rows.
    assert "`property_pages_examined` = 0" not in env["note"]
    _assert_ontology_invariant(env)


def test_m2_wiki_health_and_wiki_lint_agree_on_the_same_two_denominators(
        tmp_path: Path, capsys) -> None:
    """The sibling-surface check. M-2's real indictment was not the `and` — it was that TWO
    surfaces of ONE task, over the SAME two denominators, disagreed, and the WEAKER
    semantics sat on the reporting CLI. Both now derive vacuity from the same
    `*_examined` suffix contract and the same `models.vacuous_rule_kinds`, so they cannot
    drift apart again without this failing."""
    from scripts.wiki_index.lint import derive_vacuous_checks, run_all_checks_report

    repo, _root = build_cybos_vault(tmp_path, {
        "decisions/d1.md":
            "---\ntype: decision\ntitle: D1\nstatus: accepted\n---\nbody\n",
    }, vault_id="agree")
    lint_report = run_all_checks_report(repo, vaults=["agree"])
    repo.close()
    _rc, env = _run(capsys, ["ontology", "--vault", "agree",
                            "--db-path", str(tmp_path / "agree.db")])

    lint_vacuous = {v["population"] for v in derive_vacuous_checks(lint_report.denominators)
                    if v["check"] == "ontology-violation"}
    assert lint_vacuous == {"edges_examined"}            # wiki-lint says: edges examined 0
    assert set(env["vacuous_populations"]) == lint_vacuous   # ...and wiki-health now agrees


def test_m3_BOTH_subcommands_carry_the_vacuity_KEYS_the_contract_promises(
        tmp_path: Path, capsys) -> None:
    """THE SURFACE CENSUS FOR THIS FIX'S OWN NEW KEYS — the step M-3 says the last loop
    skipped, applied here to the keys THIS loop added.

    M-2 put `vacuous_populations` / `vacuous_kinds` on the ONTOLOGY envelope, and the
    LLM-facing contract then told orchestrators that **`total_gaps: 0`** — a *coverage* key
    — is a clean bill of health only when both lists are empty. Coverage emitted NEITHER. A
    reader doing `env.get("vacuous_kinds", [])` gets `[]` and reads the green anyway: a
    contract promising a surface the code does not cover, authored inside the fix for
    exactly that disease. Caught by grepping this fix's own surfaces, not by reasoning.

    Every report exit path of BOTH subcommands must carry both keys — the `note` is derived
    from them, and a key that appears only on some vaults is a KeyError waiting for the
    orchestrator that trusted the doc."""
    db = _db(tmp_path)                       # a typed vault: rules ran on a real population
    untyped = _untyped_db(tmp_path)          # rules configured, population EMPTY
    root = tmp_path / "kvault"               # karpathy: no rules / no ontology block at all
    root.mkdir()
    repo = SQLiteRepository(tmp_path / "kvault.db")
    repo.apply_schema()
    repo.register_vault(Vault(vault_id="kvault", name="kvault", root_path=root,
                              schema_version="2.0", registered_at=datetime(2026, 6, 16)))
    repo.close()
    kdb = str(tmp_path / "kvault.db")

    for sub, vault, db_path in (
            ("coverage", "hvault", db), ("ontology", "hvault", db),
            ("coverage", "vacuous", untyped), ("ontology", "vacuous", untyped),
            ("coverage", "kvault", kdb), ("ontology", "kvault", kdb)):
        _rc, env = _run(capsys, [sub, "--vault", vault, "--db-path", db_path])
        assert "vacuous_populations" in env, f"{sub}/{vault}: the contract's key is MISSING"
        assert "vacuous_kinds" in env, f"{sub}/{vault}: the contract's key is MISSING"
        assert isinstance(env["vacuous_populations"], list)
        assert isinstance(env["vacuous_kinds"], list)
        # ...and the contract's own rule is CHECKABLE from the envelope alone.
        total = env.get("total_gaps", env.get("total_violations"))
        if total == 0 and not env["vacuous_populations"] and not env["vacuous_kinds"]:
            assert "note" not in env         # an unqualified green ⇒ nothing was vacuous

    # the typed vault examined real populations on BOTH subcommands ⇒ genuinely green
    _rc, cov = _run(capsys, ["coverage", "--vault", "hvault", "--db-path", db])
    assert cov["vacuous_populations"] == [] and cov["vacuous_kinds"] == []
    # ...while the untyped one is vacuous on BOTH, and says so on BOTH.
    _rc, cov_v = _run(capsys, ["coverage", "--vault", "vacuous", "--db-path", untyped])
    assert cov_v["vacuous_populations"] == ["pages_examined"] and "note" in cov_v
