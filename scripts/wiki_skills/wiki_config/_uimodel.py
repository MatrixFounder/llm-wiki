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

from collections.abc import Mapping
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


def _build_ui_model_uncached(doc: dict[str, Any]) -> dict[str, FieldSpec]:
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


# (resolved schema path, mtime_ns) → model. Mirrors `sync_config._get_validator`'s
# process-lifetime singleton, but keyed on mtime (not a bare None-check) so a
# test that swaps `SYNC_SCHEMA_PATH` — or rewrites the file at the same path —
# still observes a fresh model instead of a stale cached one.
_MODEL_CACHE: tuple[tuple[Path, int], dict[str, FieldSpec]] | None = None


def build_ui_model(schema_doc: dict[str, Any] | None = None) -> dict[str, FieldSpec]:
    """The ordered ``pointer → FieldSpec`` map over `$defs/SyncConfig`.

    Top-level properties carry their own `x-wiki-scope` (missing → root-only, the
    conservative reading: an unannotated new key is NOT presented as cascading
    until someone declares it so); every nested pointer inherits its top-level
    ancestor's scope.

    Callers: `/api/schema`, the provenance engine, `scan_tree`, `_Linter` — all
    on the hot path of a single request/lint run, all re-reading + re-parsing
    the (unchanging) schema YAML before this cache. An explicit `schema_doc`
    (the R-058-10 evolution-invariant test's synthetic doc) always bypasses the
    cache — it is never the shipped file."""
    if schema_doc is not None:
        return _build_ui_model_uncached(schema_doc)
    global _MODEL_CACHE
    key = (SYNC_SCHEMA_PATH.resolve(), SYNC_SCHEMA_PATH.stat().st_mtime_ns)
    if _MODEL_CACHE is None or _MODEL_CACHE[0] != key:
        _MODEL_CACHE = (key, _build_ui_model_uncached(load_sync_schema_doc()))
    # Current call sites are verified read-only (grep at TASK time); a shallow
    # copy is cheap insurance against a future caller mutating the dict in
    # place and corrupting every OTHER caller's shared cached model.
    return dict(_MODEL_CACHE[1])


def top_level_keys(model: dict[str, FieldSpec], scope: str) -> tuple[str, ...]:
    """Top-level sync.yaml key names having the given scope (schema order)."""
    return tuple(
        ptr.lstrip("/")
        for ptr, spec in model.items()
        if "/" not in ptr.lstrip("/") and spec.scope == scope
    )


def resolve_description(model: Mapping[str, FieldSpec], pointer: str) -> str:
    """The schema description for a rendered row's pointer.

    A pointer WITH a FieldSpec always gets its OWN description — even when that
    description is empty. Only a pointer with NO FieldSpec at all falls back to
    the nearest ANCESTOR that declares one; "" when none does.

    That split is load-bearing (TASK 061 fix-loop / LOW): a described block must
    never lend its text to a child that has a FieldSpec of its own, or the row
    for an undescribed field would silently render its PARENT's meaning — a wrong
    description reads as authoritative, which is worse than a blank one. It is the
    same asymmetry `resolve_origin` (`_provenance.py`) draws: fall back only where
    the model is SILENT, never where it has spoken.

    A bare `model[pointer].description` lookup would work on TODAY's shipped
    schema — `_report_md._flatten` recurses on `dict` ONLY, so a list is a leaf
    and `/zones` (which HAS a FieldSpec) is the row pointer, never `/zones/0`.
    That is precisely why the bare lookup is a trap: it is correct by coincidence,
    and its failure mode is a SILENT EMPTY STRING. Two live pointer classes
    already fall outside the model:
      * a raw-only key inside a parsed cascading block (TASK 061 / R-061-4's
        overlay puts `/summarize/<unknown>` into `effective`);
      * an array element, should `_flatten` ever learn to recurse into lists.

    HONEST BOUNDARY — what the fallback does on the SHIPPED schema TODAY: nothing.
    Not one object `$def` carries a `description:` (grep `^  [A-Za-z]*:$` +
    `description` in config/sync-config.schema.yaml — descriptions live on LEAF
    properties only), so `/summarize/<unknown>` walks to `/summarize` (empty) and
    resolves to "", not to "its declaring block's description" as this docstring
    once claimed. The mechanism is live the moment a block gains a `description:`;
    until then it is a guard, and saying so is the point. Pinned by
    tests/test_wiki_config_provenance.py::test_resolve_description_*.

    Callers (the FieldSpec.description render sinks — grep-enumerated, TASK 061-08):
    `_report._row_html` (HTML report), `_report_md.render_show_report` (the `show`
    markdown sidecar). `serve` reads `FieldSpec.description` directly off the model
    (`_server.py` `/api/schema` → `_app_html` `.hint`), and `show`'s JSON envelope
    emits the whole model's descriptions — neither needs a per-row fallback.
    `wiki-config tree` is a DELIBERATE exclusion: it answers "where is this key
    overridden?", not "what does it mean", and a description per folder x key would
    drown the override map."""
    spec = model.get(pointer)
    if spec is not None:
        return spec.description
    probe = pointer
    while "/" in probe.lstrip("/"):
        probe = probe.rsplit("/", 1)[0]
        ancestor = model.get(probe)
        if ancestor is not None and ancestor.description:
            return ancestor.description
    return ""
