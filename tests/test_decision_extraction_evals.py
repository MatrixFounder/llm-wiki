"""TASK 063-16 — the `decision-extraction` eval set, GRADED and DUAL-LAYOUT.

★ AN EVAL WHOSE OWN EXPECTED OUTPUT THE RAIL WOULD REFUSE IS WORSE THAN NO EVAL: it
teaches the model a shape the code rejects, and it looks like coverage. So every
`expected.json` is fed through the REAL validators — the same
`validate_candidates_schema` / `validate_ontology` / `validate_refs` that `apply` runs.

★ AND MERELY VALIDATING IS NOT ENOUGH. An eval with no CENSUS stays green while the
extraction silently drops half the protocol's own rows — every page it DID write is
perfectly valid, so no validator complains. (Not hypothetical: the first hand extraction
on a real client protocol dropped 4 of 9 decision rows and 5 of 9 risks.) So each fixture
carries a `grading.json` with the expected class census, the expected edge census, and —
where present — the exact refusal code its `counterexample.json` must trigger.

★★ EVERY FIXTURE RUNS UNDER BOTH SLUG STRATEGIES. The evals used to run on `cybos` alone,
which is `transliterate` — while the operator's LIVE vault is `obsidian-personal`, which
is `preserve-unicode`. The eval set was exercising a slug strategy nobody uses and NOT
exercising the one that ships. That is this project's signature failure mode (one surface
covered, the shipped one not), and it is why fixture 05 exists: `ё`/`е` COLLAPSE under
transliterate and stay DISTINCT under preserve-unicode. Both behaviours are correct; an
eval set on one layout proves nothing about the other.

★ THE FIXTURE POPULATION IS GLOBBED, NEVER HARDCODED. A `range(1, 10)` here is how
fixture #10 gets silently skipped.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts.wiki_index.factory import make_repo
from scripts.wiki_index.layout_config import (
    LayoutConfig,
    _apply_slug_strategy,
    load_layout_config,
)
from scripts.wiki_index.models import Vault
from scripts.wiki_index.reindex import reindex_full
from scripts.wiki_index.sqlite_repository import SQLiteRepository
from scripts.wiki_skills.wiki_extract_decisions import _ontology_contract, main
from scripts.wiki_skills.wiki_extract_decisions._db import (
    load_resolvable_targets,
    resolve_target_classes,
)
from scripts.wiki_skills.wiki_extract_decisions._errors import ExtractionParseError
from scripts.wiki_skills.wiki_extract_decisions._pages import render_page
from scripts.wiki_skills.wiki_extract_decisions._validation import (
    check_in_batch_collisions,
    derive_slugs,
    validate_candidates_schema,
    validate_ontology,
    validate_refs,
)

SKILL_DIR = Path(__file__).resolve().parents[1] / "skills" / "decision-extraction"
EVALS = SKILL_DIR / "evals"
ROSTER = ("decision", "requirement", "risk")
VAULT_ID = "eval-vault"

# ★ GLOBBED. A fixture added later is graded automatically.
FIXTURES = sorted(d for d in EVALS.iterdir() if d.is_dir())

# ★ THE TWO SLUG STRATEGIES THAT ACTUALLY SHIP.
#   cybos      → transliterate     (the typed-knowledge grammar)
#   para-typed → preserve-unicode  (the OPERATOR'S LIVE VAULT)
_TYPED_CLASSES = {
    "decision": {"db_type": "research", "tag": "decision"},
    "requirement": {"db_type": "brief", "tag": "requirement"},
    "risk": {"db_type": "research", "tag": "risk"},
}
LAYOUTS = ("cybos", "para-typed")


def _ONTOLOGY_CLASSES(cfg: LayoutConfig) -> set[str]:
    """Every class the ontology NAMES — the population `type_mapping` must cover, read
    from the ontology itself rather than counted by hand."""
    assert cfg.ontology is not None
    return ({c for e in cfg.ontology.edges for c in (*e.frm, *e.to)}
            | {p.page_class for p in cfg.ontology.properties})


def _para_typed_override() -> dict[str, Any]:
    """★ `para-typed` MUST BE FAITHFUL TO THE OPERATOR'S LIVE VAULT — and the first
    version of it was NOT.

    It carried `type_mapping` alone. Stock `obsidian-personal` declares NO `ontology:`
    and NO `drift_rules`, so the fixture's G1 was VACUOUS: an invented `mitigates` edge
    sailed straight through, and the counterexample that exists to prove `mitigates` is
    refused proved nothing on the very layout the operator runs.

    A fixture calling itself "the operator's live vault" while missing the thing that
    MAKES that vault typed is this project's signature failure mode, one more time. The
    real `.wiki/layout.yaml` carries `ontology` (7 edges, 11 properties) + 3
    `drift_rules` — so this borrows them FROM `cybos`, which is exactly what the operator
    did, rather than restating them as a literal that would drift.
    """
    cybos = load_layout_config(Path("/nonexistent"), {"layout": "cybos"})
    assert cybos.ontology is not None
    # ★ THE FULL TYPED VOCABULARY, not just the roster. The ontology's load-gate requires
    # every class an edge NAMES to be a `type_mapping` key — `implements.from` includes
    # `task`, `agent`, `tool` — so a 3-class override cannot carry this ontology at all.
    # The operator's live `.wiki/layout.yaml` maps SIXTEEN classes for exactly this
    # reason. Borrowed from cybos rather than restated, so it cannot drift.
    named = _ONTOLOGY_CLASSES(cybos)
    type_mapping = {
        cls: {"db_type": db, "tag": tag}          # LayoutConfig stores it as a tuple
        for cls, (db, tag) in cybos.type_mapping.items() if cls in named
    }
    return {
        "type_mapping": type_mapping,
        "ontology": {
            "closed_types": cybos.ontology.closed_types,
            "edges": [{"edge": e.edge, "from": list(e.frm), "to": list(e.to)}
                      for e in cybos.ontology.edges],
            "properties": [{"class": p.page_class, "field": p.field,
                            "enum": list(p.enum)}
                           for p in cybos.ontology.properties],
        },
        "drift_rules": [
            {k: v for k, v in (
                ("class", r.page_class), ("edge", r.edge),
                ("expect_status", r.expect_status),
                ("forbid_status", list(r.forbid_status) if r.forbid_status else None),
            ) if v is not None}
            for r in cybos.drift_rules
        ],
    }


def _config_for(layout: str, root: Path) -> LayoutConfig:
    if layout != "para-typed":
        return load_layout_config(root, {"layout": layout})
    (root / ".wiki").mkdir(parents=True, exist_ok=True)
    (root / ".wiki" / "layout.yaml").write_text(
        yaml.safe_dump(_para_typed_override(), allow_unicode=True), encoding="utf-8")
    return load_layout_config(
        root, {"layout": "obsidian-personal", "layout_config": ".wiki/layout.yaml"})


def _vault(root: Path, db: Path, layout: str) -> LayoutConfig:
    """A vault on `layout`, carrying the slugs the fixtures link to."""
    root.mkdir(parents=True, exist_ok=True)
    base = "obsidian-personal" if layout == "para-typed" else layout
    (root / "WIKI_SCHEMA.md").write_text(
        f"---\nvault_id: {VAULT_ID}\nlanguage: ru\nlayout: {base}\n"
        + ("layout_config: .wiki/layout.yaml\n" if layout == "para-typed" else "")
        + "---\n", encoding="utf-8")
    config = _config_for(layout, root)

    # the pre-existing supersede/ref target used by fixtures 03 and 04
    d = root / ("decisions" if layout == "cybos" else "06 - BD/decisions")
    d.mkdir(parents=True, exist_ok=True)
    (d / "dec-ocheredi.md").write_text(
        "---\ntype: decision\nslug: dec-ocheredi\nstatus: accepted\n"
        "title: Использовать очереди\n---\n# Очереди\n", encoding="utf-8")

    r = SQLiteRepository(db)
    r.apply_schema()
    r.register_vault(Vault(vault_id=VAULT_ID, name=VAULT_ID, root_path=root,
                           schema_version="7.0", registered_at=datetime(2026, 7, 14)))
    r.close()
    repo = make_repo({"vault_id": VAULT_ID, "db_path": str(db),
                      "vault_root": str(root)})
    try:
        reindex_full(repo, VAULT_ID)
    finally:
        repo.close()
    return config


def _resolve_edge_targets(
    candidates: list[dict[str, Any]], config: LayoutConfig
) -> list[dict[str, Any]]:
    """★ EDGE TARGETS IN THE FIXTURES ARE **TITLES**, NOT SLUGS — because a slug is
    LAYOUT-DEPENDENT and a fixture file is not.

    An in-batch title is slugified with the layout's OWN strategy; anything else (an
    existing page's slug, e.g. `dec-ocheredi`) passes through verbatim. That is exactly
    what the REASON step does with `prepare`'s contract: it is handed the strategy and
    the existing slugs, and derives the rest."""
    by_title = {str(c["title"]): _apply_slug_strategy(
        str(c["title"]), config.slug_strategy) for c in candidates}
    out = []
    for cand in candidates:
        c = dict(cand)
        if c.get("edges"):
            c["edges"] = {
                edge: [by_title.get(t, t) for t in targets]
                for edge, targets in c["edges"].items()
            }
        out.append(c)
    return out


def _validate(
    candidates: list[dict[str, Any]], fixture: Path, vault: Path, db: Path,
    config: LayoutConfig,
) -> tuple[list[str], int]:
    """Run the REAL validators, in the REAL order `apply` runs them."""
    body = (fixture / "input.md").read_text(encoding="utf-8")
    # ★ ORDER: titles → slugs BEFORE the schema pass. The schema is what REJECTS a
    # non-slug edge target (the traversal gate), so an unresolved title would be refused
    # as an attack rather than resolved as a reference. In the real rail the REASON step
    # has already done this — it is handed `slug_strategy` in the contract.
    candidates = _resolve_edge_targets(candidates, config)
    kept = validate_candidates_schema(candidates, source_body=body, roster=ROSTER)
    if not kept:
        return [], 0
    slugs = derive_slugs(kept, config)
    check_in_batch_collisions(kept, slugs)          # ← fixture 05 lands here

    repo = make_repo({"vault_id": VAULT_ID, "db_path": str(db),
                      "vault_root": str(vault)})
    try:
        targets = sorted({t for c in kept
                          for ts in (c.get("edges") or {}).values() for t in ts})
        db_classes = resolve_target_classes(repo, VAULT_ID, targets)
        resolvable = load_resolvable_targets(repo, VAULT_ID) | set(slugs)
    finally:
        repo.close()

    validate_ontology(
        kept, ontology=_ontology_contract(config, ROSTER),
        batch_classes={s: str(c["class"]) for c, s in zip(kept, slugs)},
        db_classes=db_classes)
    rendered = [
        render_page(c, slug=s, vault_id=VAULT_ID, source_slug="input",
                    today=date(2026, 7, 14), source_indexable=False)
        for c, s in zip(kept, slugs)
    ]
    links = validate_refs(rendered, config=config, resolvable=resolvable)
    return slugs, links


def _grading(fixture: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(
        (fixture / "grading.json").read_text(encoding="utf-8"))
    return data


# --------------------------------------------------------------------------- #
# the census — a glob that matched nothing reports as a pass
# --------------------------------------------------------------------------- #


def test_the_eval_set_is_COMPLETE_and_every_fixture_is_GRADED() -> None:
    """A suite of zero tests reports green, so the population is asserted first.

    And every fixture must be GRADED — an ungraded fixture is a fixture that passes
    while the extraction drops half the protocol."""
    assert len(FIXTURES) >= 9, f"the eval glob found {[f.name for f in FIXTURES]}"
    for f in FIXTURES:
        assert (f / "input.md").is_file(), f"{f.name}: no input.md"
        assert (f / "expected.json").is_file(), f"{f.name}: no expected.json"
        assert (f / "grading.json").is_file(), (
            f"{f.name}: NO grading.json — an ungraded fixture validates the shape and "
            f"misses the census, which is exactly how a half-dropped extraction stays "
            f"green")
        why = _grading(f).get("why", "")
        assert len(why) > 80, (
            f"{f.name}: `why` must state the FAILURE MODE this fixture guards. A "
            f"fixture whose reason is not recorded is a fixture that gets deleted.")

    names = {f.name for f in FIXTURES}
    assert any(n.startswith("02-") for n in names), "the NEGATIVE fixture is missing"
    assert any("collision" in n for n in names), (
        "the SLUG-COLLISION fixture is missing — it is the only one that proves the "
        "gate is LAYOUT-DEPENDENT")
    assert any("causes" in n for n in names), (
        "the decision→causes→risk fixture is missing — that edge was forgotten on the "
        "first live run and produced a half-empty graph")


def test_the_two_slug_strategies_are_the_ones_that_actually_SHIP(
    tmp_path: Path,
) -> None:
    """★ The evals used to run on `cybos` ALONE — which is `transliterate`, while the
    operator's LIVE vault is `preserve-unicode`. The set was exercising a strategy nobody
    uses and NOT exercising the one that ships.

    Pinned so it cannot silently regress: the two layouts under test must have DIFFERENT
    slug strategies, or the dual-layout run is theatre."""
    strategies = {
        layout: _config_for(layout, tmp_path / layout).slug_strategy
        for layout in LAYOUTS
    }
    assert strategies == {"cybos": "transliterate",
                          "para-typed": "preserve-unicode"}, strategies


# --------------------------------------------------------------------------- #
# ★ the graded run — every fixture, both layouts
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("layout", LAYOUTS)
@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda f: f.name)
def test_expected_output_PASSES_and_MATCHES_ITS_GRADING(
    fixture: Path, layout: str, tmp_path: Path
) -> None:
    """The expected extraction must (a) survive the real validators and (b) match the
    class + edge census `grading.json` declares.

    (b) is the half that matters. Validation alone stays green while an extraction
    silently drops half the protocol's own rows — every page it wrote is valid."""
    grading = _grading(fixture)
    if layout not in grading.get("layouts", list(LAYOUTS)):
        pytest.skip(f"{fixture.name} declares it does not apply to {layout}")

    db = tmp_path / "x.db"
    config = _vault(tmp_path / "v", db, layout)
    candidates = json.loads((fixture / "expected.json").read_text(encoding="utf-8"))

    slugs, _links = _validate(candidates, fixture, tmp_path / "v", db, config)

    if grading.get("empty_is_success"):
        assert candidates == [], f"{fixture.name} is the NEGATIVE fixture; expected []"
        assert slugs == []
        return

    census: dict[str, int] = {}
    for c in candidates:
        census[str(c["class"])] = census.get(str(c["class"]), 0) + 1
    assert census == grading["expect"], (
        f"{fixture.name}: class census {census} != graded {grading['expect']}")

    edges: dict[str, int] = {}
    for c in candidates:
        for edge, targets in (c.get("edges") or {}).items():
            edges[edge] = edges.get(edge, 0) + len(targets)
    assert edges == grading.get("edges", {}), (
        f"{fixture.name}: edge census {edges} != graded {grading.get('edges', {})}")


