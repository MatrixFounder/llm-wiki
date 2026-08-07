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


# =============================================================================
# TASK 072 / P2 — `forbid_values`: the OPTIONAL modifier of `requires_field`
# (bead 072-08 = schema + dataclass + build + load gate; the finder is widened in
# bead 072-09). Every way the modifier can be INERT is exit 6 here — a rule that
# is read, stored and then never able to fire is the vacuous green this whole task
# exists to refuse.
# =============================================================================

_HYP_RULE = "coverage_rules:\n  - {class: hypothesis, requires_field: verified_on"


def test_forbid_values_parses_onto_the_rule(tmp_path: Path) -> None:
    override = _HYP_RULE + ', forbid_values: ["не проверено", "n/a"]}\n'
    cfg = resolve_layout_config(_vault(tmp_path, override))
    (rule,) = cfg.coverage_rules
    assert rule.page_class == "hypothesis"
    assert rule.requires_field == "verified_on"
    assert rule.forbid_values == ("не проверено", "n/a")


def test_forbid_values_absent_is_the_off_default(tmp_path: Path) -> None:
    """OFF is the default on EVERY shipped rule — the precondition of the
    off-equivalence golden in tests/test_coverage_forbid_values.py."""
    cfg = resolve_layout_config(_vault(tmp_path))
    assert [r.forbid_values for r in cfg.coverage_rules] == [(), (), ()]


def test_forbid_values_without_requires_field_rejected(tmp_path: Path) -> None:
    # `forbid_values` alone is not a rule: schema `oneOf` matches NEITHER branch.
    override = 'coverage_rules:\n  - {class: hypothesis, forbid_values: ["n/a"]}\n'
    with pytest.raises(LayoutConfigError):
        resolve_layout_config(_vault(tmp_path, override))


def test_forbid_values_on_an_edge_rule_rejected(tmp_path: Path) -> None:
    """The `dependentRequired` half — and the reason K-2 mattered. `forbid_values`
    pulls in `requires_field`, which then collides with `requires_edge` under
    `oneOf`. Under `anyOf` this document would VALIDATE and the modifier would be
    stored against an edge rule that can never consult it."""
    override = ('coverage_rules:\n  - {class: requirement, requires_edge: implemented-by, '
                'forbid_values: ["n/a"]}\n')
    with pytest.raises(LayoutConfigError):
        resolve_layout_config(_vault(tmp_path, override))


def test_empty_forbid_values_list_rejected(tmp_path: Path) -> None:
    # A dead rule (nothing can ever match) — schema `minItems: 1`.
    override = _HYP_RULE + ", forbid_values: []}\n"
    with pytest.raises(LayoutConfigError):
        resolve_layout_config(_vault(tmp_path, override))


def test_non_string_forbid_value_rejected(tmp_path: Path) -> None:
    # The compared column is CAST(... AS TEXT); a YAML int would silently never match.
    override = _HYP_RULE + ", forbid_values: [7]}\n"
    with pytest.raises(LayoutConfigError):
        resolve_layout_config(_vault(tmp_path, override))


def test_blank_forbid_value_rejected(tmp_path: Path) -> None:
    # '' is ALREADY a gap via the empty-value branch, so a blank sentinel adds nothing.
    # Verbatim parity with drift's `forbid_status` gate.
    override = _HYP_RULE + ', forbid_values: ["  "]}\n'
    with pytest.raises(LayoutConfigError, match="must not contain an empty value"):
        resolve_layout_config(_vault(tmp_path, override))


def test_hand_built_rule_bypassing_the_schema_is_still_gated(tmp_path: Path) -> None:
    """`_validate_health_rules` runs on the BUILT LayoutConfig, so a library caller
    that constructs `CoverageRule` directly (tests, embedders) hits the same wall the
    YAML does. Without this half, `dependentRequired` is the single point of failure —
    the exact shape TASK 061's M4 finding punished in the ontology gate."""
    import dataclasses

    from scripts.wiki_index.layout_config import _validate_health_rules
    from scripts.wiki_index.models import CoverageRule

    cfg = resolve_layout_config(_vault(tmp_path))
    inert = dataclasses.replace(cfg, coverage_rules=(
        CoverageRule(page_class="requirement", requires_edge="implemented-by",
                     forbid_values=("n/a",)),
    ))
    with pytest.raises(LayoutConfigError, match="forbid_values requires requires_field"):
        _validate_health_rules(inert)
