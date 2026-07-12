"""TASK 061 (R-061-1/R-061-2) — honest denominators over `find_coverage_gaps` /
`find_lifecycle_drift` / `find_ontology_violations`.

Bead 061-00 (THIS FILE, initial revision): the three `find_*_report()` DAL methods
are STUBS — `findings` are real (delegated to today's finders), but every
denominator is hardcoded `0` and `rule_stats` is `[]`. TC-00-3 pins that stub
state; bead 061-01 REPLACES TC-00-3 with real non-zero assertions (coverage +
ontology only — drift's own `pages_examined` stays 0 until 061-03, R-061-2's
`wiki-lint` bead) and adds the per-rule invariant tests.

TC-00-2 (findings parity) is the load-bearing contract: it is what lets 061-01
safely INVERT the delegation direction — collapsing `find_coverage_gaps` /
`find_lifecycle_drift` / `find_ontology_violations` into thin wrappers over the
`*_report()` methods — without a behavior change, because this test already
proves the two call directions agree.
"""

from __future__ import annotations

from pathlib import Path

from scripts.wiki_index.layout_config import resolve_layout_config
from scripts.wiki_index.models import CoverageReport, LifecycleDriftReport, OntologyReport
from tests._health_fixtures import build_health_vault


def _reports(tmp_path: Path):
    repo, root = build_health_vault(tmp_path)
    cfg = resolve_layout_config(root)
    assert cfg.ontology is not None
    coverage = repo.find_coverage_gaps_report("hvault", list(cfg.coverage_rules))
    drift = repo.find_lifecycle_drift_report("hvault", list(cfg.drift_rules))
    ontology = repo.find_ontology_violations_report("hvault", cfg.ontology)
    return repo, root, cfg, coverage, drift, ontology


# --- TC-00-1: shape --------------------------------------------------------

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


# --- TC-00-2: findings parity (the wrapper-collapse safety net) ------------

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


# --- TC-00-3: stub denominators (THIS commit only — 061-01 flips these) ----

def test_stub_denominators_are_zero(tmp_path: Path) -> None:
    # Pinned at 061-00: the stub NEVER computes a population count. 061-01
    # replaces this test's assertions with real non-zero counts on this same
    # typed fixture (coverage + ontology; drift's own `pages_examined` is
    # R-061-2 / bead 061-03 — it stays 0 even after 061-01).
    repo, _root, _cfg, coverage, drift, ontology = _reports(tmp_path)
    assert coverage.pages_examined == 0 and coverage.rule_stats == []
    assert drift.pages_examined == 0 and drift.rule_stats == []
    assert ontology.edges_examined == 0
    assert ontology.property_pages_examined == 0
    assert ontology.rule_stats == []
    # ... while findings are REAL and non-empty (proves the stub is a real
    # delegation, not a no-op) — the vacuity this task exists to make visible.
    assert len(coverage.gaps) > 0
    assert len(drift.hits) > 0
    # build_health_vault's fixture pages happen to conform to the cybos ontology
    # contract (they were authored to exercise drift/coverage, not ontology) —
    # see tests/test_ontology_violations.py for the dedicated violation fixture.
    assert len(ontology.violations) == 0
    repo.close()


def test_untyped_vault_stub_still_zero(tmp_path: Path) -> None:
    # An UNTYPED vault (no coverage_rules/drift_rules/ontology block) — the
    # degenerate-input case the real 061-01 counts must also handle (P-061-C).
    root = tmp_path / "untyped"
    root.mkdir()  # no WIKI_SCHEMA.md → defaults to karpathy → no health rules
    from datetime import datetime

    from scripts.wiki_index.models import Vault
    from scripts.wiki_index.sqlite_repository import SQLiteRepository

    repo = SQLiteRepository(tmp_path / "untyped.db")
    repo.apply_schema()
    repo.register_vault(Vault(vault_id="untyped", name="untyped", root_path=root,
                               schema_version="2.0", registered_at=datetime(2026, 6, 16)))
    cfg = resolve_layout_config(root)
    assert cfg.ontology is None
    coverage = repo.find_coverage_gaps_report("untyped", list(cfg.coverage_rules))
    drift = repo.find_lifecycle_drift_report("untyped", list(cfg.drift_rules))
    assert coverage.gaps == [] and coverage.pages_examined == 0
    assert drift.hits == [] and drift.pages_examined == 0
    repo.close()
