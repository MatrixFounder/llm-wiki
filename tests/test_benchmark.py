"""Smoke tests for scripts/benchmark.py (task-001-33).

CI does NOT enforce SLOs by default (machine-specific). Tests assert harness
correctness only.

TASK 061 FIX-LOOP (vdd-multi H3) — the tests below pin the property that the perf
critic found MISSING: that the bench can execute the code TASK 061 changed at all. The
old bench could not, and no test noticed, because every test asserted the harness
*ran* — never that it *reached* anything. So these assert on POPULATIONS, not on exit
codes:

  - `test_unit_05` pins the finding itself (the karpathy bench vault declares ZERO
    rules — over a NON-EMPTY page table, so it is a statement about the layout and not
    about an empty DB: the vacuity test that is itself vacuous is the exact trap this
    task keeps re-falling into);
  - `test_unit_06` pins that the new typed vault fires all 24 rules with a non-zero
    `matched` — a typed-pages-but-no-edges fixture would report `pages_examined > 0`
    with every `matched: 0` and "prove" non-vacuity while proving nothing;
  - `test_unit_07` pins that `min_trust` is COMPILED INTO THE STATEMENT (read off the
    executed SQL via a trace callback), not merely passed as an argument;
  - `test_unit_08` pins the fail-CLOSED wiring: a vacuous run returns False even with
    `enforce_slos=False`.

TASK 061 ITERATION-2 (perf MED-1 + LOW) — the bench's own CLAIMS, kept honest:

  - `test_unit_10` pins the two structural tests the `SLOS` comment names as the ACTUAL
    M1/M2 regression detectors (the buckets are 4-6× absolute-latency guards; the
    regressions are 1.07× and ~1.75× — the comment used to claim otherwise). Delete
    either detector "as redundant with the perf gate" and this turns red;
  - `test_unit_11` pins that the fat-provenance fixture makes the O(members) walk run to
    the END — an external member at index 0 would short-circuit `EXISTS` and the fat op
    would time a 1-member walk under a 10 000-member name.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

from scripts.benchmark import (
    _BENCH_FAT_MEMBERS,
    _BENCH_FAT_PAGES,
    _TYPED_CORE,
    _VACUITY_COUNTERS,
    generate_synthetic_vault,
    generate_typed_vault,
    measure,
    plant_fat_provenance,
    run_multivault_scaling,
    run_suite,
)
from scripts.wiki_index.layout_config import resolve_layout_config
from scripts.wiki_index.lint import run_all_checks_report
from scripts.wiki_index.models import Vault
from scripts.wiki_index.reindex import reindex_full
from scripts.wiki_index.sqlite_repository import SQLiteRepository


def _index(tmp_path: Path, root: Path, vault_id: str) -> SQLiteRepository:
    """Register + `reindex --full` a generated bench vault; return the repo."""
    repo = SQLiteRepository(tmp_path / f"{vault_id}.db")
    repo.apply_schema()
    repo.register_vault(Vault(
        vault_id=vault_id, name=vault_id, root_path=root,
        schema_version="2.0", registered_at=datetime(2026, 5, 26)))
    reindex_full(repo, vault_id)
    return repo


def test_unit_01_synthetic_vault_page_count(tmp_path):
    """generate_synthetic_vault produces N source pages + WIKI_SCHEMA.md."""
    generate_synthetic_vault(tmp_path, "bench-v", 25)
    sources = list((tmp_path / "_sources").glob("page-*.md"))
    assert len(sources) == 25
    assert (tmp_path / "WIKI_SCHEMA.md").is_file()
    # frontmatter parseable
    txt = sources[0].read_text()
    assert txt.startswith("---\n")


def test_unit_02_synthetic_deterministic_with_seed(tmp_path):
    """Same seed → identical file contents."""
    a = tmp_path / "a"
    b = tmp_path / "b"
    generate_synthetic_vault(a, "v-a", 10, seed=1)
    generate_synthetic_vault(b, "v-b", 10, seed=1)
    # WIKI_SCHEMA differs (vault_id), but page bodies depend only on i + seed
    for i in range(10):
        ap = (a / "_sources" / f"page-{i:04d}.md").read_text()
        bp = (b / "_sources" / f"page-{i:04d}.md").read_text()
        assert ap == bp


def test_unit_03_measure_returns_expected_keys():
    stats = measure("noop", lambda: None, runs=3)
    for k in ("op", "runs", "min_ms", "p50_ms", "p95_ms", "max_ms"):
        assert k in stats
    assert stats["op"] == "noop"
    assert stats["runs"] == 3


# --- TASK 061 fix-loop (H3): the bench can REACH the changed code -------------

def test_unit_04_typed_vault_resolves_to_cybos_with_all_rules(tmp_path):
    """The lint bench vault must resolve to the ONE layout that declares the rules.

    `grep -ln "drift_rules\\|coverage_rules\\|^ontology:" scripts/wiki_index/layouts/
    *.yaml` → `cybos.yaml`, and nothing else. Assert on the RESOLVED config, not on
    the `layout:` string we wrote — "I set the key" is not "the engine read it".
    """
    root = tmp_path / "typed"
    generate_typed_vault(root, "t-cybos", 60)
    config = resolve_layout_config(root)
    assert config.layout == "cybos"
    assert len(config.drift_rules) == 3
    assert len(config.coverage_rules) == 3
    assert config.ontology is not None
    assert len(config.ontology.edges) == 7
    assert len(config.ontology.properties) == 11
    # 24 = the rule count the LIVE-vault anchor in TASK.md §Completion reports.
    total = (len(config.drift_rules) + len(config.coverage_rules)
             + len(config.ontology.edges) + len(config.ontology.properties))
    assert total == 24

    # The core archetypes are a FLOOR, not a fraction: at `--n 5` the rules must still
    # bind to a non-empty population (a bench that silently goes vacuous at small N is
    # the same bug at a different scale).
    small = tmp_path / "small"
    assert generate_typed_vault(small, "t-small", 5) == len(_TYPED_CORE)


def test_unit_05_karpathy_bench_vault_declares_zero_rules(tmp_path):
    """THE H3 FINDING, pinned. The original bench vault (`_sources/page-NNNN.md`, no
    `layout:`) resolves to **karpathy** ⇒ zero drift/coverage/ontology rules ⇒ both
    config-driven checks `return [], None` before their first DAL call. The old
    `wiki-lint` bench op therefore executed NONE of the code TASK 061 changed.

    Asserted over a vault with pages INDEXED (`pages_indexed > 0`) — the point is that
    the *layout* declares no rules, not that the *table* is empty. (An earlier bead in
    this very task shipped a vacuity test that was itself vacuous: it asserted "an
    indexed page is not counted" over an EMPTY table.)
    """
    root = tmp_path / "karpathy"
    generate_synthetic_vault(root, "k-vault", 30)
    config = resolve_layout_config(root)
    assert config.layout == "karpathy"
    assert not config.drift_rules and not config.coverage_rules
    assert config.ontology is None

    repo = _index(tmp_path, root, "k-vault")
    # The table is NOT empty — so `denominators == {}` is a fact about the LAYOUT.
    assert len(repo.search_pages("synthetic", vaults=["k-vault"], limit=1000)) > 0
    report = run_all_checks_report(repo, vaults=["k-vault"])
    assert report.denominators == {}, (
        "the karpathy bench vault must stay rule-free (byte-identity anchor); the "
        "rules are exercised by the cybos `wiki-lint-rules` vault instead")
    repo.close()


def test_unit_06_typed_vault_fires_every_declared_rule(tmp_path):
    """Prove the rules RAN — do not assume the layout changed.

    Every one of the 24 declared rules must come back with `matched > 0`, and all four
    denominator populations must be non-zero. A fixture with typed pages but no typed
    EDGES would satisfy `pages_examined > 0` with every `matched: 0` — green, and
    measuring nothing.
    """
    root = tmp_path / "typed"
    n = generate_typed_vault(root, "t-fire", 80)
    assert n == 80
    repo = _index(tmp_path, root, "t-fire")
    config = resolve_layout_config(root)

    report = run_all_checks_report(repo, vaults=["t-fire"])
    denom = report.denominators["t-fire"]
    drift, ont = denom["lifecycle-drift"], denom["ontology-violation"]
    assert drift["pages_examined"] > 0
    assert ont["edges_examined"] > 0
    assert ont["property_pages_examined"] > 0
    cov = repo.find_coverage_gaps_report("t-fire", list(config.coverage_rules))
    assert cov.pages_examined > 0

    stats = list(drift["by_rule"]) + list(ont["by_rule"])
    assert len(stats) == 3 + 7 + 11
    assert all(s["matched"] > 0 for s in stats), \
        [s for s in stats if s["matched"] == 0]
    assert len(cov.rule_stats) == 3
    assert all(s.matched > 0 for s in cov.rule_stats)

    # …and the findings are non-zero too, so a regression that stops PRODUCING issues
    # (not just counting them) is visible.
    assert [i for i in report.issues if i.category == "lifecycle-drift"]
    assert [i for i in report.issues if i.category == "ontology-violation"]
    assert cov.gaps
    repo.close()


def test_unit_07_trust_predicate_is_compiled_into_the_statement(tmp_path):
    """`min_trust` must reach the SQL TEXT, not just the call site.

    The old `wiki-search` bench op passed `min_trust=None`, so `_EXTERNAL_ORIGIN_SQL`
    was never compiled in — a bench for a predicate that is not in the query. Read the
    executed statement off a trace callback and assert the predicate is (a) ABSENT
    without the floor and (b) PRESENT with it — then assert it changes the result set.

    The discriminator is the `_EXTERNAL_ORIGIN_SQL` LITERAL, not the word `json_each`:
    the `where_fields` list-membership clause ALSO walks `json_each` (ADR-005), so
    "the query mentions json_each" would have passed on the unfloored query too — a
    green assertion proving nothing, which is the disease this task exists to treat.
    (Found by running the test, not by reading it.)
    """
    from scripts.wiki_index.policy import EXTERNAL_PROVENANCE_KEYS
    from scripts.wiki_index.sqlite_repository._search import _EXTERNAL_ORIGIN_SQL

    root = tmp_path / "karpathy"
    generate_synthetic_vault(root, "k-trust", 60)
    repo = _index(tmp_path, root, "k-trust")

    seen: list[str] = []
    repo._connect().set_trace_callback(seen.append)
    unfloored = repo.search_pages(
        None, vaults=["k-trust"], where_fields=[("status", "active")], limit=1000)
    no_floor_sql = " ".join(seen)
    seen.clear()
    floored = repo.search_pages(
        None, vaults=["k-trust"], where_fields=[("status", "active")],
        min_trust="internal", limit=1000)
    floor_sql = " ".join(seen)
    repo._connect().set_trace_callback(None)

    assert _EXTERNAL_ORIGIN_SQL not in no_floor_sql   # the shape the OLD bench measured
    assert _EXTERNAL_ORIGIN_SQL in floor_sql          # the shape TASK 061 changed
    for key in EXTERNAL_PROVENANCE_KEYS:
        assert f"'{key}'" in floor_sql
    # …and it DISCRIMINATES: it removes rows, and it keeps rows. Either alone can be
    # satisfied by a degenerate vault (all-external ⇒ empty result set).
    assert len(floored) > 0
    assert len(unfloored) > len(floored)
    repo.close()


def test_unit_09_every_denominator_query_is_timed_by_some_op():
    """THE CENSUS, AS A GATE. TASK 061 added three denominator-bearing DAL methods;
    the first cut of this fix-loop timed two of them and would have shipped calling the
    hot paths covered — `find_coverage_gaps_report` (which M1's N+1 collapse also
    rewrote, and which rides the never-benched `wiki-health coverage`) was timed by
    NOTHING. It was found by grepping, not by reasoning.

    So: enumerate the `find_*_report` methods FROM THE SOURCE and require each to be
    claimed by a bench op with an SLO bucket. A fourth one cannot land untimed — this
    test fails until someone says which op measures it.
    """
    import re

    from scripts.benchmark import SLOS

    timed_by = {
        "find_lifecycle_drift_report": "wiki-lint-rules",
        "find_ontology_violations_report": "wiki-lint-rules",
        "find_coverage_gaps_report": "wiki-health-coverage",
    }
    src = (Path(__file__).parent.parent / "scripts" / "wiki_index"
           / "sqlite_repository" / "_health_rules.py").read_text(encoding="utf-8")
    declared = set(re.findall(r"def (find_\w+_report)\(", src))
    assert declared == set(timed_by), (
        "a denominator-bearing DAL method is not claimed by any bench op — add it to "
        f"`timed_by` AND give it a timed op: {declared ^ set(timed_by)}")
    for method, op in timed_by.items():
        assert op in SLOS, f"{method} is timed by {op}, which has no SLO bucket"


def test_unit_10_the_named_regression_detectors_exist():
    """THE BENCH'S CLAIM ABOUT ITS OWN LIMITS, KEPT HONEST (TASK 061 iteration-2, MED-1).

    The `SLOS` comment used to claim the buckets "CATCH" the M1/M2 regressions. The
    arithmetic against the numbers printed five lines above it says otherwise: reverting
    M2 costs ~7% MEASURED (SQLite ≥3.42 caches the per-connection JSON parse, so 12
    `json_extract` calls on the same blob in the same row are 1 parse + 11 path walks —
    the iteration-1 estimate was wrong by ~15×) and reverting M1 costs ~1.75-1.9× in
    STATEMENT COUNT, both far inside a 4-6× bucket. Nobody was hurt — but the next
    engineer reads that comment, believes the bench guards these paths, and deletes a
    structural test as "redundant with the perf gate". Then BOTH are gone.

    So the comment now names the two tests that ARE the detectors, and this test makes
    those names load-bearing: rename or delete either and the reference dangles LOUDLY
    instead of decaying into a lie. (A prose cross-reference nobody checks is exactly
    the failure mode this task keeps re-finding — a claim of coverage that enumerates
    nothing.)
    """
    import re

    src = (Path(__file__).parent.parent / "scripts" / "benchmark.py").read_text(
        encoding="utf-8")
    referenced = set(re.findall(r"(tests/[\w/]+\.py)::(\w+)", src))
    assert referenced, (
        "scripts/benchmark.py no longer NAMES the structural tests that actually catch "
        "the M1/M2 regressions — the SLO buckets do not (4-6× headroom vs a 1.07× / "
        "1.75× regression). Re-state the boundary; do not silently drop it.")

    # The two the SLO comment's boundary statement depends on. Pinned by NAME so that
    # deleting the sentence is as red as deleting the test.
    must_name = {
        ("tests/test_health_denominators.py", "test_m1_statement_census_no_n_plus_one"),
        ("tests/test_trust_tier.py",
         "test_external_origin_sql_parses_the_blob_exactly_once"),
    }
    assert must_name <= referenced, must_name - referenced

    # …and every reference RESOLVES: the file exists and defines that test.
    root = Path(__file__).parent.parent
    for rel, name in sorted(referenced):
        path = root / rel
        assert path.is_file(), f"benchmark.py names a test file that does not exist: {rel}"
        body = path.read_text(encoding="utf-8")
        assert f"def {name}(" in body, (
            f"{rel}::{name} is named by scripts/benchmark.py as a REGRESSION DETECTOR "
            "the SLO buckets cannot replace, and it no longer exists. If it was "
            "deleted as redundant with the perf gate: it was not. Restore it, or "
            "restate what now guards that path.")


def test_unit_11_the_fat_provenance_walk_does_not_short_circuit(tmp_path):
    """The `wiki-search-metadata-trust-fat` op must time a FULL O(members) walk.

    H2 made the predicate walk INSIDE a list-valued provenance key — O(members) on such
    a row, where the pre-H2 form was O(1) *because it never looked inside* (the bug).
    Nothing benched it: the only list shape in the fixture had ONE member.

    `EXISTS` short-circuits on the FIRST external member, so a fixture with an
    http-looking member at index 0 would make a 10 000-member array cost exactly what a
    1-member one costs and the op would measure NOTHING. The proof that it does not is
    the row SURVIVING the `internal` floor: that can only happen after all members are
    walked and none is external.

    Anti-vacuity guard (the fixture must BE the state it claims): the members are
    counted OFF THE INDEXED ROW, not off the generator.
    """
    import json as _json

    root = tmp_path / "karpathy"
    generate_synthetic_vault(root, "k-fat", 20)
    repo = _index(tmp_path, root, "k-fat")

    def _trust(min_trust: str | None = "internal", limit: int = 20):
        return repo.search_pages(
            None, vaults=["k-fat"], where_fields=[("status", "active")],
            min_trust=min_trust, limit=limit)

    stats = plant_fat_provenance(repo, root, "k-fat", _trust)

    # Every fat page survived the floor ⇒ every member was walked, none was external.
    assert stats["trust_fat_pages"] == _BENCH_FAT_PAGES
    assert stats["trust_fat_members"] == _BENCH_FAT_MEMBERS
    assert stats["trust_fat_rows_internal"] == _BENCH_FAT_PAGES, (
        "a fat page did not survive the `internal` floor — the fixture contains an "
        "EXTERNAL member, so `EXISTS` short-circuits and the fat op is timing a "
        "1-member walk wearing a 10 000-member name")

    # The row really carries the array it claims to (fixture == state).
    row = repo._connect().execute(
        "SELECT frontmatter_json FROM pages WHERE vault_id = ? AND slug = ?",
        ("k-fat", "fat-provenance-00")).fetchone()
    assert row is not None, "the fat page was not indexed at all"
    members = _json.loads(row[0])["sources"]
    assert len(members) == _BENCH_FAT_MEMBERS
    assert not any(
        str(m.get("url", "") if isinstance(m, dict) else m).startswith("http")
        for m in members)
    # BOTH member arms are exercised — text scalars AND objects (`jm` and `jn`).
    assert any(isinstance(m, dict) for m in members)
    assert any(isinstance(m, str) for m in members)
    repo.close()


def test_unit_08_vacuous_run_fails_even_without_slo_enforcement(monkeypatch, capsys):
    """Fail-CLOSED wiring: a bench that examined nothing is BROKEN, not slow.

    `enforce_slos=False` waives the (machine-specific) thresholds — it must never
    waive the claim that the ops executed the code they are named after.
    """
    import scripts.benchmark as bench

    monkeypatch.setattr(bench, "_measure_trust_vacuity", lambda trust_search: {
        "trust_rows_unfloored": 0, "trust_rows_internal": 0, "trust_rows_floored": 0})
    ok = run_suite(30, enforce_slos=False)
    payload = json.loads(capsys.readouterr().out)
    assert ok is False
    assert payload["vacuity"]["vacuity_ok"] is False
    assert set(payload["vacuity"]["zero_counters"]) == {
        "trust_rows_floored", "trust_rows_internal"}
    # The LINT counters still moved — the failure is attributed to the right op.
    assert payload["vacuity"]["lint_ontology_edges_examined"] > 0


@pytest.mark.slow
def test_e2e_01_suite_runs_to_completion_100(capsys):
    """N=100 suite produces JSON, exits cleanly — and REACHED the changed code."""
    ok = run_suite(100, enforce_slos=False)
    assert ok is True   # TASK 061: False now means "vacuous run", not "SLO miss"
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["n_pages"] == 100
    ops = {r["op"] for r in payload["results"]}
    assert {"wiki-search", "wiki-search-metadata-trust",
            "wiki-search-metadata-trust-fat", "wiki-index-upsert",
            "wiki-index-render", "wiki-lint", "wiki-lint-rules",
            "wiki-health-coverage", "wiki-reindex-full",
            "wiki-reindex-delta"} <= ops
    # Every op that has an SLO bucket must have been COMPARED against it.
    for r in payload["results"]:
        assert r["slo_target_ms"] is not None, r["op"]
    vac = payload["vacuity"]
    assert vac["vacuity_ok"] is True
    assert vac["layout"] == "cybos" and vac["declared_rules"] == 24
    assert vac["lint_rules_with_matches"] == 24
    for counter in _VACUITY_COUNTERS:
        assert vac[counter] > 0, counter
    assert vac["typed_pages"] == 100


@pytest.mark.slow
def test_e2e_02_multivault_scaling_smoke(capsys):
    """Multi-vault smoke: 2 vaults × 20 pages."""
    ok = run_multivault_scaling(2, 20)
    assert ok is True
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["n_vaults"] == 2


@pytest.mark.slow
def test_e2e_03_cli_invocation(tmp_path):
    """CLI exit 0 with --n 50."""
    output = tmp_path / "bench.json"
    result = subprocess.run(
        [sys.executable, "-m", "scripts.benchmark",
         "--n", "50", "--output", str(output)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(output.read_text())
    assert payload["n_pages"] == 50
