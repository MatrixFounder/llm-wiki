---
id: P-4
type: known-issue
status: open
opened_at: 2026-05-26
category: performance
slug: p-4-benchmark-suite-default-n-100-only
---

# benchmark suite default n=100 only

- **Symptom**: `pytest tests/test_benchmark.py` and CLI default `--n 100` exercise only the smallest SLO bucket. The 1k/10k SLOs in `SLOS` dict are never automatically validated.
- **Root cause**: Benchmark designed for fast smoke; no CI scale gate.
- **Affected components**: `scripts/benchmark.py`, CI workflow (not yet created).
- **Fix plan**: Add `--scale all` mode (loops 100/1000/10000 + `--enforce-slos`); wire `--n 1000 --enforce-slos` into CI; mark `--n 10000` as nightly/manual. Document expected runtime per bucket.
