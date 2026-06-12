# Development Plan: TASK 030 — reindex-perf-hardening (DF-029-1 + P-1 + R-X1-OBS-WALK)

> **Status**: EXECUTED 2026-06-12 — all 8 beads merged via `/vdd-develop-all` (per-bead Sarcasmotron, every bead converged iter-2).
> **Task ID**: 030 / Slug: `task-030-reindex-perf-hardening`
> **Source spec**: [docs/TASK.md](./TASK.md) v2 (RTM R-030-1..6; UC-30-1..4; recon facts
> F-1..F-14; Q-030-1..4) — task-review: 3-perspective adversarial, 3× NEEDS-REVISION →
> all findings folded ([record](./reviews/task-030-review.md)).
> **Architecture spec**: [docs/ARCHITECTURE.md](./ARCHITECTURE.md) status block +
> §11a **Q-030-1..6** (delta predicate; chunked-tx error semantics; descent predicate;
> `Path.glob` parity envelope).
> **Methodology**: **Stub-First / red-green, green-throughout** — every bead lands its
> tests FIRST (RED where the behavior is new; GREEN semantic pins BEFORE the engine
> rewrite they protect), then the minimal implementation; the full suite (1204+4 pytest,
> mypy `--strict`) is green at every bead boundary. Per-bead Sarcasmotron; post-ship
> `/vdd-multi` to convergence + code-review. **`tdd-strict` applies to 030-01 (SEV-2
> correctness fix) and 030-05 (engine rewrite)** — TASK-019 precedent.
> **Declared AC splits** (exactly-one-owner exceptions): AC-1.5 = P-2 detector (030-01)
> + ±5% benchmark (030-06); AC-2.5 = measurements/gate (030-06) + issue-line amendment
> (030-07); AC-2.3 = mechanical oracle (030-02) + BEGIN-IMMEDIATE audit (030-03 close).
> **New convention declared:** `docs/benchmarks/` holds committed before/after evidence
> JSONs; `docs/architectures/scalability-and-performance.md` §8.4 stays the CANONICAL
> narrative and references them (single-home rule — JSONs are evidence, not a second
> source of truth).
> **Branch**: `task-030-reindex-perf-hardening` (no auto-commit — operator's standing rule).
> **Ship-separability** (TASK §0): {030-01} ⊥ {030-02,030-03} ⊥ {030-04,030-05} — any
> workstream can be dropped mid-cycle without stranding the others; 030-06/07 close out
> whatever shipped.
> **Out of scope guards**: R-X1-CFG-COST (no NEW `resolve_layout_config` calls — assert
> in review); wiki-sync's own walk untouched; `wiki_query`/`wiki_verify_multi` DAL
> writers keep per-call txns; swap/rotation rename detection (documented residual A5).

---

## 0. Architectural Foundation (Reference)

| Surface | Change | Binding constraints |
|---|---|---|
| `scripts/wiki_index/reindex.py` | `reindex_delta`: new-path membership predicate + per-file `sqlite3.Error` catch + `new_path_ingested` envelope field; `reindex_full`: chunked caller-owned txns (K=500 module constant), bulk path skips hash pre-SELECT | F-2 string convention (`str(relative_to())`); Q-021-2 seed invariant (seeded ∩ ingested = ∅); M-1 one `replace_refs`/page; envelope additive-only |
| `scripts/wiki_index/sqlite_repository.py` | extract private txn-free DML helpers `_upsert_page_in_txn` / `_replace_refs_in_txn`; public methods delegate + keep own-tx semantics | M-4 untouched (ON CONFLICT DO UPDATE); ABC `repository.py` signatures untouched; FTS triggers STAY (Q-030-5 / F-5) |
| `scripts/wiki_index/layout_config.py` | `iter_pages` → single-pass `os.scandir` recursion + descent predicate (R-030-6) + ordered `full_match` first-match attribution (the `derive_discovered_page` matcher family) | conformance (a)–(e) per F-9; `Path.glob` symlink parity (Q-030-2/F-10); P-2 single-stat (`DirEntry.stat()` → `DiscoveredPage.mtime`); karpathy "root never walked" BY CONSTRUCTION (Q-030-6); case-sensitivity delta enumerated (UC-30-3 A4) |
| `scripts/benchmark.py` + `tests/` | baseline/after evidence; opt-in SLO gate (`WIKI_BENCH_SLO=1`); instrumented traversal/commit counters (test-side only) | measured-not-projected (§8.4); ±5% tolerances; SLOS dict unchanged |
| Docs/skill surfaces (F-12 nine + 2 design texts) | lockstep close-out | AC-4.1 repo-wide grep; KNOWN_ISSUES re-render (PW-Q); E-07 + canaries re-run only (Q-030-4) |
| `sql/`, schema, deps | **UNTOUCHED** | zero DDL (`user_version` 5), no new deps, no `import anthropic` |

---

## 1. RTM → Bead Checklist

Phase 1 (pins + baselines = the safety net) ──────────────────────────────────
- [ ] **[R-030-5-baseline]** Benchmark baselines captured + committed; GREEN semantic
  pins written BEFORE any engine change (AC-3.1 overlap-dedup pin; AC-3.5 symlink-parity
  pins on the CURRENT engine; A6 case-posture pin) → **030-00**

Phase 2 (three independent workstreams, each red→green) ──────────────────────
- [ ] **[R-030-1]** Rename-aware `--delta`: RED e2e (029-06 repro) + A1..A8 edge tests →
  membership predicate + targeted `file_path` refresh (A6 convergence, AC-1.9) +
  `sqlite3.Error` isolation + `new_path_ingested` (+ all-vaults total) → **030-01**
- [ ] **[R-030-2a]** DAL: private txn-free helpers, public delegation, mechanical
  own-tx oracle (AC-2.2) — zero behavior change → **030-02**
- [ ] **[R-030-2b]** `reindex_full` chunked txns + pre-SELECT skip: commit-count
  (AC-2.4), parity (AC-2.1), F-6 corner (AC-2.6), boundaries (AC-2.7), Q-030-5
  error-path → **030-03**
- [ ] **[R-030-3/6-units]** Pure matcher units: segment prefix-matcher (descent
  predicate), prunable-ignore classifier — unit-tested, UNWIRED → **030-04**
- [ ] **[R-030-3/6-wire]** `iter_pages` single-pass rewrite: traversal-count tests
  flip RED→GREEN (AC-3.3 i/ii/iii); conformance suites green unmodified (AC-3.2);
  AC-3.5/3.6 → **030-05**

Phase 3 (evidence + close-out) ───────────────────────────────────────────────
- [ ] **[R-030-5 + Q-030-1]** After-measurements (`--n 1000`/`--n 10000`, ≥2k PARA
  fixture, fat-karpathy fixture); ±5% checks; `WIKI_BENCH_SLO` opt-in gate; §8.4
  table; runbook line → **030-06**
- [ ] **[R-030-4]** Nine doc surfaces + issue files (corrected rationales) +
  KNOWN_ISSUES re-render + ROADMAP + Q-024-residual-2 + functional-architecture
  fix + obsidian-cli rule flip + E-07/canaries re-run + AC-4.1 repo-wide grep +
  final gates → **030-07**

> **Grouping note:** R-030-3 and R-030-6 share beads 030-04/05 because the descent
> predicate is meaningless unwired and the wiring is unsafe without it — one cohesive
> engine change, two traceable checklist items with separate ACs (plan-009 precedent).

---

## 2. Bead Sequence & Dependency Graph

```
030-00  baselines + semantic pins (GREEN pins, committed baselines)        ──┐ Phase 1
           │
030-01  delta rename-aware (R-030-1)            [independent]             ──┐
030-02  DAL txn-free helpers (R-030-2a)         [independent]               │
030-03  chunked-tx full (R-030-2b)              [needs 030-02]              ├─ Phase 2
030-04  matcher units (R-030-3/6, unwired)      [independent]               │
030-05  iter_pages rewrite (R-030-3/6, wired)   [needs 030-00 pins+030-04] ──┘
           │
030-06  perf evidence + SLO gate (R-030-5, Q-030-1)  [needs all shipped]  ──┐ Phase 3
030-07  docs/skill close-out + gates (R-030-4)       [needs 030-06]       ──┘
```

| Bead | Depends on | Verification kind |
|---|---|---|
| 030-00 | — | deterministic: pins GREEN on current engine; baseline JSONs exist + referenced |
| 030-01 | 030-00 (baseline for AC-1.5) | red→green: e2e repro RED → GREEN; TASK-021 suite green unmodified |
| 030-02 | — | zero-delta: full suite green; new oracle test green; mypy strict |
| 030-03 | 030-02 | red→green: commit-count + parity + corner tests |
| 030-04 | — | red→green unit tests on pure functions |
| 030-05 | 030-00, 030-04 | red→green: AC-3.3 counters flip; AC-3.2 conformance green UNMODIFIED |
| 030-06 | 030-01..05 | measured evidence; ±5% assertions; opt-in gate runs locally |
| 030-07 | 030-06 | grep/render/eval checks; per-phase gates + post-ship `/vdd-multi` |

---

## 3. Verification protocol (per bead + final)

1. **Per bead:** pytest (full suite) + mypy `--strict scripts/` + the bead's own AC
   list + Sarcasmotron pass on the bead diff.
2. **Engine-rewrite extra (030-05):** karpathy golden anchor
   (`test_karpathy_byte_identity.py`) + §D8 rebuildability + upsert↔reindex parity +
   security suite — all green UNMODIFIED (any needed test edit = a finding, stop and
   re-review).
3. **AC-2.3 audit step (plan-level, per task-review):** grep-enumerate every
   `BEGIN IMMEDIATE` site in `scripts/` at 030-03 close; assert the only NEW
   caller-owned txn is the chunk loop; helpers absent from `repository.py` ABC.
4. **Final:** benchmark evidence in §8.4; AC-4.1 repo-wide grep; KNOWN_ISSUES PW-Q
   clean; E-07 + canaries green; post-ship `/vdd-multi` (logic/security/performance)
   to convergence; code-review gate; NO auto-commit.

## 4. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Engine rewrite breaks an unpinned semantic | 030-00 writes the missing pins FIRST (overlap-dedup, symlink parity) — the review-found F-8 gap closes before any engine edit |
| Chunked tx hides a per-file isolation regression | Q-030-5 stage-then-flush semantics stated; error-path tests (mid-flush DML; fatal = COMMIT injection) in 030-03 |
| Chunk txn starves concurrent writers (shared global.db / iCloud) | stage-then-flush: lock held for DML only; lock-hold guard test (no file I/O inside the txn) |
| Delta predicate double-ingests a seeded row | AC-1.3 composite test asserts seeded ∩ ingested = ∅ directly |
| Delta re-detects a moved-but-unchanged file forever | targeted `file_path` refresh on "unchanged" + AC-1.9 convergence test (second delta = true no-op) |
| Walk perf "win" is fixture-flattering | AC-3.4 measures BOTH lean (±5%) and fat fixtures; obsidian-personal ≥2k synthetic vault |
| Recursive walk = `RecursionError` DoS on deep trees | explicit-stack iterative walk REQUIRED + AC-3.8 ≥1500-deep fixture |
| `full_match` vs `Path.glob` divergence (char classes, case, symlinks) | 030-04 property test = full DiscoveredPage-tuple equality vs the old engine on adversarial fixtures incl. symlink topologies; alive-set rule pins the union semantics |
| `set_trace_callback` brittleness | AC-2.4 counts both BEGIN forms on a constrained fixture; C composition documented in-test |
| Doc drift (ten surfaces incl. CLAUDE.md) | UC-30-4 enumeration + AC-4.1 multiline `rg -iU` with a defined adjudication allowlist |
