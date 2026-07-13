"""TASK 030 bead 030-06 (Q-030-1) — the opt-in local SLO-enforcement gate.

The P-1 issue's original acceptance ("enforce_slos at N=10k wired into CI")
predates the no-CI reality (TASK 030 F-11). The reinterpreted gate (Q-030-1,
operator-approved default): an opt-in slow test enforcing the full `SLOS`
table at n=1000, run locally via::

    WIKI_BENCH_SLO=1 pytest tests/test_benchmark_slo_gate.py

plus the manual 10k run documented in the runbook
(`docs/runbooks/perf-slo-gate.md`). Skipped by default — SLO numbers are
machine-specific (`tests/test_benchmark.py` docstring precedent).

TASK 061 FIX-LOOP (vdd-multi H3). The gate enforced the `SLOS` table over a suite
whose ops could not execute the two hot paths TASK 061 changed — the lint bench ran
over a **karpathy** vault (⇒ `drift_rules`/`coverage_rules`/`ontology:` are declared in
`cybos.yaml` ONLY ⇒ both checks early-out before their first DAL call) and the search
bench passed `min_trust=None` (⇒ `_EXTERNAL_ORIGIN_SQL` was never compiled into the
statement). The suite now carries `wiki-lint-rules` (cybos) and
`wiki-search-metadata-trust` (the metadata full-scan shape with the trust predicate
compiled in), and `run_suite` returns False on a VACUOUS run regardless of
`enforce_slos` — so this gate now enforces two independent claims:

  1. the ops met their SLO;  2. the ops reached the code (`vacuity_ok`).

(1) without (2) is what a green 30 s `wiki-lint` SLO meant before this fix-loop:
nothing.
"""

from __future__ import annotations

import json
import os

import pytest


@pytest.mark.slow
@pytest.mark.skipif(
    os.environ.get("WIKI_BENCH_SLO") != "1",
    reason="opt-in SLO gate: set WIKI_BENCH_SLO=1 (machine-specific numbers)",
)
def test_slo_gate_n1000_enforced(capsys) -> None:
    from scripts.benchmark import _VACUITY_COUNTERS, SLOS, run_suite

    ok = run_suite(1000, enforce_slos=True)
    payload = json.loads(capsys.readouterr().out)

    # NON-VACUITY FIRST: an SLO verdict over a population of 0 is a number about
    # nothing, so report that failure in its own terms rather than as a latency miss.
    vac = payload["vacuity"]
    assert vac["vacuity_ok"], (
        "VACUOUS bench run — an op did not reach the code it is named after "
        f"(zero counters: {vac.get('zero_counters')}). The SLOs below are "
        "meaningless until this is fixed.")
    for counter in _VACUITY_COUNTERS:
        assert vac[counter] > 0, counter
    assert vac["layout"] == "cybos", (
        "the wiki-lint-rules vault must resolve to the ONE layout declaring the "
        f"drift/coverage/ontology rules; got {vac['layout']}")

    # Every op with a declared bucket was actually compared against it (a typo in an
    # op name would else silently drop it from enforcement).
    measured = {r["op"] for r in payload["results"]}
    assert set(SLOS) <= measured, set(SLOS) - measured

    assert ok, (
        "SLO violation at n=1000 — see the per-op p95 vs SLOS output above; "
        "the design must be revisited, not the threshold (TASK-002 §5.1). The two "
        "TASK-061 buckets (wiki-search-metadata-trust / wiki-lint-rules) were set "
        "from observation at HEAD — see docs/runbooks/perf-slo-gate.md")
