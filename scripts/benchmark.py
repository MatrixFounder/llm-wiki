"""Phase 3a benchmark harness — synthetic vault generator + SLO latency runner
(task-001-33, R-14).

Generates synthetic vaults at N pages, exercises every Phase 3a operation,
measures per-op latency, and compares against SLO targets from TASK.md §5.1.

TASK 061 FIX-LOOP (vdd-multi H3) — **the bench could not execute the code TASK 061
changed.** Verified by grep, not by reasoning (this task's own lens):

  - `run_all_checks` ran over a vault generated as `_sources/page-NNNN.md` with no
    `layout:` in `WIKI_SCHEMA.md` ⇒ `resolve_layout_config` → **karpathy**. But
    `drift_rules` / `coverage_rules` / `ontology:` are declared in **`cybos.yaml`
    only** (`grep -ln "drift_rules\\|coverage_rules\\|^ontology:" scripts/wiki_index/
    layouts/*.yaml` → 1 file). So `check_lifecycle_drift_report` and
    `check_ontology_violations_report` both hit their `return [], None` early-out:
    **zero DAL calls, zero of the new denominator queries.** The 30 s `wiki-lint`
    SLO would have stayed green if those checks had been made 100× slower.
  - `search_pages("synthetic", …)` is the **FTS** branch with `min_trust=None`, so
    `_EXTERNAL_ORIGIN_SQL` was never even **compiled into** the statement.

Three ops close that hole — each measures a shape TASK 061 actually changed. The
THIRD exists because the first cut of this fix-loop shipped the first two and called
the hot paths covered; the census (`grep -n "def find_.*_report"` against the timed
ops) says otherwise:

  - **`wiki-lint-rules`** — `run_all_checks_report` over a **cybos** vault
    (`generate_typed_vault`) whose typed pages + typed EDGES make all 24 declared
    rules (3 coverage + 3 drift + 7 edge + 11 property) bind to a NON-EMPTY
    population. Kept as a SECOND vault in its OWN DB so the six pre-existing ops'
    numbers (and their SLO buckets) are untouched. Times `find_lifecycle_drift_report`
    + `find_ontology_violations_report`.
  - **`wiki-health-coverage`** — `find_coverage_gaps_report`, the THIRD denominator
    query: it rides `wiki-health coverage` (never benched), and M1's N+1 collapse
    rewrote it too.
    `tests/test_benchmark.py::test_unit_09_every_denominator_query_is_timed_by_some_op`
    makes that census a GATE.
  - **`wiki-search-metadata-trust`** — the metadata FULL-SCAN shape with the trust
    predicate compiled in: `search_pages(None, where_fields=[("status","active")],
    min_trust="internal")`.

And the bench now **proves it fired** rather than assuming it (the vacuity test that
is itself vacuous is the failure mode this whole task is about): `run_suite` emits a
`vacuity` block carrying the denominators the lint rules actually examined and the
row-count the trust floor actually removed, plus `vacuity_ok`. A vacuous bench is a
BROKEN bench, not an SLO miss — `run_suite` returns False on `not vacuity_ok`
**regardless of `enforce_slos`**.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import tempfile
import time
from datetime import date, datetime
from pathlib import Path

from scripts.wiki_index.layout import (
    CONCEPTS_SUBDIR,
    SCHEMA_FILE,
    SOURCES_SUBDIR,
)
from typing import Any, Callable

from scripts.wiki_index.layout_config import resolve_layout_config
from scripts.wiki_index.models import Vault
from scripts.wiki_index.reindex import reindex_delta, reindex_full
from scripts.wiki_index.rendering import render_index
from scripts.wiki_index.lint import run_all_checks, run_all_checks_report
from scripts.wiki_index.sqlite_repository import SQLiteRepository

# SLO table from TASK.md §5.1 (milliseconds).
#
# The six original buckets are TASK-002 §5.1 contract numbers — do not retune them.
# The TASK-061 buckets (`wiki-search-metadata-trust`, `wiki-search-metadata-trust-fat`,
# `wiki-lint-rules`, `wiki-health-coverage`) are NOT in that contract: they were set
# from the OBSERVED p95 at HEAD (3-invocation protocol, `docs/runbooks/perf-slo-gate.md`)
# with ~4-6× headroom at n=10k.
#
#            OBSERVED p95 @HEAD (2026-07-13, M1+M2+H2 landed)   BUCKET   headroom
#   trust        0.39ms /  2.1ms /  15.7ms  (100/1k/10k)      5/15/60      13×/7×/3.8×
#   trust-fat    17.0ms /  19.2ms /  32.6ms (100/1k/10k)     80/90/150    4.7×/4.7×/4.6×
#   lint-rules     28ms /   80ms /   780ms  (100/1k/10k)   150/400/2500   5.4×/5×/3.2×
#   health-cov    0.39ms /  1.8ms /  18.3ms (100/1k/10k)     5/15/80      13×/8×/4.4×
#
# `trust-fat` is `trust` re-run over the SAME query after `plant_fat_provenance` adds 4
# pages carrying a 10 000-member `sources:` array — the O(members) walk the H2 fix
# introduced (the pre-H2 predicate was O(1) on such a row *because it never looked
# inside*, which was the bug). It is nearly FLAT in n (17 → 19 → 33 ms) because its cost
# is dominated by the fixture's 40 000 member-rows, not by the page count: that IS the
# characterisation. The delta against `trust` at the same n is the price of a fat page
# on the hot search path.
#
# WHAT THESE BUCKETS ARE — and, more usefully, WHAT THEY ARE NOT (TASK 061 iteration-2,
# perf MED-1). An earlier draft of this comment claimed, in the imperative voice of a
# gate, that the buckets "CATCH the regressions they exist for: reverting
# `_EXTERNAL_ORIGIN_SQL` … blows the trust bucket; reinstating the per-rule COUNT N+1
# that M1 collapsed … blows the lint-rules AND health-coverage buckets". Do the
# arithmetic against the numbers printed above and that claim REFUTES ITSELF:
#
#   * reverting M2 costs **~7% MEASURED** (12.00 → 11.21 ms at n=10k). The pre-M2 form's
#     12 `json_extract` calls land on the SAME blob in the SAME row, and SQLite has had a
#     per-connection JSON parse cache since 3.42 — so they are 1 parse + 11 cheap path
#     walks, not 12 parses. (The perf critic's iteration-1 estimate — "~180 ms vs ~90 ms
#     against a 100 ms SLO" — was wrong by ~15×, and it RETRACTED it. The 100 ms SLO was
#     never at risk. M2 is still worth keeping: for the H2 fail-open fix, and for
#     FLATNESS IN KEY COUNT. Not for the latency.) A 3.8× bucket cannot see 1.07×.
#   * reverting M1 costs ~1.75-1.9× in STATEMENT COUNT (coverage 4 → 7, lint rules
#     25 → 38) — inside a 3.2×/4.4× bucket. And `run_all_checks_report` also runs
#     orphan-links and `check_drift`, the O(pages) file re-HASH sweep: at 10k pages that
#     ~780 ms is dominated by disk I/O and hashing, so ~25 SQL statements are a rounding
#     error inside it (P-10). You could TRIPLE the rule queries and p95 would barely
#     twitch.
#
# So — stated, rather than left merely true: these are **absolute-latency guards** with
# 4-6× headroom. They catch an ORDER-OF-MAGNITUDE blowup: a scan becoming a nested loop,
# an index vanishing, a per-row Python round-trip appearing inside a DAL method, a
# recursive `json_tree` descent replacing the fixed-depth member walk. They do **NOT**
# catch M1 or M2. They are deliberately NOT tightened to 1.3× either: SLO enforcement is
# off by default and the numbers are machine-specific, so a bucket sized to the noise
# floor is a flaky bucket, not a gate.
#
# THE ACTUAL M1/M2 REGRESSION DETECTORS ARE STRUCTURAL TESTS — both mutation-verified.
# Named here so nobody deletes one as "redundant with the perf gate": it is not
# redundant, it is the ONLY thing watching that path.
#
#   tests/test_health_denominators.py::test_m1_statement_census_no_n_plus_one
#       — counts the statements each report issues via `sqlite3.set_trace_callback`
#         (exact 4 / 5 / 20). Reinstating the per-rule COUNT is instantly red.
#   tests/test_trust_tier.py::test_external_origin_sql_parses_the_blob_exactly_once
#       — `json_each(p.frontmatter_json)` appears EXACTLY once, `json_extract` ZERO
#         times, no `json_tree`, and the LIKE count is CONSTANT in the key count.
#         Reverting to the per-key `json_extract` form is instantly red.
#
# `tests/test_benchmark.py::test_unit_10_the_named_regression_detectors_exist` keeps
# those two references honest: rename or delete either test and the bench turns red
# rather than quietly ceasing to name a detector that no longer exists.
#
# Those are the regression detectors. This is the stopwatch. Different jobs.
SLOS = {
    "wiki-search": {100: 30, 1000: 50, 10000: 100},
    "wiki-search-metadata-trust": {100: 5, 1000: 15, 10000: 60},
    "wiki-search-metadata-trust-fat": {100: 80, 1000: 90, 10000: 150},
    "wiki-index-upsert": {100: 50, 1000: 100, 10000: 100},
    "wiki-index-render": {100: 200, 1000: 1000, 10000: 5000},
    "wiki-lint": {100: 500, 1000: 2000, 10000: 30000},
    "wiki-lint-rules": {100: 150, 1000: 400, 10000: 2500},
    "wiki-health-coverage": {100: 5, 1000: 15, 10000: 80},
    "wiki-reindex-full": {100: 2000, 1000: 20000, 10000: 180000},
    "wiki-reindex-delta": {100: 100, 1000: 500, 10000: 2000},
}


# TASK 061 fix-loop (H3) — the frontmatter the `wiki-search-metadata-trust` op needs.
# A metadata filter that matches NOTHING would let SQLite skip the trust predicate
# entirely (a vacuous bench measuring a query that returns 0 rows), so `status` is
# stamped on every page and is `active` on a third of them.
#
# The period is **3** against `_BENCH_PROVENANCE`'s **4** deliberately: coprime, so all
# 12 (status × provenance) combinations occur. The first cut used period 2 and the
# `internal` shape landed only on odd `i` — i.e. NEVER on an `active` page — so the
# floored query returned 0 rows: the predicate rejected the whole result set instead of
# DISCRIMINATING within it. It filtered, so it was demonstrably compiled in and run,
# but "everything is external" is not a shape any real vault has, and a bench whose
# query returns nothing is one refactor away from being vacuous again. Pinned by the
# `trust_rows_internal` counter in `_VACUITY_COUNTERS`.
_BENCH_STATUSES = ("active", "draft", "superseded")

# The provenance shapes cycled over the source pages, one per `i % 4`. Three of the
# four are EXTERNAL — one per VALUE SHAPE the `_EXTERNAL_ORIGIN_SQL` predicate walks
# (scalar / case-variant key / list-of-objects), so the bench exercises the json_each
# walk itself and not just its cheapest branch. The 4th carries no provenance key at
# all ⇒ `internal` ⇒ it is what survives the `--min-trust internal` floor.
_BENCH_PROVENANCE = (
    "source: https://example.com/p-{i}\n",                 # scalar, canonical key
    "Source: https://example.com/p-{i}\n",                 # R-061-3 case variant
    "sources:\n  - url: https://example.com/p-{i}\n",      # H2 list-of-objects shape
    "",                                                    # internal (no provenance)
)

# ---------------------------------------------------------------------------
# TASK 061 iteration-2 (perf LOW) — the FAT provenance array
# ---------------------------------------------------------------------------
# The H2 fix made the predicate walk INSIDE a list-valued provenance key, so its per-row
# cost is O(members) on a row carrying one. The pre-H2 form was O(1) on such a row —
# because it never looked inside, which WAS the bug. Nothing bounded or benched that
# walk: `_BENCH_PROVENANCE`'s list shape has ONE member, and the live vault's 81/3267
# provenance-bearing pages all carry small arrays. "Small today" is a fact about the
# corpus, not a property of the query — so the hot search path is now also measured with
# a page that is NOT small.
#
# `_BENCH_FAT_PAGES` pages, each carrying `_BENCH_FAT_MEMBERS` members, are planted into
# the karpathy vault AFTER every other op on it has been timed (so the six TASK-002
# buckets keep their historical numbers byte-for-byte), and the trust query is re-timed
# as `wiki-search-metadata-trust-fat`. The delta between the two ops IS the
# characterisation of the walk.
#
# NONE of the members is external, deliberately: `EXISTS` short-circuits on the FIRST
# external member, so an http-looking member at index 0 would make a 10 000-member array
# cost exactly what a 1-member one costs, and the op would measure NOTHING (this task's
# disease, in a fixture). All-internal ⇒ the walk runs to the end ⇒ the row is KEPT ⇒
# `trust_fat_rows_internal` counts it. That counter is in `_VACUITY_COUNTERS`: make the
# members external and the bench turns red instead of quietly timing a short-circuit.
# Members alternate text scalar / object so BOTH member arms (`jm` text, `jn` object)
# are walked, not just the cheap one.
_BENCH_FAT_PAGES = 4
_BENCH_FAT_MEMBERS = 10_000


def _fat_provenance_page(i: int) -> str:
    """One page with a `sources:` array of `_BENCH_FAT_MEMBERS` NON-external members."""
    members = "".join(
        (f"  - ref-{i}-{j:05d}\n" if j % 2 == 0
         else f"  - url: ref-{i}-{j:05d}\n")
        for j in range(_BENCH_FAT_MEMBERS)
    )
    return (
        "---\n"
        "type: summary\n"
        f"title: Fat Provenance {i}\n"
        f"date: '2026-05-{(i % 28) + 1:02d}'\n"
        "tags: [bench, synth, fat]\n"
        # `active` ⇒ it survives the metadata filter and REACHES the trust predicate.
        "status: active\n"
        f"sources:\n{members}"
        "---\n"
        f"# Fat Provenance {i}\n\nSynthetic page with a {_BENCH_FAT_MEMBERS}-member "
        "provenance array.\n"
    )


def generate_synthetic_vault(
    target_dir: Path,
    vault_id: str,
    n_pages: int,
    *,
    with_wikilinks: bool = True,
    seed: int = 42,
) -> None:
    """Generate `<target_dir>/_sources/page-NNNN.md` plus a WIKI_SCHEMA.md.

    Karpathy layout (no `layout:` key ⇒ `resolve_layout_config` defaults to karpathy)
    — the vault the six original ops measure. TASK 061 adds `status:` + a cycling
    provenance key so the `wiki-search-metadata-trust` op has a non-empty metadata
    predicate AND a real external/internal mix to floor (see `_BENCH_PROVENANCE`).
    The typed-knowledge rules are a DIFFERENT layout — see `generate_typed_vault`.

    Deterministic for fixed `seed`.
    """
    rng = random.Random(seed)
    target_dir.mkdir(parents=True, exist_ok=True)
    sources = target_dir / SOURCES_SUBDIR
    sources.mkdir(exist_ok=True)
    concepts = target_dir / CONCEPTS_SUBDIR
    concepts.mkdir(exist_ok=True)
    (target_dir / SCHEMA_FILE).write_text(
        f"---\nvault_id: {vault_id}\nschema_version: '2.0'\n---\n"
        f"# {vault_id}\n\nSynthetic vault for benchmarking.\n"
    )

    # Seed a small concept pool to wikilink against.
    n_concepts = max(10, n_pages // 50)
    for i in range(n_concepts):
        (concepts / f"concept-{i:04d}.md").write_text(
            f"---\ntype: concept\ntitle: Concept {i}\n---\n"
            f"# Concept {i}\n\nSynthetic concept body.\n"
        )

    for i in range(n_pages):
        body_parts = [
            f"# Synthetic Page {i}", "",
            f"Body paragraph for page-{i:04d}. " * 4,
            "",
        ]
        if with_wikilinks:
            n_links = rng.randint(1, 3)
            for _ in range(n_links):
                target = rng.randint(0, n_concepts - 1)
                body_parts.append(f"See [[concept-{target:04d}]] for details.")
        body = "\n".join(body_parts) + "\n"
        fm = (
            "---\n"
            f"type: summary\n"
            f"title: Synthetic Page {i}\n"
            f"date: '2026-05-{(i % 28) + 1:02d}'\n"
            f"tags: [bench, synth, page-{i % 10}]\n"
            f"status: {_BENCH_STATUSES[i % len(_BENCH_STATUSES)]}\n"
            + _BENCH_PROVENANCE[i % len(_BENCH_PROVENANCE)].format(i=i)
            + "---\n"
        )
        (sources / f"page-{i:04d}.md").write_text(fm + body)


# ---------------------------------------------------------------------------
# TASK 061 fix-loop (H3) — the TYPED (cybos) bench vault
# ---------------------------------------------------------------------------
# The 24 rules `wiki-lint` / `wiki-health` declare live in ONE layout:
#
#   $ grep -ln "drift_rules\|coverage_rules\|^ontology:" scripts/wiki_index/layouts/*.yaml
#   scripts/wiki_index/layouts/cybos.yaml          # ← and nothing else
#
# so a bench vault that resolves to karpathy can NEVER execute a single one of them
# (both checks `return [], None` before their first DAL call). This core set makes
# every rule FAMILY bind to a non-empty population — and, deliberately, makes each
# family's `matched` non-zero too: a fixture with typed pages but no typed EDGES
# would leave `matched: 0` and "prove" non-vacuity while proving nothing (the
# R-061-2 fixture lesson, restated one layer out).
#
#   drift      (3 rules) — dec-core-stale / dec-core-voided / wf-core-stale carry the edge
#   coverage   (3 rules) — req-core-gap / cap-core-gap / fact-core-nosrc are real gaps
#   edge       (7 rules) — implements/supersedes/causes/invalidates/activates/uses/owns
#                          are ALL authored, so `edges_examined` ⊇ one row per rule
#   property  (11 rules) — every class with a `status` enum carries a scalar `status`
#
# Planted contradictions (so the FINDINGS are non-zero as well as the denominators):
# risk-core-bad `implements` (domain violation), dec-core-badrange `implements` a tool
# (range violation), dec-core-badstatus (property enum violation).
_TYPED_CORE: dict[str, str] = {
    # --- decisions: drift + the edge spine ---
    "decisions/dec-core-stale.md": "---\ntype: decision\ntitle: Dec Stale\nstatus: accepted\nsuperseded_by: [[dec-core-new]]\n---\nStale decision body.\n",
    "decisions/dec-core-new.md": "---\ntype: decision\ntitle: Dec New\nstatus: accepted\nsupersedes: [[dec-core-old]]\nimplements: [[req-core-open]]\n---\nNew decision body.\n",
    "decisions/dec-core-old.md": "---\ntype: decision\ntitle: Dec Old\nstatus: accepted\n---\nSuperseded via the DERIVED inverse edge.\n",
    "decisions/dec-core-voided.md": "---\ntype: decision\ntitle: Dec Voided\nstatus: accepted\ninvalidated_by: [[inc-core-1]]\n---\nVoided but still live.\n",
    "decisions/dec-core-badstatus.md": "---\ntype: decision\ntitle: Dec BadStatus\nstatus: pending\n---\nProperty-enum violation (`pending` is not in the decision enum).\n",
    "decisions/dec-core-badrange.md": "---\ntype: decision\ntitle: Dec BadRange\nstatus: proposed\nimplements: [[tool-core-1]]\n---\nRange violation: implements.to = [requirement, capability].\n",
    # --- incidents / events / risks: causes / invalidates / activates ---
    "incidents/inc-core-1.md": "---\ntype: incident\ntitle: Inc One\nstatus: resolved\ninvalidates: [[dec-core-voided]]\ncauses: [[inc-core-2]]\n---\nIncident body.\n",
    "incidents/inc-core-2.md": "---\ntype: incident\ntitle: Inc Two\nstatus: open\n---\nIncident body.\n",
    "events/evt-core-1.md": "---\ntype: event\ntitle: Evt One\nactivates: [[dec-core-new]]\n---\nEvent body.\n",
    "risks/risk-core-1.md": "---\ntype: risk\ntitle: Risk One\nstatus: open\ncauses: [[inc-core-2]]\n---\nRisk body.\n",
    "risks/risk-core-bad.md": "---\ntype: risk\ntitle: Risk Bad\nstatus: open\nimplements: [[req-core-gap]]\n---\nDomain violation: implements.from = [decision, task, agent, tool].\n",
    # --- workflows: drift + uses ---
    "workflows/wf-core-stale.md": "---\ntype: workflow\ntitle: WF Stale\nstatus: active\nsuperseded_by: [[wf-core-new]]\n---\nStale workflow.\n",
    "workflows/wf-core-new.md": "---\ntype: workflow\ntitle: WF New\nstatus: active\nuses: [[tool-core-1]]\n---\nCurrent workflow.\n",
    # --- coverage: requirements / capabilities / facts ---
    "requirements/req-core-open.md": "---\ntype: requirement\ntitle: Req Open\nstatus: draft\n---\nCovered by dec-core-new's `implements` (derived `implemented-by`).\n",
    "requirements/req-core-gap.md": "---\ntype: requirement\ntitle: Req Gap\nstatus: draft\n---\nNothing implements this — a coverage gap.\n",
    "capabilities/cap-core-ok.md": "---\ntype: capability\ntitle: Cap OK\nstatus: active\n---\nImplemented by agt-core-1.\n",
    "capabilities/cap-core-gap.md": "---\ntype: capability\ntitle: Cap Gap\nstatus: active\n---\nNo agent provides this — a coverage gap.\n",
    "facts/fact-core-withsrc.md": "---\ntype: fact\ntitle: Fact WithSrc\nsource: \"https://example.com/f\"\n---\nA sourced fact.\n",
    "facts/fact-core-nosrc.md": "---\ntype: fact\ntitle: Fact NoSrc\n---\nA fact with no cited source — a coverage gap.\n",
    # --- agent memory: owns / uses / implements ---
    "agents/agt-core-1.md": "---\ntype: agent\ntitle: Agent One\nstatus: active\nuses: [[tool-core-1]]\nowns: [[wf-core-new]]\nimplements: [[cap-core-ok]]\n---\nAgent body.\n",
    "tools/tool-core-1.md": "---\ntype: tool\ntitle: Tool One\nstatus: active\n---\nTool body.\n",
    "executions/exe-core-1.md": "---\ntype: execution\ntitle: Exe One\nstatus: success\nuses: [[tool-core-1]]\n---\nExecution body.\n",
    "patterns/pat-core-1.md": "---\ntype: pattern\ntitle: Pat One\nstatus: active\n---\nPattern body.\n",
    "hypotheses/hyp-core-1.md": "---\ntype: hypothesis\ntitle: Hyp One\nstatus: proposed\n---\nHypothesis body.\n",
}

# Padding archetypes cycled to scale the typed vault to N. `(subdir, prefix, type,
# status, edge_fm)` — `{prev}` binds to the previous page of the SAME archetype, so
# each class grows its own edge chain and the drift/coverage/edge populations all
# scale with N (a padding set that added only ISOLATED pages would grow
# `pages_examined` while leaving `matched` pinned at the core's constant).
_TYPED_PAD: tuple[tuple[str, str, str, str, str], ...] = (
    ("decisions", "dec-pad", "decision", "accepted", "supersedes: [[{prev}]]\n"),
    ("requirements", "req-pad", "requirement", "draft", ""),
    ("capabilities", "cap-pad", "capability", "active", ""),
    ("facts", "fact-pad", "fact", "", "source: \"https://example.com/{slug}\"\n"),
    ("workflows", "wf-pad", "workflow", "active", "superseded_by: [[{prev}]]\n"),
    ("agents", "agt-pad", "agent", "active", "uses: [[tool-core-1]]\n"),
    ("tools", "tool-pad", "tool", "active", ""),
    ("incidents", "inc-pad", "incident", "open", "causes: [[inc-core-2]]\n"),
)

# An out-of-enum `status` every Nth padded page keeps the property-rule FINDINGS
# non-zero at scale (not just the denominator).
_TYPED_BAD_STATUS_EVERY = 17


def generate_typed_vault(
    target_dir: Path, vault_id: str, n_pages: int, *, seed: int = 42,
) -> int:
    """Generate a **cybos**-layout typed-knowledge vault and return the pages written.

    `WIKI_SCHEMA.md` carries `layout: cybos` — the ONE built-in layout declaring
    `drift_rules` / `coverage_rules` / `ontology:`. Without it the R-15/R-19 checks
    short-circuit before their first DAL call and the lint bench measures nothing
    (the H3 finding).

    Page count is `max(n_pages, len(_TYPED_CORE))`: the core archetypes are ALWAYS
    written, so the rules bind to a non-empty population even at `--n 25`. Bodies
    carry a plain `[[wikilink]]` so `page_entity_refs` is dominated by `mentioned`
    rows — the LIVE shape (8836 `mentioned`, 0 typed), which is precisely the haystack
    `edges_examined` has to count the declared edge types out of.
    """
    rng = random.Random(seed ^ 0xC1B0)
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / SCHEMA_FILE).write_text(
        f"---\nvault_id: {vault_id}\nschema_version: '2.0'\nlayout: cybos\n---\n"
        f"# {vault_id}\n\nSynthetic TYPED vault (cybos) — benchmarks the R-15/R-19 rules.\n"
    )
    core_slugs = [Path(rel).stem for rel in _TYPED_CORE]

    def _write(rel: str, text: str) -> None:
        p = target_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    for rel, content in _TYPED_CORE.items():
        _write(rel, content)
    written = len(_TYPED_CORE)

    prev_of: dict[str, str] = {}
    for i in range(len(_TYPED_CORE), n_pages):
        subdir, prefix, ptype, status, edge_fm = _TYPED_PAD[i % len(_TYPED_PAD)]
        slug = f"{prefix}-{i:05d}"
        prev = prev_of.get(prefix)
        # No previous page of this archetype yet ⇒ no edge to author (a dangling
        # target would be an ORPHAN ref, which the range check skips — it would
        # inflate `edges_examined` with rows no rule can judge).
        needs_prev = "{prev}" in edge_fm
        edge = (edge_fm.format(prev=prev, slug=slug)
                if edge_fm and (prev is not None or not needs_prev) else "")
        if status:
            bad = (i % _TYPED_BAD_STATUS_EVERY == 0)
            status_fm = f"status: {'pending-review' if bad else status}\n"
        else:
            status_fm = ""
        mention = core_slugs[rng.randrange(len(core_slugs))]
        _write(f"{subdir}/{slug}.md", (
            f"---\ntype: {ptype}\ntitle: {prefix.upper()} {i}\n"
            f"{status_fm}{edge}---\n"
            f"Synthetic typed body for {slug}. See [[{mention}]] for context.\n"
        ))
        prev_of[prefix] = slug
        written += 1
    return written


def measure(
    op_name: str,
    callable_: Callable[[], Any],
    runs: int = 5,
) -> dict[str, Any]:
    """Execute `callable_` `runs` times; return latency stats in ms.

    For ``runs`` < 20 the p95 field falls back to ``max_ms`` (a fair
    upper-bound estimate) because the empirical 95th percentile is
    ill-defined on small samples. The ``runs`` field is always reported so
    callers can judge confidence.
    """
    timings_ms: list[float] = []
    for _ in range(runs):
        t0 = time.perf_counter()
        callable_()
        timings_ms.append((time.perf_counter() - t0) * 1000.0)
    timings_ms.sort()
    if runs >= 20:
        p95 = statistics.quantiles(timings_ms, n=20)[18]
    else:
        # Under-sampled: report worst observed as an honest upper bound.
        p95 = max(timings_ms)
    return {
        "op": op_name,
        "runs": runs,
        "min_ms": round(min(timings_ms), 3),
        "p50_ms": round(statistics.median(timings_ms), 3),
        "p95_ms": round(p95, 3),
        "max_ms": round(max(timings_ms), 3),
    }


def _check_slo(
    op: str, n_pages: int, p95_ms: float
) -> tuple[bool, float | None]:
    if op not in SLOS:
        return True, None
    bucket = SLOS[op].get(n_pages)
    if bucket is None:
        return True, None
    return p95_ms <= bucket, float(bucket)


# The counters a NON-vacuous run must have moved. Each is a claim the bench makes
# about ITSELF, checked against the run — not an assumption. `>= 1` on every one of
# them is what distinguishes "the rules fired and were fast" from "the rules never
# ran and the SLO stayed green because nothing happened" (the H3 finding).
_VACUITY_COUNTERS: tuple[str, ...] = (
    "lint_drift_pages_examined",
    "lint_coverage_pages_examined",
    "lint_ontology_edges_examined",
    "lint_ontology_property_pages_examined",
    "lint_rules_with_matches",
    # BOTH sides of the trust predicate: rows it REMOVED (⇒ it was compiled in and
    # evaluated) AND rows it KEPT (⇒ it discriminates, rather than rejecting the whole
    # result set — see `_BENCH_STATUSES`). Either one alone can be satisfied by a
    # degenerate vault.
    "trust_rows_floored",
    "trust_rows_internal",
    # The FAT-array walk ran to the END (TASK 061 iteration-2 / perf LOW): a fat page
    # survives the floor only if all `_BENCH_FAT_MEMBERS` members were walked and none
    # was external. 0 here = `wiki-search-metadata-trust-fat` is timing a short-circuit
    # — a number about a walk that did not happen.
    "trust_fat_rows_internal",
)


# -----------------------------------------------------------------------------
# The vacuity probes. BOTH take the TIMED OP'S OWN CALLABLE — never a query written
# beside it.
#
# The first cut of this fix-loop got that wrong, and it is worth stating plainly
# because it is the SAME failure one level in: the probes issued their own
# `search_pages(...)` / `run_all_checks_report(...)` calls with the arguments the op
# was *supposed* to use. So a mutation of the timed op — someone "simplifying"
# `min_trust="internal"` back to `None`, or repointing the lint lambda at the karpathy
# vault — would have left `vacuity_ok: true`: a proof about a query NOBODY TIMES,
# certifying an op it never touched. Passing the op's closure in makes the coupling
# structural: the thing measured and the thing proven are one object.
# -----------------------------------------------------------------------------

def _measure_rule_vacuity(
    lint_rules: Callable[[], Any], repo: SQLiteRepository,
    vault_id: str, vault_root: Path,
) -> dict[str, Any]:
    """PROVE the lint rules fired — do not assume the layout changed.

    `lint_rules` is the `wiki-lint-rules` op's OWN callable (see above): its report is
    what the denominators are read from, so a bench pointed at a rule-free layout
    reports zeros here instead of a fast, empty, green run. `find_coverage_gaps_report`
    is probed alongside — coverage rides `wiki-health`, not lint, but it is the third
    population TASK 061 gave a denominator to, and it is just as unreachable from a
    karpathy vault.
    """
    report = lint_rules()
    denom = report.denominators.get(vault_id, {})
    drift = denom.get("lifecycle-drift", {})
    ont = denom.get("ontology-violation", {})
    config = resolve_layout_config(vault_root)
    cov = repo.find_coverage_gaps_report(vault_id, list(config.coverage_rules))
    by_rule = list(drift.get("by_rule", [])) + list(ont.get("by_rule", []))
    matched = sum(1 for s in by_rule if int(s.get("matched", 0)) > 0)
    matched += sum(1 for s in cov.rule_stats if s.matched > 0)
    return {
        "layout": config.layout,
        "declared_rules": (len(config.drift_rules) + len(config.coverage_rules)
                           + (len(config.ontology.edges) + len(config.ontology.properties)
                              if config.ontology else 0)),
        "lint_drift_pages_examined": int(drift.get("pages_examined", 0)),
        "lint_coverage_pages_examined": cov.pages_examined,
        "lint_ontology_edges_examined": int(ont.get("edges_examined", 0)),
        "lint_ontology_property_pages_examined":
            int(ont.get("property_pages_examined", 0)),
        "lint_rules_with_matches": matched,
        "lint_issues": len(report.issues),
        "coverage_gaps": len(cov.gaps),
    }


def _measure_trust_vacuity(
    trust_search: Callable[..., list[Any]],
) -> dict[str, Any]:
    """PROVE the `min_trust` predicate was compiled in AND evaluated — by counting the
    rows it REMOVED, through the TIMED OP'S OWN closure (see above).

    `trust_search` is called twice: once as the op runs it (floor ON) and once with the
    floor OFF. A delta of 0 means the timed op is measuring a predicate that touches
    nothing — including the case where someone drops `min_trust` from the op entirely,
    which is exactly the pre-061 bench shape this fix-loop exists to make impossible.
    `limit` is raised so the two counts are the true pre-LIMIT populations, not two
    capped 20s that look equal.
    """
    big = 1_000_000
    floored = trust_search(limit=big)
    unfloored = trust_search(min_trust=None, limit=big)
    return {
        "trust_rows_unfloored": len(unfloored),
        "trust_rows_internal": len(floored),
        "trust_rows_floored": len(unfloored) - len(floored),
    }


def plant_fat_provenance(
    repo: SQLiteRepository, vault_root: Path, vault_id: str,
    trust_search: Callable[..., list[Any]],
) -> dict[str, Any]:
    """Plant the fat-provenance pages and PROVE the walk ran to the END (perf LOW).

    Called AFTER every karpathy op is timed and after `_measure_trust_vacuity`, so the
    six TASK-002 buckets and the trust-floor counters are computed over the historical
    population; the pages then exist for the `wiki-search-metadata-trust-fat` op only.

    The proof is the `internal` row-count DELTA across the planting, measured through
    the timed op's OWN closure: a fat page survives the `--min-trust internal` floor
    **iff** the predicate walked all `_BENCH_FAT_MEMBERS` members without finding an
    external one. A short-circuiting fixture (any http-looking member) would leave the
    delta at 0 ⇒ `trust_fat_rows_internal: 0` ⇒ `vacuity_ok: false` — a fat op secretly
    timing a 1-member walk fails loudly instead of reporting a fast green.
    """
    from scripts.wiki_index.normalization import normalize_frontmatter
    from scripts.wiki_index.reindex import _build_page
    from scripts.wiki_source.base import SourceItem
    from scripts.wiki_source.manual import ManualSourceAdapter

    big = 1_000_000
    before = len(trust_search(limit=big))

    adapter = ManualSourceAdapter()
    for i in range(_BENCH_FAT_PAGES):
        path = vault_root / SOURCES_SUBDIR / f"fat-provenance-{i:02d}.md"
        path.write_text(_fat_provenance_page(i), encoding="utf-8")
        item = SourceItem(kind="manual", source_path=path,
                          vault_root=vault_root, vault_id=vault_id)
        out = adapter.fetch(item)
        updated_fm, db_type = normalize_frontmatter(out.frontmatter)
        repo.upsert_page(_build_page(
            out, vault_id, db_type, path, vault_root, updated_fm))

    after = len(trust_search(limit=big))
    return {
        "trust_fat_pages": _BENCH_FAT_PAGES,
        "trust_fat_members": _BENCH_FAT_MEMBERS,
        "trust_fat_rows_internal": after - before,
    }


def run_suite(n_pages: int, output_json_path: Path | None = None,
              enforce_slos: bool = False, seed: int = 42) -> bool:
    """Build the synthetic vaults, run the ten operations, return the verdict.

    Two vaults, two DBs (TASK 061 fix-loop / H3):

      - a **karpathy** vault (`generate_synthetic_vault`) — the six original ops, plus
        `wiki-search-metadata-trust` (the metadata full-scan shape with the
        derived-trust predicate compiled in) and `wiki-search-metadata-trust-fat` (the
        same query, re-timed after `plant_fat_provenance` adds the O(members) list shape
        the H2 fix introduced and nothing measured);
      - a **cybos** vault (`generate_typed_vault`) in its OWN DB — `wiki-lint-rules`
        and `wiki-health-coverage`, the only shape in which the 24 declared
        drift/coverage/ontology rules can execute at all. A separate DB keeps the six
        original ops' numbers (and their SLO buckets) byte-for-byte comparable with
        every run before this one.

    The return value is `False` when the run was **vacuous** (a rule population or the
    trust-floor delta came back 0) — regardless of `enforce_slos`, because a bench that
    cannot execute the code it names is broken, not slow. `enforce_slos` additionally
    folds in the per-op SLO verdicts.

    Uses a temp dir so each invocation is hermetic. ``seed`` propagates to the
    mutator RNG so two runs with the same seed exercise the same workload.
    """
    results: list[dict[str, Any]] = []
    all_pass = True
    mutator_rng = random.Random(seed ^ 0xBEEF)

    with tempfile.TemporaryDirectory() as tmp:
        vault_root = Path(tmp) / "vault"
        db_path = Path(tmp) / "bench.db"
        vault_id = "bench-vault"

        generate_synthetic_vault(vault_root, vault_id, n_pages, seed=seed)

        repo = SQLiteRepository(db_path)
        repo.apply_schema()
        repo.register_vault(Vault(
            vault_id=vault_id, name=vault_id, root_path=vault_root,
            schema_version="2.0", registered_at=datetime(2026, 5, 26),
        ))

        # reindex --full (also seeds the DB for subsequent ops)
        full = measure("wiki-reindex-full",
                       lambda: reindex_full(repo, vault_id), runs=1)
        results.append(full)

        # wiki-search
        search = measure(
            "wiki-search",
            lambda: repo.search_pages("synthetic", vaults=[vault_id]),
            runs=5,
        )
        results.append(search)

        # wiki-search-metadata-trust (TASK 061 fix-loop / H3) — the ONLY op that
        # compiles `_EXTERNAL_ORIGIN_SQL` into the statement. `query=None` selects the
        # metadata FULL-SCAN branch (no FTS candidate-set narrowing to hide the
        # per-row json_each walk behind), and `min_trust="internal"` prepends
        # `AND NOT <external-origin>` to the WHERE. The `wiki-search` op above is the
        # FTS branch with `min_trust=None`: it cannot execute one byte of this.
        #
        # ONE closure, timed AND probed (`_measure_trust_vacuity` takes it): the query
        # the bench proves is filtering is, by construction, the query the bench times.
        def _trust_search(
            min_trust: str | None = "internal", limit: int = 20,
        ) -> list[Any]:
            return repo.search_pages(
                None, vaults=[vault_id], where_fields=[("status", "active")],
                min_trust=min_trust, limit=limit)

        trust_search = measure(
            "wiki-search-metadata-trust", _trust_search, runs=5)
        results.append(trust_search)

        # wiki-index-upsert (one fresh page mutation)
        new_page = vault_root / SOURCES_SUBDIR / "bench-mutator.md"
        from scripts.wiki_source.base import SourceItem
        from scripts.wiki_source.manual import ManualSourceAdapter
        from scripts.wiki_index.normalization import normalize_frontmatter
        from scripts.wiki_index.reindex import _build_page

        adapter = ManualSourceAdapter()

        def _upsert_once() -> None:
            new_page.write_text(
                "---\ntype: summary\ntitle: Mutator\n"
                f"date: '2026-05-26'\ntags: [bench]\n---\n"
                f"# Mutator {mutator_rng.random()}\n"
            )
            item = SourceItem(kind="manual", source_path=new_page,
                              vault_root=vault_root, vault_id=vault_id)
            out = adapter.fetch(item)
            updated_fm, db_type = normalize_frontmatter(out.frontmatter)
            page = _build_page(out, vault_id, db_type, new_page, vault_root,
                               updated_fm)
            repo.upsert_page(page)

        upsert = measure("wiki-index-upsert", _upsert_once, runs=5)
        results.append(upsert)

        # wiki-index-render
        render = measure(
            "wiki-index-render",
            lambda: render_index(repo, vault_id),
            runs=3,
        )
        results.append(render)

        # wiki-lint
        lint = measure(
            "wiki-lint",
            lambda: run_all_checks(repo, vaults=[vault_id]),
            runs=3,
        )
        results.append(lint)

        # wiki-reindex --delta (no changes)
        delta = measure(
            "wiki-reindex-delta",
            lambda: reindex_delta(repo, vault_id),
            runs=3,
        )
        results.append(delta)

        vacuity: dict[str, Any] = _measure_trust_vacuity(_trust_search)

        # wiki-search-metadata-trust-fat (TASK 061 iteration-2 / perf LOW) — the SAME
        # closure, re-timed over a population that now also holds `_BENCH_FAT_PAGES`
        # pages carrying a `_BENCH_FAT_MEMBERS`-member provenance array. H2 made the
        # predicate walk INSIDE a list value, so its per-row cost is O(members) on such
        # a row; the only list shape benched until now had ONE member. Planted HERE,
        # after every other karpathy op is timed, so those ops' numbers are untouched.
        vacuity.update(
            plant_fat_provenance(repo, vault_root, vault_id, _trust_search))
        results.append(
            measure("wiki-search-metadata-trust-fat", _trust_search, runs=5))
        repo.close()

        # ---- wiki-lint-rules: the SAME `run_all_checks` code, over a vault whose
        # layout actually DECLARES the 24 drift/coverage/ontology rules (cybos). Own
        # vault, own DB — the six ops above keep their historical numbers.
        typed_root = Path(tmp) / "typed-vault"
        typed_db = Path(tmp) / "bench-rules.db"
        typed_id = "bench-typed"
        typed_pages = generate_typed_vault(typed_root, typed_id, n_pages, seed=seed)

        trepo = SQLiteRepository(typed_db)
        trepo.apply_schema()
        trepo.register_vault(Vault(
            vault_id=typed_id, name=typed_id, root_path=typed_root,
            schema_version="2.0", registered_at=datetime(2026, 5, 26),
        ))
        reindex_full(trepo, typed_id)   # untimed — `wiki-reindex-full` is measured above

        # Same discipline as the trust op: ONE closure, timed AND probed.
        def _lint_rules() -> Any:
            return run_all_checks_report(trepo, vaults=[typed_id])

        lint_rules = measure("wiki-lint-rules", _lint_rules, runs=3)
        results.append(lint_rules)

        # wiki-health-coverage — the THIRD denominator query. Found by CENSUSING the
        # diff, not by reasoning about it:
        #
        #   $ grep -n "def find_.*_report" .../\_health_rules.py
        #   find_lifecycle_drift_report      → timed by wiki-lint-rules
        #   find_ontology_violations_report  → timed by wiki-lint-rules
        #   find_coverage_gaps_report        → timed by NOTHING          ← here
        #
        # It rides `wiki-health coverage`, which has never had a bench op at all — and
        # M1's N+1 collapse rewrote it too (its own comment: "`wiki-health coverage`
        # went 3 → 7 statements, a >2× regression of the whole command"). Timing the
        # other two and calling the hot paths covered would have been this task's
        # fractal, in the very fix for it.
        cov_rules = list(resolve_layout_config(typed_root).coverage_rules)

        def _health_coverage() -> Any:
            return trepo.find_coverage_gaps_report(typed_id, cov_rules)

        results.append(measure("wiki-health-coverage", _health_coverage, runs=3))

        vacuity.update(
            _measure_rule_vacuity(_lint_rules, trepo, typed_id, typed_root))
        vacuity["typed_pages"] = typed_pages
        trepo.close()

    vacuity_ok = all(int(vacuity.get(k, 0)) > 0 for k in _VACUITY_COUNTERS)
    vacuity["vacuity_ok"] = vacuity_ok
    if not vacuity_ok:
        vacuity["zero_counters"] = [
            k for k in _VACUITY_COUNTERS if int(vacuity.get(k, 0)) <= 0]

    # SLO comparison
    for r in results:
        ok, target = _check_slo(r["op"], n_pages, r["p95_ms"])
        r["slo_target_ms"] = target
        r["slo_ok"] = ok
        if not ok:
            all_pass = False

    payload = {
        "n_pages": n_pages,
        "results": results,
        "all_pass": all_pass,
        "enforce_slos": enforce_slos,
        # What the run actually EXAMINED. A p95 next to a population of 0 is a number
        # about nothing — this block is what makes the SLO verdict above mean anything
        # (TASK 061 fix-loop / H3).
        "vacuity": vacuity,
    }
    json_out = json.dumps(payload, indent=2)
    if output_json_path:
        output_json_path.write_text(json_out)
    print(json_out)
    # A vacuous run FAILS unconditionally: `enforce_slos=False` waives the SLO
    # thresholds (machine-specific), never the claim that the ops ran the code.
    if not vacuity_ok:
        return False
    return all_pass or not enforce_slos


def run_multivault_scaling(
    n_vaults: int, pages_per_vault: int,
    output_json_path: Path | None = None,
) -> bool:
    """Generate N vaults, run cross-vault search + lint duplicates."""
    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "multi.db"
        repo = SQLiteRepository(db_path)
        repo.apply_schema()
        vault_ids: list[str] = []
        for i in range(n_vaults):
            vid = f"bench-vault-{i:03d}"
            vault_ids.append(vid)
            vroot = Path(tmp) / vid
            generate_synthetic_vault(vroot, vid, pages_per_vault, seed=42 + i)
            repo.register_vault(Vault(
                vault_id=vid, name=vid, root_path=vroot,
                schema_version="2.0", registered_at=datetime(2026, 5, 26),
            ))
            reindex_full(repo, vid)

        cross_search = measure(
            "wiki-search-cross-vault",
            lambda: repo.search_pages("synthetic", vaults=vault_ids),
            runs=5,
        )
        results.append(cross_search)

        cross_dup = measure(
            "wiki-lint-cross-vault-dup",
            lambda: repo.find_cross_vault_concept_duplicates(),
            runs=3,
        )
        results.append(cross_dup)
        repo.close()

    payload = {
        "mode": "multivault-scaling",
        "n_vaults": n_vaults,
        "pages_per_vault": pages_per_vault,
        "results": results,
    }
    json_out = json.dumps(payload, indent=2)
    if output_json_path:
        output_json_path.write_text(json_out)
    print(json_out)
    return True


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Phase 3a benchmark harness")
    p.add_argument("--n", type=int, default=100,
                   help="Pages in single-vault suite (default 100)")
    p.add_argument("--multivault", nargs=2, type=int, metavar=("N", "M"),
                   help="Run multi-vault scaling: N vaults × M pages each")
    p.add_argument("--output", type=Path, help="Write JSON to this path too")
    p.add_argument("--enforce-slos", action="store_true",
                   help="Exit 1 if any SLO miss")
    args = p.parse_args(argv)

    if args.multivault:
        run_multivault_scaling(args.multivault[0], args.multivault[1],
                               args.output)
        return 0
    ok = run_suite(args.n, args.output, enforce_slos=args.enforce_slos)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
