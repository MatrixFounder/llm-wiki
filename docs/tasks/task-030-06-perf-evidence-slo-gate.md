# 030-06 — Perf evidence + opt-in SLO gate (R-030-5, Q-030-1)

**RTM:** R-030-5. **UC:** UC-30-1/2/3. **Depends:** 030-01..05.

## Goal
Prove the wins (measured, not projected — §8.4/P-5 lesson) and land the Q-030-1
reinterpreted P-1 gate.

## Steps
1. After-measurements, same protocol as 030-00 (3 runs, medians):
   `--n 1000` + `--n 10000` → `docs/benchmarks/030-after-n{1000,10000}.json`.
   Assertions: full-rebuild p95 improvement reported with the number; delta-noop
   p95 within ±5% of baseline (AC-1.5); upsert p95 within ±5% (public DAL path
   unchanged); full @10k < 180 s SLO with explicit headroom (AC-2.5).
2. Walk evidence: PARA-synthetic ≥2k fixture before/after wall-time + scandir
   counts; fat-karpathy fixture strictly improved; lean karpathy/dev-project
   within ±5% (AC-3.4). Record in `docs/benchmarks/030-walk-evidence.md`.
3. **Opt-in SLO gate (Q-030-1):** `tests/test_benchmark_slo_gate.py` —
   `@pytest.mark.slow` + skip unless `WIKI_BENCH_SLO=1`; runs
   `run_suite(1000, enforce_slos=True)`. Runbook line (10k manual run) added to
   `docs/runbooks/` + README dev section.
4. Update `docs/architectures/scalability-and-performance.md` §8.4 table
   (P-1 + R-X1-OBS-WALK rows: measured before/after, mechanism one-liners).

## Acceptance
- ✅ All ±5% assertions hold (or the regression is investigated + fixed before
  close — no waivers).
- ✅ Evidence files committed + referenced from §8.4; SLOS dict UNCHANGED.
- ✅ Gate test runs green locally with `WIKI_BENCH_SLO=1`; skipped by default.
- ✅ Sarcasmotron pass.
