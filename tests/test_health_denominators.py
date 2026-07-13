"""TASK 061 (R-061-1/R-061-2) — honest denominators over `find_coverage_gaps` /
`find_lifecycle_drift` / `find_ontology_violations`.

Bead 061-00: the three `find_*_report()` DAL methods were STUBS — `findings`
real (delegated to today's finders), every denominator hardcoded `0`.

Bead 061-01: `find_coverage_gaps_report` and `find_ontology_violations_report`
compute REAL denominators (R-061-1 — coverage `pages_examined`, ontology
`edges_examined` + `property_pages_examined`) and the legacy list methods collapse
into thin wrappers over the report methods (one code path).

Bead 061-03 (THIS revision): `find_lifecycle_drift_report`'s OWN `pages_examined`
+ per-rule `matched` land too (R-061-2 — surfaced by `wiki-lint`, whose lint-side
envelope is tested in `tests/test_lint_denominators.py`). FOUR denominators over
FOUR populations, none sharing a noun inside one envelope.

TC-00-2 (findings parity, still exercised below) is the load-bearing contract
that made the wrapper-collapse safe — the two call directions were proven to
agree BEFORE the collapse inverted which one is authoritative.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from scripts.wiki_index.layout_config import resolve_layout_config
from scripts.wiki_index.models import CoverageReport, LifecycleDriftReport, OntologyReport, Vault
from scripts.wiki_index.sqlite_repository import SQLiteRepository
from tests._health_fixtures import _FILES, build_cybos_vault, build_health_vault

_TYPE_RE = re.compile(r"\ntype: (\S+)\n")


def _type_counts(files: dict[str, str]) -> dict[str, int]:
    """Derive {class: page_count} straight from a fixture's frontmatter — the
    TC-01-1 "do not hand-copy a magic number" contract."""
    counts: dict[str, int] = {}
    for content in files.values():
        m = _TYPE_RE.search(content)
        if m:
            counts[m.group(1)] = counts.get(m.group(1), 0) + 1
    return counts


def _reports(tmp_path: Path):
    repo, root = build_health_vault(tmp_path)
    cfg = resolve_layout_config(root)
    assert cfg.ontology is not None
    coverage = repo.find_coverage_gaps_report("hvault", list(cfg.coverage_rules))
    drift = repo.find_lifecycle_drift_report("hvault", list(cfg.drift_rules))
    ontology = repo.find_ontology_violations_report("hvault", cfg.ontology)
    return repo, root, cfg, coverage, drift, ontology


# --- TC-00-1: shape ----------------------------------------------------------

def test_report_shapes(tmp_path: Path) -> None:
    repo, _root, _cfg, coverage, drift, ontology = _reports(tmp_path)
    assert isinstance(coverage, CoverageReport)
    assert isinstance(coverage.pages_examined, int)
    assert isinstance(coverage.rule_stats, list)
    assert isinstance(coverage.gaps, list)

    assert isinstance(drift, LifecycleDriftReport)
    assert isinstance(drift.pages_examined, int)
    assert isinstance(drift.rule_stats, list)
    assert isinstance(drift.hits, list)

    assert isinstance(ontology, OntologyReport)
    assert isinstance(ontology.edges_examined, int)
    assert isinstance(ontology.property_pages_examined, int)
    assert isinstance(ontology.rule_stats, list)
    assert isinstance(ontology.violations, list)
    repo.close()


def test_rule_stat_to_json_shape(tmp_path: Path) -> None:
    from scripts.wiki_index.models import RuleStat
    stat = RuleStat(page_class="requirement", kind="edge", ref="implemented-by",
                     matched=3, matched_by_kind={"gaps": 3}, findings={"gaps": 1})
    assert stat.to_json() == {
        "class": "requirement", "kind": "edge", "ref": "implemented-by",
        "matched": 3, "matched_by_kind": {"gaps": 3}, "findings": {"gaps": 1},
    }


# --- TC-00-2 / TC-01-5: findings parity (the wrapper-collapse safety net) ----

def test_coverage_findings_parity(tmp_path: Path) -> None:
    repo, root, cfg, coverage, _drift, _ontology = _reports(tmp_path)
    legacy = repo.find_coverage_gaps("hvault", list(cfg.coverage_rules))
    assert coverage.gaps == legacy
    repo.close()


def test_drift_findings_parity(tmp_path: Path) -> None:
    repo, root, cfg, _coverage, drift, _ontology = _reports(tmp_path)
    legacy = repo.find_lifecycle_drift("hvault", list(cfg.drift_rules))
    assert drift.hits == legacy
    repo.close()


def test_ontology_findings_parity(tmp_path: Path) -> None:
    repo, root, cfg, _coverage, _drift, ontology = _reports(tmp_path)
    legacy = repo.find_ontology_violations("hvault", cfg.ontology)
    assert ontology.violations == legacy
    repo.close()


# --- TC-01-1: typed fixture ⇒ non-zero, EXACT numbers derived from the fixture

def test_coverage_pages_examined_exact(tmp_path: Path) -> None:
    repo, _root, cfg, coverage, _drift, _ontology = _reports(tmp_path)
    counts = _type_counts(_FILES)
    coverage_classes = {r.page_class for r in cfg.coverage_rules}
    assert coverage_classes == {"requirement", "capability", "fact"}  # census, not belief
    expected = sum(counts.get(c, 0) for c in coverage_classes)
    assert expected == 6          # 2 requirements + 1 capability + 3 facts (spec's own worked example)
    assert coverage.pages_examined == expected
    repo.close()


def test_ontology_property_pages_examined_exact(tmp_path: Path) -> None:
    repo, _root, cfg, _coverage, _drift, ontology = _reports(tmp_path)
    assert cfg.ontology is not None
    counts = _type_counts(_FILES)
    prop_classes = {p.page_class for p in cfg.ontology.properties}
    assert len(prop_classes) == 11        # census: cybos.yaml ships 11 property rules
    expected = sum(counts.get(c, 0) for c in prop_classes)
    assert ontology.property_pages_examined == expected
    # build_health_vault authors decision(8)/incident(1)/workflow(2)/requirement(2)/
    # capability(1) — every one of those 5 classes IS a property class; "fact" is NOT.
    assert expected == 14
    repo.close()


def test_ontology_edges_examined_exact(tmp_path: Path) -> None:
    # Independent oracle: query page_entity_refs directly (NOT via the private helper
    # under test) for rows whose ref_type is in the ontology's declared edge vocabulary.
    repo, _root, cfg, _coverage, _drift, ontology = _reports(tmp_path)
    assert cfg.ontology is not None
    edge_types = sorted({e.edge for e in cfg.ontology.edges})
    assert edge_types == ["activates", "causes", "implements", "invalidates",
                           "owns", "supersedes", "uses"]     # census of cybos.yaml edges:
    placeholders = ",".join("?" * len(edge_types))
    row = repo._connect().execute(
        f"SELECT COUNT(*) FROM page_entity_refs WHERE vault_id=? AND ref_type IN ({placeholders})",
        ["hvault", *edge_types]).fetchone()
    assert ontology.edges_examined == row[0]
    assert ontology.edges_examined > 0
    repo.close()


# --- TC-01-2: untyped fixture ⇒ 0 — THE VACUITY GATE ------------------------

def test_untyped_and_nontyped_class_reads_zero(tmp_path: Path) -> None:
    # A `type: concept` page — `concept` is a real class but NOT one any coverage/ontology
    # rule binds to (a non-typed ADR-003 class), so it must NOT be counted. This reproduces
    # the LIVE-vault state (0 examined despite 713 real `concept` pages) inside CI.
    #
    # BEAD 061-03 CORRECTION (found by grepping cybos.yaml's `paths:`, not by reasoning):
    # this fixture originally filed the page at `_concepts/some-concept.md` — and cybos
    # ships **no `_concepts/**` glob**, so that page was NEVER INDEXED. The test passed
    # because `pages` was EMPTY, not because an indexed concept page was correctly
    # excluded: a check that examined nothing reporting green, INSIDE the test written to
    # kill that bug (the 8th recurrence of this task's fractal). Nesting it under a
    # RECURSIVE glob (`facts/**/*.md`) is what actually indexes it — asserted below, so
    # the fixture can never silently go vacuous again.
    files = {
        "facts/_concepts/some-concept.md":
            "---\ntype: concept\ntitle: Some Concept\n---\nbody\n",
    }
    repo, root = build_cybos_vault(tmp_path, files, vault_id="vacuous")
    cfg = resolve_layout_config(root)
    assert cfg.ontology is not None
    # THE GUARD: the page is really in `pages`, with `$.type = concept`. Without this,
    # every assertion below would hold over an empty table and prove nothing.
    assert repo._connect().execute(
        "SELECT COUNT(*) FROM pages WHERE vault_id='vacuous' "
        "AND json_extract(frontmatter_json, '$.type') = 'concept'").fetchone()[0] == 1
    coverage = repo.find_coverage_gaps_report("vacuous", list(cfg.coverage_rules))
    ontology = repo.find_ontology_violations_report("vacuous", cfg.ontology)
    assert coverage.pages_examined == 0
    assert ontology.edges_examined == 0
    assert ontology.property_pages_examined == 0
    # ... while the OLD envelope shape ("0 gaps"/"0 violations") stays exactly as
    # vacuous as it always was — the ambiguity this task closes.
    assert len(coverage.gaps) == 0
    assert len(ontology.violations) == 0
    repo.close()


def test_mentioned_only_vault_edges_examined_zero(tmp_path: Path) -> None:
    # THE LIVE 8836-ref TRAP: a vault with real page_entity_refs rows — but every one
    # is `mentioned` (body wikilinks), never a declared ontology edge. `edges_examined`
    # must read 0 despite a non-empty page_entity_refs table (acceptance criterion).
    files = {
        "decisions/d1.md": "---\ntype: decision\ntitle: D1\nstatus: accepted\n---\nSee [[d2]] and [[d3]].\n",
        "decisions/d2.md": "---\ntype: decision\ntitle: D2\nstatus: accepted\n---\nSee [[d1]] and [[d3]].\n",
        "decisions/d3.md": "---\ntype: decision\ntitle: D3\nstatus: accepted\n---\nSee [[d1]] and [[d2]].\n",
    }
    repo, root = build_cybos_vault(tmp_path, files, vault_id="mentionsonly")
    cfg = resolve_layout_config(root)
    assert cfg.ontology is not None
    total_refs = repo._connect().execute(
        "SELECT COUNT(*) FROM page_entity_refs WHERE vault_id=?", ["mentionsonly"]).fetchone()[0]
    assert total_refs > 0        # the trap: refs exist...
    ontology = repo.find_ontology_violations_report("mentionsonly", cfg.ontology)
    assert ontology.edges_examined == 0   # ...but NONE are the declared edge vocabulary
    repo.close()


# --- TC-01-3: per-rule invariants (P-061-A) ---------------------------------

# A dedicated ontology fixture carrying BOTH a domain AND a range violation on the
# SAME examined ref row (`fact-badcauses` `causes` a `workflow`: fact ∉ `causes.from`,
# workflow ∉ `causes.to`) — this is the P-061-A case the RTM names explicitly: ONE
# examined row can be BOTH kinds, so `domain_e + range_e` (2) > `matched_e` (1) —
# the invariant MUST be per-kind (`domain_e <= matched_e` AND `range_e <= matched_e`
# independently), never a summed `violations_e <= matched_e`.
_INVARIANT_FILES = {
    "facts/fact-badcauses.md":
        "---\ntype: fact\ntitle: Fact BadCauses\nsource: \"x\"\ncauses: [[wf-target]]\n---\nb\n",
    "workflows/wf-target.md":
        "---\ntype: workflow\ntitle: WF Target\nstatus: active\n---\nb\n",
    "decisions/dec-badprop.md":
        "---\ntype: decision\ntitle: Dec BadProp\nstatus: bogus\n---\nb\n",
    "decisions/dec-ok.md":
        "---\ntype: decision\ntitle: Dec OK\nstatus: accepted\n---\nb\n",
}


def test_per_rule_invariants_coverage(tmp_path: Path) -> None:
    repo, _root, _cfg, coverage, _drift, _ontology = _reports(tmp_path)
    for stat in coverage.rule_stats:
        gaps = stat.findings["gaps"]
        assert gaps <= stat.matched <= coverage.pages_examined
    # NOT asserted: `sum(gaps) <= pages_examined`. Two coverage rules CAN target the
    # same class (schema permits it), so one page could gap under BOTH rules — the
    # per-rule form above is the only one that holds on correct data (RTM constraint 3).
    repo.close()


def test_per_rule_invariants_ontology_dual_kind(tmp_path: Path) -> None:
    repo, root = build_cybos_vault(tmp_path, _INVARIANT_FILES, vault_id="invariantv")
    cfg = resolve_layout_config(root)
    assert cfg.ontology is not None
    report = repo.find_ontology_violations_report("invariantv", cfg.ontology)

    causes_stat = next(s for s in report.rule_stats if s.kind == "edge" and s.ref == "causes")
    assert causes_stat.matched == 1                      # the one fact-badcauses ref row
    assert causes_stat.findings == {"domain": 1, "range": 1}
    # THE invariant this whole task is fussy about: per-kind, never summed.
    assert causes_stat.findings["domain"] <= causes_stat.matched
    assert causes_stat.findings["range"] <= causes_stat.matched
    assert causes_stat.matched <= report.edges_examined
    # ...while the naive SUMMED form is FALSE on this exact fixture — pin it so a
    # future refactor can't quietly revert to the forbidden total-form assertion.
    assert causes_stat.findings["domain"] + causes_stat.findings["range"] > causes_stat.matched

    prop_stat = next(s for s in report.rule_stats if s.kind == "property" and s.page_class == "decision")
    assert prop_stat.findings["property"] == 1            # dec-badprop only
    assert prop_stat.findings["property"] <= prop_stat.matched <= report.property_pages_examined
    repo.close()


# --- TC-01-4: matched is not a proxy for examined ---------------------------

def test_matched_independent_of_denominator(tmp_path: Path) -> None:
    # Every requirement page GAPS (no implemented-by edge exists anywhere in this
    # tiny vault) — so `matched == gaps` for the requirement rule — while
    # `pages_examined` counts the UNION of all coverage classes (requirement ∪
    # capability ∪ fact), proving the two numbers vary independently.
    files = {
        "requirements/req-1.md": "---\ntype: requirement\ntitle: R1\nstatus: draft\n---\nb\n",
        "requirements/req-2.md": "---\ntype: requirement\ntitle: R2\nstatus: draft\n---\nb\n",
    }
    repo, root = build_cybos_vault(tmp_path, files, vault_id="matchedv")
    cfg = resolve_layout_config(root)
    report = repo.find_coverage_gaps_report("matchedv", list(cfg.coverage_rules))
    assert report.pages_examined == 2      # only the 2 requirement pages exist
    req_stat = next(s for s in report.rule_stats if s.page_class == "requirement")
    assert req_stat.matched == 2
    assert req_stat.findings["gaps"] == req_stat.matched == 2   # every page gaps
    repo.close()


# --- TC-01-5 covered above (parity) + degenerate-SQL guard ------------------

def test_untyped_vault_zero_rules_no_sql(tmp_path: Path) -> None:
    # An UNTYPED vault (no coverage_rules/drift_rules/ontology block) — P-061-C: an
    # empty rule/class/edge set must return 0 with NO SQL executed (never a
    # degenerate `IN ()`).
    root = tmp_path / "untyped"
    root.mkdir()  # no WIKI_SCHEMA.md → defaults to karpathy → no health rules
    repo = SQLiteRepository(tmp_path / "untyped.db")
    repo.apply_schema()
    repo.register_vault(Vault(vault_id="untyped", name="untyped", root_path=root,
                               schema_version="2.0", registered_at=datetime(2026, 6, 16)))
    cfg = resolve_layout_config(root)
    assert cfg.ontology is None
    coverage = repo.find_coverage_gaps_report("untyped", list(cfg.coverage_rules))
    drift = repo.find_lifecycle_drift_report("untyped", list(cfg.drift_rules))
    assert coverage.gaps == [] and coverage.pages_examined == 0 and coverage.rule_stats == []
    assert drift.hits == [] and drift.pages_examined == 0 and drift.rule_stats == []
    # ontology is None for karpathy — callers never even reach the DAL (mirrors the
    # pre-061 `find_ontology_violations` no-op contract; not exercised here).
    repo.close()


# --- drift's OWN denominator — LANDED by R-061-2 / bead 061-03 --------------

def test_drift_denominator_landed_in_061_03(tmp_path: Path) -> None:
    # Bead 061-01 shipped this as a VISIBLE, tracked residual (`pages_examined == 0`,
    # `rule_stats == []`, docstring citing R-061-2) rather than a silent gap. Bead 061-03
    # closes it, and this test FLIPS to the real numbers — the pin did its job: the
    # residual could not be forgotten, because forgetting it would have left a test
    # asserting a stub.
    repo, _root, _cfg, _coverage, drift, _ontology = _reports(tmp_path)
    assert len(drift.hits) > 0            # findings are real (the 4 drift contradictions)
    counts = _type_counts(_FILES)
    drift_classes = {r.page_class for r in _cfg.drift_rules}
    assert drift_classes == {"decision", "workflow"}      # census, not belief
    assert drift.pages_examined == sum(counts.get(c, 0) for c in drift_classes) == 10
    # cybos ships TWO drift rules on `decision` (superseded-by + invalidated-by) — the
    # very "two rules, one class" shape that makes a TOTAL-form invariant false. One
    # RuleStat PER RULE, not per class.
    assert len(drift.rule_stats) == len(_cfg.drift_rules) == 3
    for stat in drift.rule_stats:
        assert stat.kind == "drift"
        assert stat.findings["drift"] <= stat.matched <= drift.pages_examined
    repo.close()


# =============================================================================
# 061 FIX-LOOP (vdd-multi) — M1 (perf), M3 (per-kind denominator), M4 (degenerate rule)
# =============================================================================

# --- M3: the ontology EDGE `matched` counted rows the check CANNOT JUDGE -----

_GHOST_FILES = {
    # `uses` from a `workflow` IS in the declared domain (from: [agent, workflow,
    # execution]) → no domain violation; both targets are DANGLING, so `tgt_type` is NULL
    # and the RANGE check cannot judge a single one of these rows. Pre-fix this reported
    # `{matched: 2, findings: {domain: 0, range: 0}}` — "2 examined, all clean" — while
    # `range` examined ZERO. `{"total_gaps": 0}` one level down, inside TASK 061's own
    # numbers.
    "workflows/wf-a.md":
        "---\ntype: workflow\ntitle: WF A\nstatus: active\nuses: [[ghost-1]]\n---\nb\n",
    "workflows/wf-b.md":
        "---\ntype: workflow\ntitle: WF B\nstatus: active\nuses: [[ghost-2]]\n---\nb\n",
}


def test_m3_edge_matched_by_kind_excludes_unjudgeable_rows(tmp_path: Path) -> None:
    repo, root = build_cybos_vault(tmp_path, _GHOST_FILES, vault_id="ghostv")
    cfg = resolve_layout_config(root)
    assert cfg.ontology is not None
    # THE ANTI-VACUITY GUARD (the earlier bead shipped a vacuity test that was itself
    # vacuous — over an EMPTY table): the `uses` refs really are stored, and their targets
    # really are absent from `pages`.
    conn = repo._connect()
    assert conn.execute(
        "SELECT COUNT(*) FROM page_entity_refs WHERE vault_id='ghostv' "
        "AND ref_type='uses'").fetchone()[0] == 2
    assert conn.execute(
        "SELECT COUNT(*) FROM pages WHERE vault_id='ghostv' "
        "AND slug IN ('ghost-1','ghost-2')").fetchone()[0] == 0

    report = repo.find_ontology_violations_report("ghostv", cfg.ontology)
    uses = next(s for s in report.rule_stats if s.kind == "edge" and s.ref == "uses")
    assert uses.matched == 2                        # 2 ref rows were fetched...
    assert uses.findings == {"domain": 0, "range": 0}
    # ...but only the DOMAIN check could judge them. `range` examined NOTHING, and now
    # says so instead of hiding inside a `matched` it never applied to.
    assert uses.matched_by_kind == {"domain": 2, "range": 0}
    repo.close()


def test_m3_matched_by_kind_mirrors_findings_on_every_rule(tmp_path: Path) -> None:
    """The structural invariant every producer upholds — asserted over ALL THREE finders'
    rule_stats (`grep -n "RuleStat(" scripts/wiki_index/sqlite_repository/_health_rules.py`
    → 6 construction sites: drift ×2, coverage ×1, ontology edge ×1, ontology property ×2):

        set(matched_by_kind) == set(findings)   and
        ∀k: findings[k] <= matched_by_kind[k] <= matched
    """
    repo, _root, cfg, coverage, drift, ontology = _reports(tmp_path)
    stats = [*coverage.rule_stats, *drift.rule_stats, *ontology.rule_stats]
    assert len(stats) == (len(cfg.coverage_rules) + len(cfg.drift_rules)
                          + len(cfg.ontology.edges) + len(cfg.ontology.properties)) == 24
    for stat in stats:
        assert set(stat.matched_by_kind) == set(stat.findings), stat
        for kind, n in stat.findings.items():
            assert n <= stat.matched_by_kind[kind] <= stat.matched, stat
    repo.close()


# --- M4: a degenerate ontology PROPERTY rule is NOT dropped from by_rule -----

def test_m4_degenerate_property_rule_still_gets_a_rulestat(tmp_path: Path) -> None:
    """Exact mirror of `test_tc_03_4_degenerate_rule_still_gets_a_rulestat` (drift). A
    hand-built property rule with an EMPTY enum (bypassing the config load-gate, which
    rejects it) is skipped by the finder — but it STILL gets a RuleStat, because its class
    still counts toward `property_pages_examined`. Pre-fix the rule VANISHED from
    `by_rule` while inflating the denominator: the `∀ declared rule` quantifier held only
    because CONFIG forbade the case, not because the CODE handled it."""
    import dataclasses

    from scripts.wiki_index.models import OntologyConfig, OntologyProperty

    repo, root = build_cybos_vault(tmp_path, {
        "decisions/d1.md": "---\ntype: decision\ntitle: D1\nstatus: accepted\n---\nb\n",
        "decisions/d2.md": "---\ntype: decision\ntitle: D2\nstatus: bogus\n---\nb\n",
    }, vault_id="degenprop")
    cfg = resolve_layout_config(root)
    assert cfg.ontology is not None
    degenerate = OntologyProperty(page_class="decision", field="status", enum=())
    ont: OntologyConfig = dataclasses.replace(
        cfg.ontology, edges=(), properties=(degenerate,))

    report = repo.find_ontology_violations_report("degenprop", ont)
    assert report.violations == []                  # a no-enum rule can flag nothing...
    assert report.property_pages_examined == 2      # ...yet its class DID count here
    assert len(report.rule_stats) == 1              # ...and the rule is PRESENT
    stat = report.rule_stats[0]
    assert stat.kind == "property" and stat.ref == "status"
    assert stat.matched == 2                        # both decisions carry a scalar status
    assert stat.matched_by_kind == {"property": 2}
    assert stat.findings == {"property": 0}
    repo.close()


# --- M1: no N+1 — one grouped statement per FAMILY, never one COUNT per rule --

def _statements(repo: SQLiteRepository) -> list[str]:
    """Every SQL statement the repo's connection executes, captured live."""
    stmts: list[str] = []
    repo._connect().set_trace_callback(stmts.append)
    return stmts


