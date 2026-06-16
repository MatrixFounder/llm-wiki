"""TASK 036 / R-15 — layout-config parsing + load-time validation of the
derived-knowledge-health rules (drift_rules / coverage_rules)."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.wiki_index.layout_config import LayoutConfigError, resolve_layout_config

_BASE_SCHEMA = ('---\nvault_id: cfgvault\nschema_version: "2.0"\n'
                'language: en\nlayout: cybos\n---\n')


def _vault(tmp_path: Path, override: str | None = None) -> Path:
    root = tmp_path / "v"
    root.mkdir()
    (root / "WIKI_SCHEMA.md").write_text(_BASE_SCHEMA, encoding="utf-8")
    if override is not None:
        (root / ".wiki").mkdir()
        (root / ".wiki" / "layout.yaml").write_text(override, encoding="utf-8")
    return root


def test_cybos_ships_health_rules(tmp_path: Path) -> None:
    cfg = resolve_layout_config(_vault(tmp_path))
    assert len(cfg.drift_rules) == 3
    assert len(cfg.coverage_rules) == 3
    dr = {(r.page_class, r.edge): r for r in cfg.drift_rules}
    assert dr[("decision", "superseded-by")].expect_status == "superseded"
    assert dr[("decision", "invalidated-by")].forbid_status == ("proposed", "accepted")
    cov = {r.page_class: r for r in cfg.coverage_rules}
    assert cov["fact"].requires_field == "source"
    assert cov["requirement"].requires_edge == "implemented-by"
    assert cov["capability"].requires_edge == "implemented-by"


def test_layout_without_rules_is_empty(tmp_path: Path) -> None:
    # a vault with no WIKI_SCHEMA → defaults to karpathy → no health rules
    root = tmp_path / "k"
    root.mkdir()
    cfg = resolve_layout_config(root)
    assert cfg.drift_rules == ()
    assert cfg.coverage_rules == ()


def test_unknown_drift_edge_rejected(tmp_path: Path) -> None:
    override = "drift_rules:\n  - {class: decision, edge: bogus-edge, expect_status: superseded}\n"
    with pytest.raises(LayoutConfigError, match="unknown edge"):
        resolve_layout_config(_vault(tmp_path, override))


def test_unknown_coverage_edge_rejected(tmp_path: Path) -> None:
    override = "coverage_rules:\n  - {class: requirement, requires_edge: not-an-edge}\n"
    with pytest.raises(LayoutConfigError, match="unknown edge"):
        resolve_layout_config(_vault(tmp_path, override))


def test_bad_coverage_field_rejected(tmp_path: Path) -> None:
    # uppercase + hyphen fail the metadata-filter field allow-list
    override = "coverage_rules:\n  - {class: fact, requires_field: Bad-Field}\n"
    with pytest.raises(LayoutConfigError):
        resolve_layout_config(_vault(tmp_path, override))


def test_drift_rule_both_branches_rejected(tmp_path: Path) -> None:
    # schema `oneOf` forbids setting both expect_status AND forbid_status
    override = ("drift_rules:\n  - {class: decision, edge: superseded-by, "
                "expect_status: superseded, forbid_status: [accepted]}\n")
    with pytest.raises(LayoutConfigError):
        resolve_layout_config(_vault(tmp_path, override))


def test_empty_expect_status_rejected(tmp_path: Path) -> None:
    # vdd-multi critic-logic LOW: an empty expect_status would flag every page with the edge
    override = 'drift_rules:\n  - {class: decision, edge: superseded-by, expect_status: ""}\n'
    with pytest.raises(LayoutConfigError, match="non-empty"):
        resolve_layout_config(_vault(tmp_path, override))
