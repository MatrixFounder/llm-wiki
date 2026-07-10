"""TASK 058 — schema → UI-model projection (the evolution invariant, R-058-10).

The ONE source of truth for what the interface shows is `config/sync-config.schema.yaml`:
key types, enums, defaults, human descriptions, plus the TASK 058 `x-wiki-*`
annotations (`x-wiki-scope`: root-only | cascading; `x-wiki-format`: regex | glob |
path). This module projects that schema into a flat, ordered
``JSON pointer → FieldSpec`` map consumed by every interface surface (CLI reports,
the HTML report, the serve form). A NEW field added to the schema therefore appears
everywhere with ZERO interface-code changes — enforced by a dedicated test.

Read-only; no knowledge of any concrete key name lives here (or anywhere downstream).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SYNC_SCHEMA_PATH = _REPO_ROOT / "config" / "sync-config.schema.yaml"

# Scope annotation values (see the schema's SyncConfig comment block).
SCOPE_ROOT_ONLY = "root-only"
SCOPE_CASCADING = "cascading"


@dataclass(frozen=True)
class FieldSpec:
    """One schema node, addressable by its JSON pointer (e.g. `/summarize/profile`).

    ``scope`` is inherited from the node's TOP-LEVEL ancestor property — the unit
    of scope in sync.yaml is the top-level key. ``kind`` is the JSON-Schema `type`
    (`object` nodes render as fieldsets, scalars/arrays as inputs). ``fmt`` is the
    `x-wiki-format` annotation (regex | glob | path | None)."""

    pointer: str
    kind: str
    scope: str
    description: str = ""
    enum: tuple[str, ...] | None = None
    default: Any = None
    fmt: str | None = None
    items_kind: str | None = None


def load_sync_schema_doc(path: Path | None = None) -> dict[str, Any]:
    """Read the sync-config schema YAML (default: the repo copy). Kept injectable
    so tests can exercise the evolution invariant with a synthetic field."""
    doc = yaml.safe_load((path or SYNC_SCHEMA_PATH).read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise ValueError("sync-config schema: not a YAML mapping")
    return doc


def _resolve_ref(node: dict[str, Any], defs: dict[str, Any]) -> dict[str, Any]:
    """Resolve a local `$ref: '#/$defs/X'`, merging ref-site annotations OVER the
    target's (the ref site is where `x-wiki-scope` lives for block properties)."""
    ref = node.get("$ref")
    if not isinstance(ref, str) or not ref.startswith("#/$defs/"):
        return node
    target = defs.get(ref.removeprefix("#/$defs/"))
    if not isinstance(target, dict):
        return node
    merged = dict(target)
    for key, value in node.items():
        if key != "$ref":
            merged[key] = value
    return merged


def _walk(
    out: dict[str, FieldSpec],
    node: dict[str, Any],
    defs: dict[str, Any],
    pointer: str,
    scope: str,
) -> None:
    node = _resolve_ref(node, defs)
    kind = str(node.get("type") or "object")
    enum_raw = node.get("enum")
    enum = tuple(str(v) for v in enum_raw) if isinstance(enum_raw, list) else None
    items = node.get("items")
    items_kind: str | None = None
    if isinstance(items, dict):
        items_kind = str(_resolve_ref(items, defs).get("type") or "string")
    out[pointer] = FieldSpec(
        pointer=pointer,
        kind=kind,
        scope=scope,
        description=str(node.get("description") or "").strip(),
        enum=enum,
        default=node.get("default"),
        fmt=node.get("x-wiki-format"),
        items_kind=items_kind,
    )
    props = node.get("properties")
    if isinstance(props, dict):
        for name, child in props.items():
            if isinstance(child, dict):
                _walk(out, child, defs, f"{pointer}/{name}", scope)


def build_ui_model(schema_doc: dict[str, Any] | None = None) -> dict[str, FieldSpec]:
    """The ordered ``pointer → FieldSpec`` map over `$defs/SyncConfig`.

    Top-level properties carry their own `x-wiki-scope` (missing → root-only, the
    conservative reading: an unannotated new key is NOT presented as cascading
    until someone declares it so); every nested pointer inherits its top-level
    ancestor's scope."""
    doc = schema_doc if schema_doc is not None else load_sync_schema_doc()
    defs = doc.get("$defs")
    if not isinstance(defs, dict):
        raise ValueError("sync-config schema: missing $defs")
    sync = defs.get("SyncConfig")
    if not isinstance(sync, dict) or not isinstance(sync.get("properties"), dict):
        raise ValueError("sync-config schema: missing $defs/SyncConfig.properties")
    out: dict[str, FieldSpec] = {}
    for name, child in sync["properties"].items():
        if not isinstance(child, dict):
            continue
        scope = str(child.get("x-wiki-scope") or SCOPE_ROOT_ONLY)
        _walk(out, child, defs, f"/{name}", scope)
    return out


def top_level_keys(model: dict[str, FieldSpec], scope: str) -> tuple[str, ...]:
    """Top-level sync.yaml key names having the given scope (schema order)."""
    return tuple(
        ptr.lstrip("/")
        for ptr, spec in model.items()
        if "/" not in ptr.lstrip("/") and spec.scope == scope
    )