@pytest.mark.parametrize("layout", LAYOUTS)
@pytest.mark.parametrize(
    "fixture", [f for f in FIXTURES if (f / "counterexample.json").is_file()],
    ids=lambda f: f.name)
def test_the_COUNTEREXAMPLE_is_REFUSED_with_the_GRADED_code(
    fixture: Path, layout: str, tmp_path: Path
) -> None:
    """★ A SKILL rule with no failing case is a SKILL rule that rots.

    Each counterexample is the WRONG extraction, and `grading.json` names the exact code
    the rail must refuse it with. `refused_with` is asserted — not merely "it raised":
    a counterexample refused for the WRONG reason would pass a laxer test while proving
    nothing about the rule it is supposed to demonstrate.

    ★ Fixture 05 is the interesting one: its counterexample is REFUSED on `cybos`
    (transliterate collapses `ё`/`е` onto one slug) and ACCEPTED on `para-typed`
    (preserve-unicode keeps them distinct). BOTH are correct. `accepted_on` is how the
    grading says so.
    """
    grading = _grading(fixture)
    spec = grading["counterexample"]
    db = tmp_path / "x.db"
    config = _vault(tmp_path / "v", db, layout)
    bad = json.loads((fixture / "counterexample.json").read_text(encoding="utf-8"))

    if layout in spec.get("accepted_on", []):
        # ...and it must actually be ACCEPTED here — asserting only the refusal half
        # would let a rail that refuses EVERYTHING pass this test.
        _validate(bad, fixture, tmp_path / "v", db, config)
        return

    if layout not in spec.get("on_layouts", list(LAYOUTS)):
        pytest.skip(f"{fixture.name} counterexample not graded for {layout}")

    with pytest.raises(ExtractionParseError) as exc:
        _validate(bad, fixture, tmp_path / "v", db, config)
    assert exc.value.error == spec["refused_with"], (
        f"{fixture.name} on {layout}: refused with {exc.value.error}, graded "
        f"{spec['refused_with']} — a counterexample refused for the WRONG reason "
        f"proves nothing about the rule it demonstrates")


