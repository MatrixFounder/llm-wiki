# Runbook — performance SLO gate (TASK 030 / Q-030-1)

The repo has no CI; SLO enforcement is a LOCAL, opt-in gate (numbers are
machine-specific — `tests/test_benchmark.py` precedent). Run it:

```bash
# venv active, repo root
WIKI_BENCH_SLO=1 pytest tests/test_benchmark_slo_gate.py        # n=1000, enforced
python -m scripts.benchmark --n 10000 --enforce-slos            # manual 10k gate
```

Run BOTH before shipping any change to `reindex.py` / `sqlite_repository.py`
hot paths / `layout_config.iter_pages`. On a miss: the DESIGN is revisited,
not the threshold (`SLOS` dict in `scripts/benchmark.py` mirrors TASK-002
§5.1 — the single source of truth).

For before/after evidence use the 3-invocation median protocol
(`docs/benchmarks/030-walk-baseline.md` §SLO) and commit the JSONs with their
`_provenance` blocks (`docs/benchmarks/` convention, PLAN-030 §Methodology;
`docs/architectures/scalability-and-performance.md` §8.4 stays the canonical
narrative).
