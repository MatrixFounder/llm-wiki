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

## A green SLO is only worth what the run EXAMINED (TASK 061 fix-loop, H3)

The suite used to run every op against ONE synthetic vault generated as
`_sources/page-NNNN.md` with no `layout:` key — which `resolve_layout_config`
resolves to **karpathy**. Two consequences, both invisible for as long as they
existed:

- `drift_rules` / `coverage_rules` / `ontology:` are declared in **`cybos.yaml`
  only** (`grep -ln "drift_rules\|coverage_rules\|^ontology:"
  scripts/wiki_index/layouts/*.yaml` → one file). So the `wiki-lint` bench op hit
  `check_lifecycle_drift_report`'s and `check_ontology_violations_report`'s
  `return [], None` early-out: **zero DAL calls**. The 30 s SLO would have stayed
  green if those checks had been made 100× slower.
- `wiki-search` benched `search_pages("synthetic", …)` — the FTS branch with
  `min_trust=None`, so `_EXTERNAL_ORIGIN_SQL` was **never compiled into the
  statement**.

Three ops close that, each measuring a shape TASK 061 actually changed:

| op | what it executes that nothing else does |
|---|---|
| `wiki-lint-rules` | `run_all_checks_report` over a **cybos** vault (`generate_typed_vault`) — typed pages **and typed edges**, so all **24** declared rules (3 coverage + 3 drift + 7 edge + 11 property) bind to a non-empty population. Own vault, own DB: the six original ops keep their historical numbers. Times `find_lifecycle_drift_report` + `find_ontology_violations_report`. |
| `wiki-health-coverage` | `find_coverage_gaps_report` — the **third** denominator query. It rides `wiki-health coverage`, which had no bench op at all, and M1's N+1 collapse rewrote it too. Found by censusing `grep -n "def find_.*_report"` against the timed ops — timing the other two and declaring the hot paths covered would have been TASK 061's own fractal inside the fix for it. |
| `wiki-search-metadata-trust` | `search_pages(None, where_fields=[("status","active")], min_trust="internal")` — the metadata **full-scan** shape with the derived-trust predicate **compiled in** (no FTS candidate set to hide the per-row `json_each` walk behind). |

`tests/test_benchmark.py::test_unit_09` turns that census into a **gate**: the
`find_*_report` methods are enumerated from the source, and a fourth one fails the
test until an op claims it.

**Still unbenched (stated, not left merely true):** `run_multivault_scaling` (the
`--multivault` mode) exercises cross-vault search + duplicate detection only; it has
never had SLO buckets and touches none of the TASK-061 code. `wiki-health ontology`
runs the same `find_ontology_violations_report` the lint op times, so it needs no
second op.

**The bench proves it fired; it does not assume it.** Every run emits a `vacuity`
block (denominators the rules examined; rows the trust floor removed *and* kept)
and `vacuity_ok`. A vacuous run returns **False regardless of `--enforce-slos`** —
`enforce_slos=False` waives the machine-specific *thresholds*, never the claim that
the ops executed the code they are named after. Both probes are driven by the timed
op's **own closure**, so mutating the op (dropping `min_trust`, repointing the lint
vault) turns the gate red instead of leaving a proof about a query nobody times.

### Observed at HEAD — 2026-07-13, after the 061 fix-loop landed (M1 + M2 + H2)

3-invocation protocol, MacBook (darwin 25.5.0, Python 3.14.4), p95 of 5 runs
(3 for lint):

| op | n=100 | n=1 000 | n=10 000 | bucket (100/1k/10k) |
|---|---|---|---|---|
| `wiki-search-metadata-trust` | 0.34–0.37 ms | 1.62–1.73 ms | 13.4–14.1 ms | **5 / 15 / 60 ms** |
| `wiki-lint-rules` | 25.6–26.0 ms | 79.3–80.1 ms | 630–642 ms | **150 / 400 / 2500 ms** |
| `wiki-health-coverage` | 0.27–0.35 ms | 1.74–1.78 ms | 17.1–17.4 ms | **5 / 15 / 80 ms** |

Run-to-run spread is under 2 % at every size. The three new buckets are set at ~4-6×
the observed p95 at n=10k — deliberately **tighter, relative to observation, than the
historical table** (whose 10k `wiki-lint` bucket sits ~80× over the measurement). A
bucket with 50× headroom cannot fail, and an SLO that cannot fail is TASK 061's own
bug wearing a stopwatch. They are sized to catch the regressions they exist for:

- reverting `_EXTERNAL_ORIGIN_SQL` to its pre-M2 shape (12 `frontmatter_json`
  re-parses per row instead of one `json_each` pass) blows the trust bucket;
- reinstating the per-rule `COUNT` N+1 that M1 collapsed (one extra `pages` scan per
  declared rule) blows the lint-rules **and** health-coverage buckets.

**These numbers are the answer to "what shape is there now?"** — they were taken at
HEAD *after* the concurrent fix-loop landed M1 (the N+1 collapse), M2 and H2 (the
`json_each` single-pass external-origin predicate). Both hot paths are already in
their improved shape; there is no pre-fix baseline in this table to compare against,
because before this bench existed **neither path was measured at all**.

The six TASK-002 §5.1 buckets are a **contract** and are not retuned here.

**Cost note:** the 10k run now builds two vaults (10k karpathy + 10k cybos) and
reindexes both. End-to-end it is ~12 s on the reference machine.

### Sanity-check the gate itself

The gate is only as good as its teeth. Both mutations below were run against this
harness and both turn it red — reproduce them after touching `benchmark.py`:

| mutation | expected |
|---|---|
| `generate_typed_vault` → emits the karpathy vault instead | `vacuity_ok: false`, `zero_counters` names all five lint counters, `layout: karpathy`, `declared_rules: 0` |
| the timed trust op drops `min_trust` | `vacuity_ok: false`, `zero_counters: ["trust_rows_floored"]` (unfloored == floored == 20) |
