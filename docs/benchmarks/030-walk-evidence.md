# TASK 030 — AFTER evidence (bead 030-06; post 030-01..05)

Same machine as `030-walk-baseline.md` (macOS APFS, Python 3.14.4). Protocol
DRIFT, disclosed (Sarcasmotron 030-06 LOW): walk wall-times here are medians
of **5** (baseline used medians of 3); SLO JSONs use the identical
3-invocation median protocol on both sides (provenance in each JSON).
Tolerance reading (recorded): the TASK's ±5% is ONE-SIDED — an improvement
always satisfies it; the bound exists to catch regressions.

## Walk (R-X1-OBS-WALK — closed)

| fixture | metric | BEFORE | AFTER | verdict |
|---|---|---|---|---|
| PARA-synthetic 2084 files (obsidian-personal) | scandir calls | **140** (all 69 dirs ≥2×, root ×4) | **61** (every dir ×1, root ×1) | −56%; AC-3.3(i) ✅ |
| | dirs walked >1× | 69 | **0** | exactly-once ✅ |
| | `**/_raw/**` subtrees (×8) | traversed + post-filtered (the only ignored trees the old engine entered — baseline census: 69 = root+4 system+8 areas+48 subs+8 `_raw`) | **0 scandirs** (pruned) | AC-3.3(iii) ✅ |
| | `.obsidian`/`_templates` | 0 (never reached by the built-in globs — paths[]-prefix-failure) | **0** — now BY CONSTRUCTION (alive-set), instrumented | parity, provable ✅ |
| | wall median | 94.1 ms | **77.0 ms** | −18% ✅ |
| fat-karpathy (110 pages + 600 fat files) | scandir calls | 25 | **6** | −76% |
| | `.obsidian`/`.git`/`attachments` | 0 | **0** | §3.5 property held BY CONSTRUCTION; AC-3.3(ii) ✅ |
| | wall median (same-session OLD-engine reconstruction vs NEW, medians of 5) | 2.13 ms | **1.65 ms** | −23% ✅ |
| dev-project (90 files — distribution: issues 30 / tasks 25 / plans 20 / adr 5 / reviews 10, flat `*.md` per dir; method-reproducible, builder not committed — noted per the 030-06 review LOW) (AC-3.4 lean leg — measured BOTH sides via the git-HEAD-reconstructed old engine, same session) | wall median | 3.19 ms | **2.84 ms** | −11% ✅ |
| | scandir calls / multi | — (old engine: per-glob, no count captured) | 6 / 0 | exactly-once ✅ |

Root-scandir footnote (Q-030-6): karpathy gains exactly ONE root scandir the
literal-anchored globs avoided — covered by the lean improvements above.

## SLO benchmarks (P-1 — closed)

| op | n | BEFORE p95 | AFTER p95 | Δ | SLO | headroom |
|---|---|---|---|---|---|---|
| `wiki-reindex-full` | 1000 | 459.8 ms | **226.9 ms** | **−51% (2.03×)** | 20 000 | 88× |
| `wiki-reindex-full` | 10000 | 4601.6 ms | **2353.1 ms** | **−49% (1.96×)** | 180 000 | **76×** |
| `wiki-reindex-delta` (no-op) | 1000 | 28.4 ms | 22.3 ms | −21% (walk win) | 500 | 22× |
| `wiki-reindex-delta` (no-op) | 10000 | 246.3 ms | 191.8 ms | −22% | 2000 | 10× |
| `wiki-index-upsert` | 1000 | 0.6 ms | 0.5 ms | sub-ms timer noise | 100 | ≫ |
| `wiki-index-upsert` | 10000 | 0.6 ms | 0.7 ms | sub-ms timer noise (public DAL path = delegation only; ±0.1 ms is below the 5-run p95 resolution) | 100 | ≫ |

All `_provenance` blocks committed in the four JSONs
(`030-{baseline,after}-n{1000,10000}.json`); after-capture all-runs spreads:
full @1k [223.3, 227.3, 226.9], @10k [2352.5, 2353.1, 2442.2].

## Q-030-1 gate

`tests/test_benchmark_slo_gate.py` — `@pytest.mark.slow` + `WIKI_BENCH_SLO=1`
env gate → `run_suite(1000, enforce_slos=True)`. Manual 10k run:
`docs/runbooks/perf-slo-gate.md`. P-4 (CI scale gate proper) remains OPEN.
