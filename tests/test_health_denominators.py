"""TASK 061 (R-061-1/R-061-2) — honest denominators over `find_coverage_gaps` /
`find_lifecycle_drift` / `find_ontology_violations`.

Bead 061-00: the three `find_*_report()` DAL methods were STUBS — `findings`
real (delegated to today's finders), every denominator hardcoded `0`.

Bead 061-01 (THIS revision): `find_coverage_gaps_report` and
`find_ontology_violations_report` compute REAL denominators (R-061-1 — coverage
`pages_examined`, ontology `edges_examined` + `property_pages_examined`) and the
legacy list methods collapse into thin wrappers over the report methods (one
code path). `find_lifecycle_drift_report`'s OWN `pages_examined` stays a stub
`0` — that denominator is R-061-2 (bead 061-03, `wiki-lint`'s BOTH-checks fix),
deliberately NOT this bead's scope (see the RTM: R-061-1 names ONLY
`find_coverage_gaps` + `find_ontology_violations`; R-061-2 is the one that adds
drift's own `pages_examined`).

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
                     matched=3, findings={"gaps": 1})
    assert stat.to_json() == {
        "class": "requirement", "kind": "edge", "ref": "implemented-by",
        "matched": 3, "findings": {"gaps": 1},
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
    # No `type:` at all, PLUS a `type: concept` page — concept is a real class but
    # NOT one any coverage/ontology rule binds to (a non-typed ADR-003 class), so it
    # must NOT be counted either. This reproduces the LIVE-vault state (0 examined
    # despite 713 real `concept` pages) inside CI.
    files = {
        "notes/untyped.md": "---\ntitle: No Type At All\n---\nbody\n",
        "_concepts/some-concept.md": "---\ntype: concept\ntitle: Some Concept\n---\nbody\n",
    }
    repo, root = build_cybos_vault(tmp_path, files, vault_id="vacuous")
    cfg = resolve_layout_config(root)
    assert cfg.ontology is not None
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


# --- drift's OWN denominator stays a stub (R-061-2 / bead 061-03 scope) -----

def test_drift_denominator_still_stub_until_061_03(tmp_path: Path) -> None:
    # R-061-1 (this bead's RTM scope) is coverage + ontology ONLY. Drift's own
    # `pages_examined` denominator is R-061-2 (bead 061-03, `wiki-lint`) — pinned
    # here so it is a VISIBLE, tracked residual, not a silent gap.
    repo, _root, _cfg, _coverage, drift, _ontology = _reports(tmp_path)
    assert len(drift.hits) > 0            # findings are real (the 4 drift contradictions)
    assert drift.pages_examined == 0      # denominator: still 061-03's job
    assert drift.rule_stats == []
    repo.close()
