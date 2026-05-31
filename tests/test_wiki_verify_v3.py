"""TASK 010 — the v3 adversarial-reasoning extension benchmark (22 cases, 6 domains).

Deterministic guards only (the LLM 4-critic run itself is recorded under reports/v3/):
- `evals-v3.json` well-formedness + the same invariants the v1/v2 sets must hold, for
  BOTH `seeded` and `natural` constructions (vocab pinned to the gate enums; per-case
  `_is_fail(expected) == expected_verdict`; spans resolvable against answer + all examined
  bodies; unique `(defect_id, lens)` pairs).
- Coverage of the four NEW defect classes v2 omitted: temporal, negation/polarity-flip,
  multi-document (>=2 examined sources: composition + cross-source conflict), entity-confusion.
- Reproducibility: `grade_run(evals-v3.json, committed run-outputs) == committed grading`
  for the shipped-prompt run — so the benchmark's headline numbers can't silently drift
  from `grade.py`.

v3 is a SEPARATE file; `grade.py` + the committed v1/v2 run-outputs are untouched, so the
v1/v2 reproducibility pins stay byte-identical (the additive-only / non-regression invariant).
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from scripts.wiki_skills.wiki_verify_multi import _SEV_ORDER, _VALID_LENSES, _is_fail

_E = Path(__file__).resolve().parents[1] / "skills/wiki-verify/evals"
_spec = importlib.util.spec_from_file_location("wiki_verify_eval_grade_v3", _E / "grade.py")
assert _spec and _spec.loader
_grade = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_grade)

_VALID_CONSTRUCTIONS = {"seeded", "natural"}


def _bench() -> dict:
    return json.loads((_E / "evals-v3.json").read_text(encoding="utf-8"))


def test_v3_has_22_cases_across_6_domains() -> None:
    cases = _bench()["evals"]
    assert len(cases) == 22
    assert len({c["domain"] for c in cases}) == 6
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids))
    assert all(c["construction"] in _VALID_CONSTRUCTIONS for c in cases)


def test_v3_has_both_constructions() -> None:
    cases = _bench()["evals"]
    constructions = {c["construction"] for c in cases}
    assert constructions == {"seeded", "natural"}, "v3 must mix seeded + natural"
    assert sum(c["construction"] == "natural" for c in cases) >= 4


def test_v3_exercises_multi_source_grounding() -> None:
    # the previously-unexercised path: at least some cases supply >=2 examined sources.
    cases = _bench()["evals"]
    multi = [c for c in cases if len(c["examined"]) >= 2]
    assert len(multi) >= 6, "multi-document group must exercise >=2 examined sources"


def test_v3_invariants_hold_per_case() -> None:
    for c in _bench()["evals"]:
        hay = c["answer"] + " " + " ".join(e["body"] for e in c["examined"])
        pairs = []
        for f in c["expected_findings"]:
            assert f["lens"] in _VALID_LENSES, f"case {c['id']}: bad lens {f['lens']}"
            assert f["min_severity"] in _SEV_ORDER, f"case {c['id']}: bad severity"
            assert f["span"] in hay, f"case {c['id']}: span not resolvable: {f['span']!r}"
            pairs.append((f["defect_id"], f["lens"]))
        assert len(pairs) == len(set(pairs)), f"case {c['id']}: dup (defect_id, lens)"
        # forbidden spans must also resolve (a FP-guard on a phantom span guards nothing).
        for fb in c["forbidden_findings"]:
            assert fb["span"] in hay, f"case {c['id']}: forbidden span not resolvable: {fb['span']!r}"
        findings = [{"lens": f["lens"], "severity": f["min_severity"]} for f in c["expected_findings"]]
        fail = _is_fail(findings, "high")
        assert (c["expected_verdict"] == "fail") == fail, f"case {c['id']}: verdict vs _is_fail"
        assert c["expected_exit"] == (6 if fail else 0)


def test_v3_vocab_pinned_to_gate() -> None:
    d = _bench()
    assert set(d["lens_vocab"]) == set(_VALID_LENSES)
    assert set(d["severity_vocab"]) == set(_SEV_ORDER)
    assert d["fail_on_default"] == "high"


def _reproduces(run_outputs: str, grading: str) -> None:
    cases = _bench()["evals"]
    raw = json.loads((_E / "reports/v3" / run_outputs).read_text(encoding="utf-8"))
    run = {int(k): v for k, v in raw.items()}
    expected = json.loads((_E / "reports/v3" / grading).read_text(encoding="utf-8"))
    assert _grade.grade_run(cases, run) == expected, f"{grading} is stale vs grade.py"


def test_v3_shipped_grading_reproducible() -> None:
    # the shipped-prompt coverage run (bead 010-04/05): grade_run must reproduce committed grading.
    _reproduces("shipped-run-outputs.json", "shipped-grading.json")
