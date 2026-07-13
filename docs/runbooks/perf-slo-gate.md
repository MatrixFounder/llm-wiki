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
| `wiki-search-metadata-trust-fat` | the SAME query, re-timed after `plant_fat_provenance` adds 4 pages carrying a **10 000-member `sources:` array** — the O(members) walk the H2 fix introduced (the pre-H2 predicate was O(1) on such a row *because it never looked inside*, which was the bug). Added in iteration-2: the only list shape in the fixture had **one** member, so nothing bounded or benched a fat one. |

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
| `wiki-search-metadata-trust` | 0.38–0.39 ms | 1.75–2.12 ms | 14.0–15.7 ms | **5 / 15 / 60 ms** |
| `wiki-search-metadata-trust-fat` | 16.4–17.0 ms | 18.7–19.2 ms | 31.2–32.6 ms | **80 / 90 / 150 ms** |
| `wiki-lint-rules` | 26.5–27.8 ms | 79.3–80.1 ms | 725–780 ms | **150 / 400 / 2500 ms** |
| `wiki-health-coverage` | 0.35–0.39 ms | 1.74–1.80 ms | 17.6–18.3 ms | **5 / 15 / 80 ms** |

Run-to-run spread is under ~5 % at every size. `trust-fat` is nearly **flat in n**
(17 → 19 → 33 ms) because its cost is dominated by the fixture's 40 000 member-rows,
not by the page count — that flatness *is* the characterisation of the O(members)
walk; the delta against `trust` at the same n is the price of one fat page on the hot
search path.

**These numbers are the answer to "what shape is there now?"** — they were taken at
HEAD *after* the concurrent fix-loop landed M1 (the N+1 collapse), M2 and H2 (the
`json_each` single-pass external-origin predicate). Both hot paths are already in
their improved shape; there is no pre-fix baseline in this table to compare against,
because before this bench existed **neither path was measured at all**.

The six TASK-002 §5.1 buckets are a **contract** and are not retuned here.

### What these buckets CATCH — and what they do NOT (TASK 061 iteration-2, perf MED-1)

An earlier version of this section claimed the buckets were "sized to catch the
regressions they exist for": reverting M2 "blows the trust bucket", reinstating M1's
per-rule `COUNT` N+1 "blows the lint-rules **and** health-coverage buckets". Do the
arithmetic against the table directly above and the claim **refutes itself**:

| bucket | observed @10k | bucket | headroom | regression it claimed to catch | actual size | caught? |
|---|---|---|---|---|---|---|
| `wiki-search-metadata-trust` | 15.7 ms | 60 ms | 3.8× | revert M2 | **1.07×** (12.00 → 11.21 ms, measured) | **no** |
| `wiki-lint-rules` | 780 ms | 2500 ms | 3.2× | revert M1 | ~1.5–1.9× in *statement count* (25 → 38) | **no** |
| `wiki-health-coverage` | 18.3 ms | 80 ms | 4.4× | revert M1 | ~1.75× in *statement count* (4 → 7) | **no** |

Why M2 is only ~7 %: the pre-M2 form's 12 `json_extract` calls hit the **same blob in
the same row**, and SQLite has had a per-connection **JSON parse cache since 3.42** —
so they are *1 parse + 11 cheap path walks*, not 12 parses. (The perf critic's
iteration-1 estimate — "~180 ms vs ~90 ms against a 100 ms SLO" — was wrong by ~15×
and it retracted it. The 100 ms SLO was never at risk. M2 is still worth keeping: for
the **H2 fail-open fix** and for **flatness in key count** — structurally pinned, not
timed — but not for the latency.) And `wiki-lint-rules` p95 is dominated by
`check_drift`'s **O(pages) file re-hash sweep** (disk I/O + hashing, P-10): at 10k
pages you could *triple* the rule queries and p95 would barely twitch.

So, stated rather than left merely true:

