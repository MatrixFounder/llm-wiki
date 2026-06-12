"""TASK 030 bead 030-06 (Q-030-1) — the opt-in local SLO-enforcement gate.

The P-1 issue's original acceptance ("enforce_slos at N=10k wired into CI")
predates the no-CI reality (TASK 030 F-11). The reinterpreted gate (Q-030-1,
operator-approved default): an opt-in slow test enforcing the full `SLOS`
table at n=1000, run locally via::

    WIKI_BENCH_SLO=1 pytest tests/test_benchmark_slo_gate.py

plus the manual 10k run documented in the runbook
(`docs/runbooks/perf-slo-gate.md`). Skipped by default — SLO numbers are
machine-specific (`tests/test_benchmark.py` docstring precedent).
"""

from __future__ import annotations

import os

import pytest


@pytest.mark.slow
@pytest.mark.skipif(
    os.environ.get("WIKI_BENCH_SLO") != "1",
    reason="opt-in SLO gate: set WIKI_BENCH_SLO=1 (machine-specific numbers)",
)
def test_slo_gate_n1000_enforced() -> None:
    from scripts.benchmark import run_suite

    assert run_suite(1000, enforce_slos=True), (
        "SLO violation at n=1000 — see the per-op p95 vs SLOS output above; "
        "the design must be revisited, not the threshold (TASK-002 §5.1)")
