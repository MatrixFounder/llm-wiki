---
id: P-1
type: known-issue
status: fixed
opened_at: 2026-05-26
resolved_at: 2026-06-12
category: performance
slug: p-1-reindex-full-per-page-transactions
---

# reindex_full per-page transactions

- **Symptom**: `reindex_full` called `repo.upsert_page` + `repo.replace_refs` once per
  page; each opened its own `BEGIN IMMEDIATE`/`COMMIT`. At 10k pages → ~20k per-page
  commits + FTS5 trigger work per commit.
- **Root cause**: `upsert_page`/`replace_refs` own their transactions (the M-4-derived
  per-call contract), preventing a trivial outer BEGIN (SQLite forbids nested BEGIN).
- **RESOLVED (TASK 030 / R-030-2, beads 030-02+030-03)**: **stage-then-flush chunked
  transactions** — private txn-free DML helpers (`_upsert_page_in_txn`/
  `_replace_refs_in_txn`; public methods delegate, per-call semantics preserved, M-4
  untouched); `reindex_full` stages derivation (ALL file I/O) OUTSIDE any txn into a
  K=500-page ∧ 32 MiB-estimate buffer, then flushes DML-only under ONE `BEGIN IMMEDIATE`
  — the write lock is held ms-scale (Q-030-5; concurrent writers on a shared global.db
  stay live). Per-page commits: ~2N → ceil(N/K)+1.
  **Measured (3-run median p95, `docs/benchmarks/030-*`)**: full @1k
  **459.8 → 226.9 ms (2.03×)**; full @10k **4601.6 → 2353.1 ms (1.96×; 76× SLO
  headroom)**.
- **Original fix-plan correction (recorded)**: the old plan here ("defer FTS5
  maintenance: drop+rebuild triggers + bulk INSERT into pages_fts at end") was
  mechanically workable for the internal-content `pages_fts`, but REJECTED for recorded
  reasons: it requires runtime DDL (against the zero-DDL posture); a crash in the
  triggers-dropped window leaves permanent silent FTS desync; and `pages_fts` is shared
  across vaults — dropping triggers would affect concurrent operations on OTHER vaults.
  Triggers stay; trigger DML inside one outer txn is cheap.
- **Acceptance gate (amended per Q-030-1)**: the original "enforce_slos at N=10k wired
  into CI" predated the no-CI reality. Landed instead: the opt-in local gate
  (`WIKI_BENCH_SLO=1 pytest tests/test_benchmark_slo_gate.py`), the runbook
  (`docs/runbooks/perf-slo-gate.md`), and the one-time committed 10k before/after
  measurement. P-4 (the CI scale gate proper) remains open.