> These are **absolute-latency guards** (4–6× headroom). They catch an
> **order-of-magnitude blowup** — a scan becoming a nested loop, an index vanishing, a
> per-row Python round-trip appearing inside a DAL method, a recursive `json_tree`
> descent replacing the fixed-depth member walk. They do **not** catch M1 or M2.

They are deliberately **not** tightened to 1.3×: enforcement is off by default and the
numbers are machine-specific, so a bucket sized to the noise floor is a flaky bucket,
not a gate.

**The actual M1/M2 regression detectors are structural tests** (both mutation-verified,
both named in the `SLOS` comment and kept resolvable by
`tests/test_benchmark.py::test_unit_10_the_named_regression_detectors_exist`):

- `tests/test_health_denominators.py::test_m1_statement_census_no_n_plus_one` — counts
  the statements each report issues via `sqlite3.set_trace_callback` (exact 4 / 5 / 20).
- `tests/test_trust_tier.py::test_external_origin_sql_parses_the_blob_exactly_once` —
  exactly one `json_each(p.frontmatter_json)`, zero `json_extract`, no `json_tree`, LIKE
  count constant in the key count.

**Do not delete either as "redundant with the perf gate".** They are not redundant;
they are the only thing watching those paths. *Those are the regression detectors. This
is the stopwatch. Different jobs.*

### Cost note — and why the 10k setup is deliberately expensive

The 10k run builds **two** 10k vaults (karpathy + cybos) and reindexes both; the second
`reindex_full` is **untimed setup** (`wiki-reindex-full`'s own 10k SLO is 180 s, so this
is a multi-minute leg in the worst case — ~7 s on the reference machine). Then
`plant_fat_provenance` writes and indexes 4 more pages carrying 10 000 provenance
members each. End-to-end the 10k run is **~13.7 s** on the reference machine.

That doubled setup is the **honest price of covering the shape**, not waste: the typed
vault is the only fixture in which the 24 drift/coverage/ontology rules can execute at
all. **Do not "optimise" `generate_typed_vault(n_pages)` down to a constant (n=100) to
speed the run up** — that would silently destroy the *scale* coverage of the rule
queries and leave `wiki-lint-rules` measuring a fixed 100-page population under a 10k
banner, which is the same class of bug this whole runbook section exists to document.
If the setup cost ever has to come down, shrink it **loudly** (a new op name, a new
bucket, a note here), never by quietly pinning n.

**Still unbenched (stated, not left merely true):** a fat provenance array on the FTS
branch (`wiki-search` with `min_trust`) — the FTS candidate set narrows the row count
before the predicate, so it is strictly cheaper than the metadata full-scan shape
`trust-fat` already bounds; and `reindex`/`upsert` of a fat-array page (the YAML parse
is O(members) there too, but it is a write path, not the hot read path).

### Sanity-check the gate itself

The gate is only as good as its teeth. Both mutations below were run against this
harness and both turn it red — reproduce them after touching `benchmark.py`:

| mutation | expected |
|---|---|
| `generate_typed_vault` → emits the karpathy vault instead | `vacuity_ok: false`, `zero_counters` names all five lint counters, `layout: karpathy`, `declared_rules: 0` |
| the timed trust op drops `min_trust` | `vacuity_ok: false`, `zero_counters: ["trust_rows_floored"]` (unfloored == floored == 20) |
| `_fat_provenance_page` members become `https://…` | `vacuity_ok: false`, `zero_counters: ["trust_fat_rows_internal"]` — `EXISTS` short-circuits on member 0, so `trust-fat` would have been timing a 1-member walk under a 10 000-member name (also red: `test_unit_11_the_fat_provenance_walk_does_not_short_circuit`) |
| rename `test_m1_statement_census_no_n_plus_one` (or the trust-tier structural test) | red: `test_unit_10_the_named_regression_detectors_exist` — the `SLOS` comment names them as the M1/M2 detectors the buckets cannot replace, so the reference must resolve |