def test_m1_statement_census_no_n_plus_one(tmp_path: Path) -> None:
    """A REGRESSION PIN, not a benchmark: the first cut of TASK 061 computed `matched`
    with a fresh full `pages` scan PER RULE, on top of the finder query that already loops
    per rule — 21 → 38 statements per lint run, and a >2× regression of `wiki-health
    coverage` (3 → 7). Counted, not believed: `sqlite3.set_trace_callback`."""
    repo, root = build_health_vault(tmp_path)
    cfg = resolve_layout_config(root)
    assert cfg.ontology is not None
    # census of the RULE COUNTS this is asserted against (cybos is the only built-in
    # layout declaring any) — so a rule added in a later task moves these numbers loudly.
    n_cov, n_drift = len(cfg.coverage_rules), len(cfg.drift_rules)
    n_edge, n_prop = len(cfg.ontology.edges), len(cfg.ontology.properties)
    assert (n_cov, n_drift, n_edge, n_prop) == (3, 3, 7, 11)

    stmts = _statements(repo)
    repo.find_coverage_gaps_report("hvault", list(cfg.coverage_rules))
    # ONE class histogram + one gap-finder per rule (was 1 + n_cov + n_cov = 7).
    assert len(stmts) == 1 + n_cov == 4, stmts

    stmts.clear()
    repo.find_lifecycle_drift_report("hvault", list(cfg.drift_rules))
    # ONE class histogram + ONE (class, ref_type) probe + one drift-finder per rule
    # (was 1 + n_drift + n_drift = 7).
    assert len(stmts) == 2 + n_drift == 5, stmts

    stmts.clear()
    repo.find_ontology_violations_report("hvault", cfg.ontology)
    # ONE refs COUNT (rides idx_refs_type) + one edge-finder per edge rule + ONE property
    # histogram + one property-finder per property rule (was 1 + n_edge + 1 + 2*n_prop = 31).
    assert len(stmts) == 1 + n_edge + 1 + n_prop == 20, stmts

    repo._connect().set_trace_callback(None)
    repo.close()


