"""TASK 011 — the v4 deep multi-hop extension benchmark (13 cases, 3 chains, 3 domains).

Deterministic guards only (the LLM 4-critic run is recorded under reports/v4/):
- `evals-v4.json` well-formedness + the same invariants the v1/v2/v3 sets hold, for BOTH
  `seeded` and `natural` constructions (vocab pinned to the gate enums; per-case
  `_is_fail(expected) == expected_verdict`; spans resolvable against answer + all examined
  bodies; unique `(defect_id, lens)` pairs).
- TWO v4-specific invariants: the set actually contains DEEP chains (>=4 examined sources),
  and it contains the signature BROKEN-MIDDLE-HOP fail group.
- Reproducibility: `grade_run(evals-v4.json, committed run-outputs) == committed grading`.

v4 is a SEPARATE file; `grade.py` + the committed v1/v2/v3 run-outputs are untouched, so the
v1/v2/v3 reproducibility pins stay byte-identical (the additive-only / non-regression invariant).
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from scripts.wiki_skills.wiki_verify_multi import _SEV_ORDER, _VALID_LENSES, _is_fail

_E = Path(__file__).resolve().parents[1] / "skills/wiki-verify/evals"
_spec = importlib.util.spec_from_file_location("wiki_verify_eval_grade_v4", _E / "grade.py")
assert _spec and _spec.loader
_grade = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_grade)

_VALID_CONSTRUCTIONS = {"seeded", "natural"}


def _bench() -> dict:
    return json.loads((_E / "evals-v4.json").read_text(encoding="utf-8"))


def test_v4_has_13_cases_across_3_domains() -> None:
    cases = _bench()["evals"]
    assert len(cases) == 13
    assert len({c["domain"] for c in cases}) == 3
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids))
    assert all(c["construction"] in _VALID_CONSTRUCTIONS for c in cases)


def test_v4_has_both_constructions() -> None:
    cases = _bench()["evals"]
    assert {c["construction"] for c in cases} == {"seeded", "natural"}
    assert sum(c["construction"] == "natural" for c in cases) >= 3


def test_v4_exercises_deep_chains() -> None:
    # the previously-unexercised path: 4-5-source dependency chains (v3's max was 3).
    cases = _bench()["evals"]
    deep = [c for c in cases if len(c["examined"]) >= 4]
    assert len(deep) >= 5, "v4 must exercise >=4-source deep chains"
    assert max(len(c["examined"]) for c in cases) >= 5, "v4 must include a 5-hop chain"


def test_v4_has_broken_middle_hop_group() -> None:
    # the signature deep-multihop class: correct endpoints, fabricated middle link -> FAIL.
    cases = _bench()["evals"]
    bm = [c for c in cases if "broken-middle" in c["name"]]
    assert len(bm) >= 4, "v4 must contain the broken-middle-hop group"
    for c in bm:
        assert c["expected_verdict"] == "fail" and c["expected_exit"] == 6
        fl = {ef["lens"] for ef in c["expected_findings"]}
        assert "factual" in fl, f"case {c['id']}: broken-middle defect must be factual"


def test_v4_invariants_hold_per_case() -> None:
    for c in _bench()["evals"]:
        bodies = " ".join(e["body"] for e in c["examined"])
        hay = c["answer"] + " " + bodies
        pairs = []
        for ef in c["expected_findings"]:
            assert ef["lens"] in _VALID_LENSES, f"case {c['id']}: bad lens"
            assert ef["min_severity"] in _SEV_ORDER, f"case {c['id']}: bad severity"
            assert ef["span"] in hay, f"case {c['id']}: span not resolvable: {ef['span']!r}"
            # a FAIL-case fabrication span must be ABSENT from every source body (else it is
            # a defensible inference, not a fabrication).
            if c["expected_verdict"] == "fail":
                assert ef["span"] not in bodies, (
                    f"case {c['id']}: fail span present in a source — not a fabrication: {ef['span']!r}")
            pairs.append((ef["defect_id"], ef["lens"]))
        assert len(pairs) == len(set(pairs)), f"case {c['id']}: dup (defect_id, lens)"
        for fb in c["forbidden_findings"]:
            assert fb["span"] in hay, f"case {c['id']}: forbidden span not resolvable: {fb['span']!r}"
        findings = [{"lens": ef["lens"], "severity": ef["min_severity"]} for ef in c["expected_findings"]]
        fail = _is_fail(findings, "high")
        assert (c["expected_verdict"] == "fail") == fail, f"case {c['id']}: verdict vs _is_fail"
        assert c["expected_exit"] == (6 if fail else 0)


def test_v4_vocab_pinned_to_gate() -> None:
    d = _bench()
    assert set(d["lens_vocab"]) == set(_VALID_LENSES)
    assert set(d["severity_vocab"]) == set(_SEV_ORDER)
    assert d["fail_on_default"] == "high"


def _reproduces(run_outputs: str, grading: str) -> None:
    cases = _bench()["evals"]
    raw = json.loads((_E / "reports/v4" / run_outputs).read_text(encoding="utf-8"))
    run = {int(k): v for k, v in raw.items()}
    expected = json.loads((_E / "reports/v4" / grading).read_text(encoding="utf-8"))
    assert _grade.grade_run(cases, run) == expected, f"{grading} is stale vs grade.py"


def test_v4_shipped_grading_reproducible() -> None:
    _reproduces("shipped-run-outputs.json", "shipped-grading.json")
