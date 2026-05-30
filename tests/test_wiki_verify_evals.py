"""TASK 009 / bead 009-01 — well-formedness of the committed `wiki-verify` eval set.

Deterministic, no LLM, no run. Pins the eval set's shape + vocab to the SHIPPED gate
enums (`_VALID_LENSES`/`_SEV_ORDER`) so an eval edit can never drift from the contract
the critics are graded against. Also enforces the C2 data-guarantee: the injection case
carries BOTH a `security` and a `factual` expected finding for the same `injection`
defect (the sanctioned overlap / FAIL-redundancy backstop, plan-review NIT-4).
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts.wiki_skills.wiki_verify_multi import _SEV_ORDER, _VALID_LENSES, _is_fail

_EVALS = Path(__file__).resolve().parents[1] / "skills/wiki-verify/evals/evals.json"
_NAMED = {  # the 7 cases the set MUST contain (id → name); additions allowed (>= 7)
    1: "clean-grounded", 2: "factual-overclaim", 3: "injection",
    4: "logic-only-circular", 5: "omission-only",
    6: "false-positive-guard", 7: "borderline-overclaim",
}


def _load() -> dict:
    return json.loads(_EVALS.read_text(encoding="utf-8"))


def test_evals_json_parses_and_is_a_floor_of_seven() -> None:
    data = _load()
    cases = data["evals"]
    assert len(cases) >= 7, "expected at least the 7 named cases (>= 7, not == 7)"
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids)), "case ids must be unique"


def test_named_cases_present() -> None:
    by_id = {c["id"]: c for c in _load()["evals"]}
    for cid, name in _NAMED.items():
        assert cid in by_id, f"missing required case id {cid} ({name})"
        assert by_id[cid]["name"] == name, f"case {cid} should be '{name}'"


def test_every_case_is_self_contained() -> None:
    for c in _load()["evals"]:
        for k in ("id", "name", "question", "answer", "examined",
                  "injection_class", "expected_findings",
                  "expected_verdict", "expected_exit"):
            assert k in c, f"case {c.get('id')} missing field '{k}'"
        assert isinstance(c["examined"], list) and c["examined"], \
            f"case {c['id']} must examine >=1 source"
        for e in c["examined"]:
            assert {"project", "slug", "body"} <= set(e), \
                f"case {c['id']} examined entry malformed"
        assert c["expected_verdict"] in {"pass", "fail"}
        assert c["expected_exit"] in {0, 6}


def test_vocab_pinned_to_code_enums() -> None:
    """The eval vocab MUST be a subset of the shipped gate enums — drift caught here."""
    for c in _load()["evals"]:
        for f in c["expected_findings"]:
            assert f["lens"] in _VALID_LENSES, \
                f"case {c['id']}: lens '{f['lens']}' not in {_VALID_LENSES}"
            assert f["min_severity"] in _SEV_ORDER, \
                f"case {c['id']}: severity '{f['min_severity']}' not in {set(_SEV_ORDER)}"
        for fb in c.get("forbidden_findings", []):
            assert fb["forbidden_lens"] in _VALID_LENSES


def test_defect_id_lens_pairs_unique_per_case() -> None:
    """A (defect_id, lens) pair is unique within a case — but a defect_id MAY appear
    under >1 lens (that is how the sanctioned C2 overlap is expressed)."""
    for c in _load()["evals"]:
        pairs = [(f["defect_id"], f["lens"]) for f in c["expected_findings"]]
        assert len(pairs) == len(set(pairs)), \
            f"case {c['id']}: duplicate (defect_id, lens) pair"


def test_at_least_one_injection_class_case() -> None:
    assert any(c["injection_class"] for c in _load()["evals"]), \
        "the set must exercise an injection-class case"


def test_injection_case_has_c2_backstop_data_guarantee() -> None:
    """plan-review NIT-4: the injection case (3) must carry BOTH a `security` finding
    AND a `factual` finding (>= high) for the same `injection` defect — so the C2
    adversarial check (drop security → still FAIL via factual) asserts against committed
    data, not a run-time improvisation."""
    case3 = next(c for c in _load()["evals"] if c["id"] == 3)
    assert case3["injection_class"] is True
    inj = [f for f in case3["expected_findings"] if f["defect_id"] == "injection"]
    lenses = {f["lens"] for f in inj}
    assert {"security", "factual"} <= lenses, \
        "injection case must expect BOTH security and factual (the C2 backstop)"
    factual = next(f for f in inj if f["lens"] == "factual")
    assert _SEV_ORDER[factual["min_severity"]] >= _SEV_ORDER["high"], \
        "the factual backstop must be >= high so it independently forces FAIL"


def test_expected_finding_spans_are_resolvable() -> None:
    """Each expected-finding `span` is locatable in the case text so recall is
    satisfiable against real critic output. Present-in-answer defects (hallucination,
    injection, contradiction, overclaim) anchor in the ANSWER; an OMISSION defect
    (completeness) describes missing content, so its span anchors in an EXAMINED
    SOURCE body. The invariant: span ∈ answer OR span ∈ some examined source."""
    for c in _load()["evals"]:
        haystacks = [c["answer"]] + [e["body"] for e in c["examined"]]
        for f in c["expected_findings"]:
            if "span" in f:
                assert any(f["span"] in h for h in haystacks), \
                    f"case {c['id']}: defect '{f['defect_id']}' span not in answer or any source"


def test_expected_verdict_and_exit_consistent_with_is_fail() -> None:
    """vdd-multi MED-3: each case's `expected_verdict` + `expected_exit` MUST equal what
    the SHIPPED `_is_fail` derives from its `expected_findings` (at their `min_severity`
    floors). Pins the fixture-internal invariant so a future edit can't declare a
    self-contradictory case (e.g. `fail` + exit 0, or findings whose severities don't
    derive the stated verdict)."""
    for c in _load()["evals"]:
        findings = [{"lens": f["lens"], "severity": f["min_severity"]}
                    for f in c["expected_findings"]]
        derived_fail = _is_fail(findings, "high")
        assert (c["expected_verdict"] == "fail") == derived_fail, \
            f"case {c['id']}: expected_verdict '{c['expected_verdict']}' != _is_fail({derived_fail})"
        assert c["expected_exit"] == (6 if derived_fail else 0), \
            f"case {c['id']}: expected_exit {c['expected_exit']} inconsistent with the verdict"


def test_forbidden_findings_well_formed_when_present() -> None:
    for c in _load()["evals"]:
        for fb in c.get("forbidden_findings", []):
            assert {"forbidden_lens", "span"} <= set(fb)
            assert fb["span"] in c["answer"], \
                f"case {c['id']}: forbidden span must be in the answer"