def test_the_CYRILLIC_COLLISION_is_REAL_and_LAYOUT_DEPENDENT(tmp_path: Path) -> None:
    """★★ THE MEASUREMENT BEHIND FIXTURE 05, AND BEHIND THE WHOLE LANGUAGE DECISION.

    Real Russian protocols spell `ё` and `е` inconsistently IN THE SAME DOCUMENT.
    `Критерии приёмки` and `Критерии приемки` are DIFFERENT requirements — and under
    `transliterate` they become ONE SLUG. The second page silently OVERWRITES the first:
    one file, one DB row, one requirement gone, and ZERO lint issues, because the file
    that survives is perfectly valid.

    This is measured here rather than asserted in a README, and it is the reason the eval
    inputs are RUSSIAN: an English fixture cannot produce this failure at all.
    """
    a, b = "Критерии приёмки", "Критерии приемки"
    assert a != b
    assert _apply_slug_strategy(a, "transliterate") == \
           _apply_slug_strategy(b, "transliterate"), (
        "the transliterate strategy no longer collapses ё/е — fixture 05's whole "
        "premise is gone and its grading must be revisited")
    assert _apply_slug_strategy(a, "preserve-unicode") != \
           _apply_slug_strategy(b, "preserve-unicode")


# --------------------------------------------------------------------------- #
# the SKILL's rules, each gated
# --------------------------------------------------------------------------- #


