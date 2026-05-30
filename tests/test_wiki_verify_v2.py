"""TASK 009 follow-up — the v2 diverse benchmark (32 cases, 12 domains).

Deterministic guards only (the LLM run itself is recorded under reports/v2/):
- `evals-v2.json` well-formedness + the same invariants the v1 set must hold
  (vocab pinned to the gate enums; per-case `_is_fail(expected) == expected_verdict`;
  spans resolvable; unique (defect_id, lens) pairs).
- Reproducibility: `grade_run(evals-v2.json, committed run-outputs) == committed grading`
  for BOTH the baseline and enriched runs — so the benchmark's headline numbers can't
  silently drift from `grade.py`.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from scripts.wiki_skills.wiki_verify_multi import _SEV_ORDER, _VALID_LENSES, _is_fail

_E = Path(__file__).resolve().parents[1] / "skills/wiki-verify/evals"
_spec = importlib.util.spec_from_file_location("wiki_verify_eval_grade_v2", _E / "grade.py")
assert _spec and _spec.loader
_grade = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_grade)


def _bench() -> dict:
    return json.loads((_E / "evals-v2.json").read_text(encoding="utf-8"))


def test_v2_has_32_cases_across_12_domains() -> None:
    cases = _bench()["evals"]
    assert len(cases) == 32
    assert len({c["domain"] for c in cases}) == 12
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids))


def test_v2_invariants_hold_per_case() -> None:
    for c in _bench()["evals"]:
        hay = c["answer"] + " " + " ".join(e["body"] for e in c["examined"])
        pairs = []
        for f in c["expected_findings"]:
            assert f["lens"] in _VALID_LENSES
            assert f["min_severity"] in _SEV_ORDER
            assert f["span"] in hay, f"case {c['id']}: span not resolvable"
            pairs.append((f["defect_id"], f["lens"]))
        assert len(pairs) == len(set(pairs)), f"case {c['id']}: dup (defect_id, lens)"
        findings = [{"lens": f["lens"], "severity": f["min_severity"]} for f in c["expected_findings"]]
        fail = _is_fail(findings, "high")
        assert (c["expected_verdict"] == "fail") == fail, f"case {c['id']}: verdict vs _is_fail"
        assert c["expected_exit"] == (6 if fail else 0)


def _reproduces(run_outputs: str, grading: str) -> None:
    cases = _bench()["evals"]
    raw = json.loads((_E / "reports/v2" / run_outputs).read_text(encoding="utf-8"))
    run = {int(k): v for k, v in raw.items()}
    expected = json.loads((_E / "reports/v2" / grading).read_text(encoding="utf-8"))
    assert _grade.grade_run(cases, run) == expected, f"{grading} is stale vs grade.py"


def test_v2_baseline_grading_reproducible() -> None:
    _reproduces("baseline-run-outputs.json", "baseline-grading.json")


def test_v2_enriched_grading_reproducible() -> None:
    _reproduces("enriched-run-outputs.json", "enriched-grading.json")
