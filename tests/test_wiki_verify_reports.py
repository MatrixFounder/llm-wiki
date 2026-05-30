"""TASK 009 — vdd-multi MED-4: the recorded grading JSONs are REPRODUCIBLE.

The baseline→enriched measurement's *LLM fan-out* is recorded once (the committed raw
`reports/*-run-outputs.json` — the critic outputs); the *scoring* (`grade.py`) is
deterministic. This pins that deterministic half: `grade_run(evals.json, run_outputs)`
must equal the committed `reports/*-grading.json`. So a grade.py logic change can no
longer silently invalidate the recorded headline numbers (10→3, recall 0.571→1.0, …)
without a red test. (The live LLM fan-out itself is NOT re-run here — only the
deterministic transform over its recorded output.)
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_E = Path(__file__).resolve().parents[1] / "skills/wiki-verify/evals"
_spec = importlib.util.spec_from_file_location("wiki_verify_eval_grade", _E / "grade.py")
assert _spec and _spec.loader
_grade = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_grade)


def _reproduces(run_outputs_file: str, grading_file: str) -> None:
    cases = json.loads((_E / "evals.json").read_text(encoding="utf-8"))["evals"]
    raw = json.loads((_E / "reports" / run_outputs_file).read_text(encoding="utf-8"))
    run_outputs = {int(k): v for k, v in raw.items()}
    expected = json.loads((_E / "reports" / grading_file).read_text(encoding="utf-8"))
    assert _grade.grade_run(cases, run_outputs) == expected, \
        f"{grading_file} is stale — re-grade from {run_outputs_file} (grade.py changed?)"


def test_baseline_grading_reproducible() -> None:
    _reproduces("baseline-run-outputs.json", "baseline-grading.json")


def test_enriched_grading_reproducible() -> None:
    _reproduces("enriched-run-outputs.json", "enriched-grading.json")