def test_m1_histograms_agree_with_the_per_rule_oracle(tmp_path: Path) -> None:
    """The collapse 1+N → 1 must not change a single number. Independent oracle: the
    per-rule COUNT queries the fix DELETED, re-issued here by hand against every rule."""
    repo, root = build_health_vault(tmp_path)
    cfg = resolve_layout_config(root)
    assert cfg.ontology is not None
    conn = repo._connect()

    coverage = repo.find_coverage_gaps_report("hvault", list(cfg.coverage_rules))
    for stat, rule in zip(coverage.rule_stats, cfg.coverage_rules, strict=True):
        oracle = conn.execute(
            "SELECT COUNT(*) FROM pages p WHERE p.vault_id='hvault' "
            "AND json_extract(p.frontmatter_json,'$.type') = ?", [rule.page_class]
        ).fetchone()[0]
        assert stat.matched == oracle > 0

    drift = repo.find_lifecycle_drift_report("hvault", list(cfg.drift_rules))
    for stat, drule in zip(drift.rule_stats, cfg.drift_rules, strict=True):
        oracle = conn.execute(
            "SELECT COUNT(*) FROM pages p WHERE p.vault_id='hvault' "
            "AND json_extract(p.frontmatter_json,'$.type') = ? "
            "AND EXISTS (SELECT 1 FROM page_entity_refs r WHERE r.vault_id=p.vault_id "
            "  AND r.page_slug=p.slug AND r.page_project=p.project AND r.ref_type = ?)",
            [drule.page_class, drule.edge]).fetchone()[0]
        assert stat.matched == oracle
    assert any(s.matched > 0 for s in drift.rule_stats)   # not vacuously equal to 0

    ontology = repo.find_ontology_violations_report("hvault", cfg.ontology)
    prop_stats = [s for s in ontology.rule_stats if s.kind == "property"]
    for stat, prule in zip(prop_stats, cfg.ontology.properties, strict=True):
        oracle = conn.execute(
            "SELECT COUNT(*) FROM pages p WHERE p.vault_id='hvault' "
            "AND json_extract(p.frontmatter_json,'$.type') = ? "
            "AND json_type(p.frontmatter_json, ?) = 'text'",
            [prule.page_class, f"$.{prule.field}"]).fetchone()[0]
        assert stat.matched == oracle
    assert any(s.matched > 0 for s in prop_stats)         # not vacuously equal to 0
    repo.close()
