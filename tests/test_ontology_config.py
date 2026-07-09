"""TASK 054 / R-19 — layout-config parsing + load-time validation of the formal
ontology contract (`ontology:` block: closed_types / edges / properties).

Negative cases call `_validate_ontology` directly on a real cybos config with a
swapped-in bad `ontology` (deterministic, exercises the real `type_mapping` roster
without depending on the `.wiki/layout.yaml` deep-merge semantics); one positive
end-to-end case proves the resolve→merge→validate path accepts a valid override.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from scripts.wiki_index.layout_config import (
    LayoutConfigError,
    _validate_ontology,
    resolve_layout_config,
)
from scripts.wiki_index.models import OntologyConfig, OntologyEdge, OntologyProperty

_BASE_SCHEMA = ('---\nvault_id: ontvault\nschema_version: "2.0"\n'
                'language: en\nlayout: cybos\n---\n')


def _vault(tmp_path: Path, override: str | None = None) -> Path:
    root = tmp_path / "v"
    root.mkdir()
    (root / "WIKI_SCHEMA.md").write_text(_BASE_SCHEMA, encoding="utf-8")
    if override is not None:
        (root / ".wiki").mkdir()
        (root / ".wiki" / "layout.yaml").write_text(override, encoding="utf-8")
    return root


def _cybos_cfg(tmp_path: Path):
    return resolve_layout_config(_vault(tmp_path))


def _with_ontology(tmp_path: Path, ont: OntologyConfig):
    """A real cybos LayoutConfig (full type_mapping roster) with `ontology` swapped."""
    return dataclasses.replace(_cybos_cfg(tmp_path), ontology=ont)


# --- OFF ≡ None ------------------------------------------------------------

def test_layout_without_ontology_is_none(tmp_path: Path) -> None:
    # a vault with no WIKI_SCHEMA → defaults to karpathy → no ontology block
    root = tmp_path / "k"
    root.mkdir()
    assert resolve_layout_config(root).ontology is None


def test_only_cybos_ships_ontology_block() -> None:
    # OFF ≡ byte-identical: no non-cybos built-in layout carries an `ontology:` block, so
    # their resolved config has `ontology is None` and every ontology code path no-ops.
    import yaml

    from scripts.wiki_index.layout_config import LAYOUTS_DIR
    for f in sorted(LAYOUTS_DIR.glob("*.yaml")):
        raw = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        assert ("ontology" in raw) == (f.stem == "cybos"), f"{f.stem}: unexpected ontology block"


def test_cybos_ships_ontology(tmp_path: Path) -> None:
    cfg = _cybos_cfg(tmp_path)
    ont = cfg.ontology
    assert ont is not None
    assert ont.closed_types is True
    assert len(ont.edges) >= 1
    assert len(ont.properties) >= 1
    # every declared edge/property class is a real type_mapping key (else load would fail)
    roster = set(cfg.type_mapping)
    for e in ont.edges:
        assert set(e.frm) | set(e.to) <= roster
    for p in ont.properties:
        assert p.page_class in roster and p.enum


# --- load-gate negatives (each a distinct exit-6 branch) -------------------

def test_unknown_edge_rejected(tmp_path: Path) -> None:
    cfg = _with_ontology(tmp_path, OntologyConfig(
        edges=(OntologyEdge("bogus-edge", ("decision",), ("requirement",)),)))
    with pytest.raises(LayoutConfigError, match="unknown ref_type"):
        _validate_ontology(cfg)


def test_unknown_from_class_rejected(tmp_path: Path) -> None:
    cfg = _with_ontology(tmp_path, OntologyConfig(
        edges=(OntologyEdge("implements", ("notaclass",), ("requirement",)),)))
    with pytest.raises(LayoutConfigError, match="unknown class"):
        _validate_ontology(cfg)


def test_unknown_to_class_rejected(tmp_path: Path) -> None:
    cfg = _with_ontology(tmp_path, OntologyConfig(
        edges=(OntologyEdge("implements", ("decision",), ("notaclass",)),)))
    with pytest.raises(LayoutConfigError, match="unknown class"):
        _validate_ontology(cfg)


def test_empty_from_rejected(tmp_path: Path) -> None:
    cfg = _with_ontology(tmp_path, OntologyConfig(
        edges=(OntologyEdge("implements", (), ("requirement",)),)))
    with pytest.raises(LayoutConfigError, match="non-empty from/to"):
        _validate_ontology(cfg)


def test_unknown_property_class_rejected(tmp_path: Path) -> None:
    cfg = _with_ontology(tmp_path, OntologyConfig(
        properties=(OntologyProperty("notaclass", "status", ("open",)),)))
    with pytest.raises(LayoutConfigError, match="unknown class"):
        _validate_ontology(cfg)


def test_bad_property_field_rejected(tmp_path: Path) -> None:
    # uppercase + hyphen fail the metadata-filter field allow-list (SQL-path safety)
    cfg = _with_ontology(tmp_path, OntologyConfig(
        properties=(OntologyProperty("decision", "Bad-Field", ("open",)),)))
    with pytest.raises(LayoutConfigError):
        _validate_ontology(cfg)


def test_empty_enum_rejected(tmp_path: Path) -> None:
    cfg = _with_ontology(tmp_path, OntologyConfig(
        properties=(OntologyProperty("decision", "status", ()),)))
    with pytest.raises(LayoutConfigError, match="non-empty enum"):
        _validate_ontology(cfg)


def test_empty_enum_member_rejected(tmp_path: Path) -> None:
    cfg = _with_ontology(tmp_path, OntologyConfig(
        properties=(OntologyProperty("decision", "status", ("accepted", "")),)))
    with pytest.raises(LayoutConfigError, match="empty value"):
        _validate_ontology(cfg)


def test_duplicate_edge_rejected(tmp_path: Path) -> None:
    # critic-logic MINOR: two `implements` rules AND (not union) → false positives; reject.
    cfg = _with_ontology(tmp_path, OntologyConfig(edges=(
        OntologyEdge("implements", ("decision",), ("requirement",)),
        OntologyEdge("implements", ("task",), ("capability",)),
    )))
    with pytest.raises(LayoutConfigError, match="more than once"):
        _validate_ontology(cfg)


def test_duplicate_property_rejected(tmp_path: Path) -> None:
    cfg = _with_ontology(tmp_path, OntologyConfig(properties=(
        OntologyProperty("decision", "status", ("proposed",)),
        OntologyProperty("decision", "status", ("accepted",)),
    )))
    with pytest.raises(LayoutConfigError, match="more than once"):
        _validate_ontology(cfg)


def test_valid_ontology_passes(tmp_path: Path) -> None:
    cfg = _with_ontology(tmp_path, OntologyConfig(
        closed_types=True,
        edges=(OntologyEdge("implements", ("decision", "task"), ("requirement",)),),
        properties=(OntologyProperty("decision", "status", ("proposed", "accepted")),)))
    _validate_ontology(cfg)  # no raise


# --- end-to-end resolve→merge→validate (a valid override loads) ------------

def test_valid_ontology_override_loads(tmp_path: Path) -> None:
    override = (
        "ontology:\n"
        "  closed_types: false\n"
        "  edges:\n"
        "    - {edge: causes, from: [incident], to: [risk]}\n"
        "  properties:\n"
        "    - {class: risk, field: status, enum: [open, mitigated, closed]}\n"
    )
    cfg = resolve_layout_config(_vault(tmp_path, override))
    assert cfg.ontology is not None
    edges = {e.edge: e for e in cfg.ontology.edges}
    assert edges["causes"].frm == ("incident",) and edges["causes"].to == ("risk",)


def test_unknown_edge_override_rejected(tmp_path: Path) -> None:
    override = "ontology:\n  edges:\n    - {edge: nope-edge, from: [decision], to: [requirement]}\n"
    with pytest.raises(LayoutConfigError, match="unknown ref_type"):
        resolve_layout_config(_vault(tmp_path, override))