def test_the_NEGATIVE_fixture_is_a_SUCCESS_end_to_end(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Through the actual CLI, not just the validators: `[]` ⇒ exit 0, `no_candidates`.

    MUT: `CANDIDATE_COUNT_MIN = 1` ⇒ RED.
    """
    fixture = EVALS / "02-deferred-no-decisions"
    db = tmp_path / "x.db"
    v = tmp_path / "v"
    _vault(v, db, "cybos")
    (v / "meetings").mkdir(exist_ok=True)
    (v / "meetings" / "m1.md").write_text(
        (fixture / "input.md").read_text(encoding="utf-8"), encoding="utf-8")

    code = main(["prepare", "--vault", VAULT_ID, "--vault-root", str(v),
                 "--source-page", "meetings/m1.md", "--db-path", str(db)])
    prep = json.loads(capsys.readouterr().out.strip())
    assert code == 0

    cands = tmp_path / "c.json"
    cands.write_text("[]", encoding="utf-8")
    code = main(["apply", "--vault", VAULT_ID, "--vault-root", str(v),
                 "--source-page", "meetings/m1.md",
                 "--source-hash", prep["source_hash"],
                 "--candidates-file", str(cands), "--db-path", str(db)])
    env = json.loads(capsys.readouterr().out.strip())
    assert code == 0
    assert env["action"] == "no_candidates"


def test_SKILL_md_documents_the_rules_the_fixtures_demonstrate() -> None:
    """Doc and fixture must agree. A rule taught but never demonstrated rots; a rule
    demonstrated but never taught is a trap the model walks into every time."""
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    assert "BARE IDs IN PROSE CAN BE REFS" in text and "DEC-004" in text  # 04
    assert "bare_ids_are_refs" in text          # ...and it is LAYOUT-DEPENDENT
    assert "AN EMPTY EXTRACTION IS A SUCCESS" in text                   # 02
    assert "OPEN COMMITMENT IS DATA" in text                            # 07
    assert "There is no `mitigates`" in text                            # 08
    assert "IN_BATCH_SLUG_COLLISION" in text                            # 05
    assert "anthropic" not in text.lower()      # a CONTRACT, not a call


def test_SKILL_md_teaches_the_EDGE_procedure_and_it_matches_the_ONTOLOGY() -> None:
    """★ THE EDGE GUIDANCE, GATED AGAINST THE REAL ONTOLOGY.

    The first live run produced 28 faithful pages and 4 edges — a LIST, not a graph. Root
    cause, found by DERIVING the legal edge set instead of assuming it: `decision
    --causes--> risk` («what risk does this decision CREATE?») was never even considered.

    So the SKILL must teach EVERY edge the roster can legally author. A doc that taught a
    FORBIDDEN edge would be worse than no doc; one that OMITS a legal edge is how the
    graph stays thin — and neither failure is visible without re-deriving the set here.
    """
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    cfg = load_layout_config(Path("/nonexistent"), {"layout": "cybos"})
    assert cfg.ontology is not None

    roster = set(ROSTER)
    legal = {e.edge for e in cfg.ontology.edges
             if (roster & set(e.frm)) and (roster & set(e.to))}
    for edge in legal:
        assert f"`{edge}`" in text, (
            f"the ontology lets a {ROSTER} page author `{edge}`, and the SKILL never "
            f"mentions it — that edge will simply never be authored")

    assert "decision → risk" in text and "CREATE" in text
    assert "mitigates" not in {e.edge for e in cfg.ontology.edges}
    assert "requirement` authors almost NO edges" in text
    assert "requirement" not in {
        f for e in cfg.ontology.edges if e.edge == "implements" for f in e.frm}, (
        "the ontology changed: a requirement can now author `implements`, so the "
        "SKILL's direction rule is now WRONG")


@pytest.mark.parametrize("layout", LAYOUTS)
def test_BOTH_layouts_are_TYPED_and_NON_VACUOUS(tmp_path: Path, layout: str) -> None:
    """★ THE FIXTURE MUST BE FAITHFUL, OR THE COUNTEREXAMPLES PROVE NOTHING.

    `para-typed`'s first version carried `type_mapping` alone — and stock
    `obsidian-personal` declares NO `ontology:`, so G1 there was VACUOUS. An invented
    `mitigates` edge sailed straight through, and fixture 08 (which exists to prove
    `mitigates` is refused) was green on the very layout the operator runs.

    A fixture that calls itself "the operator's live vault" while missing the thing that
    MAKES that vault typed is a check that examined nothing, reporting green.

    So: both layouts under test must declare a NON-EMPTY ontology, or the whole graded
    run is theatre.
    """
    config = _config_for(layout, tmp_path / layout)
    assert config.ontology is not None, (
        f"{layout} declares NO ontology — G1 is vacuous there and every "
        f"ONTOLOGY_VIOLATION counterexample passes for the wrong reason")
    assert len(config.ontology.edges) >= 5
    assert len(config.ontology.properties) >= 3
    assert config.drift_rules, f"{layout} has no drift_rules — G3 cannot fire"
    assert set(ROSTER) <= set(config.type_mapping)
