"""TASK 058 — the provenance engine: WHO defines each effective sync.yaml value.

Replays the Option-A cascade with the resolver's OWN primitives — `_ancestor_dirs`
(chain), `_load_validated_raw` (full hardening at every level), `deep_merge` (the
real merge), `_parse_resummarize`/`_parse_summarize` (the real defaults) — and, in
parallel, records per-JSON-pointer origins. The origin-assignment walk mirrors
`deep_merge`'s branch condition character-for-character (dict+dict → recurse; else
the incoming pointer and its whole subtree are claimed by the current level), so
the labels cannot diverge from the merge semantics. Which top-level keys cascade
vs are root-only is read from the SCHEMA's `x-wiki-scope` annotations via
`_uimodel` — no key name is hardcoded here (evolution invariant, R-058-10).

The real resolver (`scripts/wiki_skills/_resummarize.py`) is NOT modified or
called at runtime; an equivalence test (tests/test_wiki_config_provenance.py)
release-gates that `parse(merged_here) == resolve_policy()/resolve_summarize()`.

Read-only: this module never writes.
"""

from __future__ import annotations

import dataclasses
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from scripts.wiki_index.config_loader import deep_merge
from scripts.wiki_index.sync_config import (
    SummarizeConfig,
    SyncConfigError,
    _load_validated_raw,
    _parse_resummarize,
    _parse_summarize,
)
from scripts.wiki_skills._resummarize import _ancestor_dirs

from ._uimodel import (
    SCOPE_CASCADING,
    SCOPE_ROOT_ONLY,
    FieldSpec,
    build_ui_model,
    top_level_keys,
)

ROOT_LABEL = "root"

# Directories never descended into by the tree scan. `.wiki` itself is probed
# for `sync.yaml` at each visited dir, never walked.
_PRUNE_DIRS = frozenset({".git", ".obsidian", ".trash", "node_modules"})


class SyncConfigLevelError(SyncConfigError):
    """A cascade level whose `.wiki/sync.yaml` fails the hardened load. Carries
    the offending LEVEL label (a vault-relative folder path — safe to echo);
    the file's values are never echoed (CWE-209)."""

    def __init__(self, level: str, cause: SyncConfigError) -> None:
        super().__init__(cause.code, cause.detail, reason=cause.reason)
        self.level = level


@dataclass(frozen=True)
class Origin:
    """Provenance of one effective value: which level supplied it (`default` |
    `root` | a vault-relative folder path) and which shallower levels it shadows."""

    origin: str
    shadows: tuple[str, ...] = ()
    scope: str = SCOPE_CASCADING
    note: str = ""

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"origin": self.origin, "scope": self.scope}
        if self.shadows:
            out["shadows"] = list(self.shadows)
        if self.note:
            out["note"] = self.note
        return out


def resolve_origin(origins: Mapping[str, Origin], pointer: str) -> Origin | None:
    """`origins.get(pointer)`, falling back to the NEAREST ANCESTOR pointer's
    origin when the exact pointer carries none of its own — the leaves of a
    configured, nested root-only block (e.g. `/transcript_dedup/enabled`) get
    no per-leaf origin entry from the assignment fold above; they inherit the
    block's own (root) origin. Additive only: never overrides an entry that
    already exists at `pointer` itself."""
    origin = origins.get(pointer)
    probe = pointer
    while origin is None and "/" in probe.lstrip("/"):
        probe = probe.rsplit("/", 1)[0]
        origin = origins.get(probe)
    return origin


@dataclass(frozen=True)
class LevelInfo:
    """One configured cascade level (a dir that HAS `.wiki/sync.yaml`)."""

    level: str
    file: str
    defines: tuple[str, ...]
    ignored: tuple[str, ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "file": self.file,
            "defines": list(self.defines),
            "ignored": list(self.ignored),
        }


@dataclass
class FolderProvenance:
    """The `show` result: effective config + per-pointer origins for one folder."""

    folder: str
    effective: dict[str, Any] = field(default_factory=dict)
    origins: dict[str, Origin] = field(default_factory=dict)
    levels: list[LevelInfo] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    # RAW merged cascading blocks — the equivalence-test surface.
    merged_raw: dict[str, dict[str, Any] | None] = field(default_factory=dict)


@dataclass(frozen=True)
class TreeNode:
    """One configured folder in the `tree` map."""

    folder: str
    defines: dict[str, str]
    ignored: tuple[str, ...]
    overridden_by: dict[str, tuple[str, ...]]
    error: dict[str, str] | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "folder": self.folder,
            "defines": dict(self.defines),
            "ignored": list(self.ignored),
            "overridden_by": {p: list(v) for p, v in self.overridden_by.items()},
            "error": dict(self.error) if self.error else None,
        }


# --------------------------------------------------------------------------- #
# Origin-assignment fold (mirrors deep_merge)
# --------------------------------------------------------------------------- #


def _claim_subtree(origins: dict[str, Origin], value: Any, pointer: str, label: str) -> None:
    """Claim `pointer` (and, when `value` is a dict, every descendant pointer)
    for `label`, pushing any previous different owner onto the shadow chain."""
    prev = origins.get(pointer)
    if prev is not None and prev.origin != label:
        origins[pointer] = Origin(label, shadows=prev.shadows + (prev.origin,))
    elif prev is None:
        origins[pointer] = Origin(label)
    if isinstance(value, dict):
        for key, child in value.items():
            _claim_subtree(origins, child, f"{pointer}/{key}", label)


def _assign_origins(
    origins: dict[str, Origin],
    base: dict[str, Any],
    override: dict[str, Any],
    label: str,
    prefix: str,
) -> None:
    """Mirror of `deep_merge`: same branch condition, but instead of building the
    merged dict it records which level owns each pointer after this step."""
    for key, override_val in override.items():
        pointer = f"{prefix}/{key}"
        base_val = base.get(key)
        if isinstance(base_val, dict) and isinstance(override_val, dict):
            _assign_origins(origins, base_val, override_val, label, pointer)
        else:
            if isinstance(base_val, dict) and not isinstance(override_val, dict):
                # scalar-over-dict replace: the old subtree no longer exists.
                for stale in [p for p in origins if p.startswith(pointer + "/")]:
                    del origins[stale]
            _claim_subtree(origins, override_val, pointer, label)


def _to_jsonable(value: Any) -> Any:
    """Frozen-dataclass → plain JSON-able structure (tuples become lists)."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _to_jsonable(dataclasses.asdict(value))
    if isinstance(value, dict):
        return {k: _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(v) for v in value]
    return value


def _leaf_pointers(block: dict[str, Any], prefix: str) -> list[str]:
    """All leaf (non-dict) pointers inside a raw block, `prefix`-rooted."""
    out: list[str] = []
    for key, value in block.items():
        pointer = f"{prefix}/{key}"
        if isinstance(value, dict):
            out.extend(_leaf_pointers(value, pointer))
        else:
            out.append(pointer)
    return out


def _tag_defaults(
    origins: dict[str, Origin], effective: Any, pointer: str, scope: str
) -> None:
    """Every leaf pointer present in the EFFECTIVE tree but claimed by no level
    is a built-in default (the parsers inject those, jsonschema does not)."""
    if isinstance(effective, dict):
        for key, child in effective.items():
            _tag_defaults(origins, child, f"{pointer}/{key}", scope)
        return
    if pointer not in origins:
        origins[pointer] = Origin("default", scope=scope)


def _rel_label(d: Path, vault_root: Path) -> str:
    rel = d.relative_to(vault_root).as_posix()
    return ROOT_LABEL if rel == "." else rel


# --------------------------------------------------------------------------- #
# show
# --------------------------------------------------------------------------- #


def compute_folder_provenance(
    folder: Path,
    vault_root: Path,
    model: dict[str, FieldSpec] | None = None,
    raw_cache: dict[Path, dict[str, Any] | SyncConfigError] | None = None,
) -> FolderProvenance:
    """Effective config + per-pointer provenance for `folder`.

    Raises `SyncConfigLevelError` (a `SyncConfigError`) when ANY ancestor level
    fails the hardened load — matching the resolver, which would refuse the scan:
    an effective config computed over a broken level would be a lie.

    `raw_cache` (default `None` → a fresh, call-local dict — fully
    backward-compatible) memoizes `_load_validated_raw` per ancestor DIR so a
    caller building provenance for MANY folders (e.g. `_report.py`'s
    per-folder loop) loads each shared ancestor (the vault root, above all)
    exactly once instead of once per folder."""
    ui = model if model is not None else build_ui_model()
    cascading = top_level_keys(ui, SCOPE_CASCADING)
    root_only = top_level_keys(ui, SCOPE_ROOT_ONLY)
    cache = raw_cache if raw_cache is not None else {}

    chain = _ancestor_dirs(folder / "_probe_", vault_root)
    raws: list[tuple[str, dict[str, Any]]] = []
    has_file: dict[str, bool] = {}
    for d in chain:
        label = _rel_label(d, vault_root)
        has_file[label] = (d / ".wiki" / "sync.yaml").is_file()
        cached = cache.get(d)
        if cached is None:
            try:
                cached = _load_validated_raw(d)
            except SyncConfigError as exc:
                cache[d] = exc
                raise SyncConfigLevelError(label, exc) from exc
            cache[d] = cached
        elif isinstance(cached, SyncConfigError):
            raise SyncConfigLevelError(label, cached)
        raws.append((label, cached))

    rel_folder = _rel_label(folder, vault_root)
    prov = FolderProvenance(folder="." if rel_folder == ROOT_LABEL else rel_folder)

    # Configured levels + the ignored-key trap (root-only key in a non-root file).
    for label, raw in raws:
        if not has_file[label]:
            continue
        defines: list[str] = []
        ignored: list[str] = []
        for key, value in raw.items():
            if key in cascading and isinstance(value, dict):
                defines.extend(_leaf_pointers(value, f"/{key}"))
            elif label == ROOT_LABEL:
                defines.append(f"/{key}")
            else:
                ignored.append(key)
        rel_file = (f"{label}/" if label != ROOT_LABEL else "") + ".wiki/sync.yaml"
        prov.levels.append(LevelInfo(label, rel_file, tuple(defines), tuple(ignored)))
        if ignored:
            prov.warnings.append({
                "code": "NON_CASCADING_KEY_IN_SUBFOLDER",
                "level": label,
                "keys": ignored,
                "hint": ("these keys are consumed ONLY from the vault-root "
                         ".wiki/sync.yaml and have NO effect in this folder"),
            })

    # Cascading blocks: fold with the REAL deep_merge, mirror origins alongside.
    for block_name in cascading:
        merged: dict[str, Any] = {}
        found = False
        for label, raw in raws:
            block = raw.get(block_name)
            if isinstance(block, dict):
                found = True
                _assign_origins(prov.origins, merged, block, label, f"/{block_name}")
                merged = deep_merge(merged, block)
        prov.merged_raw[block_name] = merged if found else None

        # Parse with the REAL parsers, in the resolvers' exact call shape.
        effective_block: Any
        if block_name == "resummarize":
            typed = _parse_resummarize(merged) if found else None
            effective_block = _to_jsonable(typed) if typed is not None else None
        elif block_name == "summarize":
            effective_block = _to_jsonable(_parse_summarize(merged) or SummarizeConfig())
        else:  # a future cascading block: expose the merged RAW dict as-is
            effective_block = merged if found else None
        prov.effective[block_name] = effective_block
        if effective_block is None:
            prov.origins[f"/{block_name}"] = Origin(
                "default", scope=SCOPE_CASCADING,
                note="not configured at any level",
            )
        else:
            _tag_defaults(prov.origins, effective_block, f"/{block_name}", SCOPE_CASCADING)

    # Root-only keys: consumed from the vault root only (by construction).
    root_raw = raws[0][1] if raws else {}
    for key in root_only:
        pointer = f"/{key}"
        spec = ui.get(pointer)
        if key in root_raw:
            prov.effective[key] = root_raw[key]
            prov.origins[pointer] = Origin(ROOT_LABEL, scope=SCOPE_ROOT_ONLY)
        else:
            prov.effective[key] = spec.default if spec is not None else None
            prov.origins[pointer] = Origin("default", scope=SCOPE_ROOT_ONLY)

    return prov


# --------------------------------------------------------------------------- #
# tree
# --------------------------------------------------------------------------- #

# Same bound + truncation contract as the `/api/tree` endpoint (bounded
# operator-facing scan, never a full-vault crawl with no ceiling).
_TREE_WALK_CAP = 5000


@dataclass(frozen=True)
class WalkedFolder:
    """One directory visited by `walk_vault_tree` — label + resolved path +
    whether it carries its own `.wiki/sync.yaml`."""

    label: str
    path: Path
    configured: bool


def walk_vault_tree(vault_root: Path) -> tuple[list[WalkedFolder], bool]:
    """The ONE walk feeding both the `/api/tree` flat folder list and
    `scan_tree`'s configured-node map (previously two separate `os.walk`s —
    one here, one in `_server.py`). Capped at `_TREE_WALK_CAP` visited dirs;
    the second return value mirrors the endpoint's `truncated` semantics."""
    out: list[WalkedFolder] = []
    truncated = False
    for dirpath, dirnames, _filenames in os.walk(vault_root, followlinks=False):
        dirnames[:] = sorted(
            d for d in dirnames if d not in _PRUNE_DIRS and not d.startswith(".")
        )
        d = Path(dirpath)
        label = _rel_label(d, vault_root)
        label = "." if label == ROOT_LABEL else label
        out.append(WalkedFolder(label, d, (d / ".wiki" / "sync.yaml").is_file()))
        if len(out) >= _TREE_WALK_CAP:
            truncated = True
            break
    return out, truncated


def _is_descendant(child: str, parent: str) -> bool:
    if parent == ".":
        return child != "."
    return child != parent and child.startswith(parent + "/")


def scan_tree_from_walk(
    walked: list[WalkedFolder], model: dict[str, FieldSpec] | None = None
) -> list[TreeNode]:
    """`scan_tree`'s node-building pass over an ALREADY-WALKED folder list (no
    filesystem walk of its own) — the piece `/api/tree` reuses to avoid a
    second `os.walk` over the same vault."""
    ui = model if model is not None else build_ui_model()
    cascading = set(top_level_keys(ui, SCOPE_CASCADING))

    configured: list[tuple[str, dict[str, Any] | None, dict[str, str] | None]] = []
    for wf in walked:
        if not wf.configured:
            continue
        try:
            configured.append((wf.label, _load_validated_raw(wf.path), None))
        except SyncConfigError as exc:
            configured.append(
                (wf.label, None,
                 {"code": exc.code, "reason": exc.reason, "detail": exc.detail})
            )

    # Per-node defines (pointer → scope), for the cross-node overridden_by pass.
    defines_by_node: dict[str, dict[str, str]] = {}
    ignored_by_node: dict[str, tuple[str, ...]] = {}
    for label, raw, error in configured:
        if raw is None:
            continue
        defines: dict[str, str] = {}
        ignored: list[str] = []
        for key, value in raw.items():
            if key in cascading and isinstance(value, dict):
                for pointer in _leaf_pointers(value, f"/{key}"):
                    defines[pointer] = SCOPE_CASCADING
            elif label == ".":
                defines[f"/{key}"] = SCOPE_ROOT_ONLY
            else:
                ignored.append(key)
        defines_by_node[label] = defines
        ignored_by_node[label] = tuple(ignored)

    nodes: list[TreeNode] = []
    for label, raw, error in configured:
        if raw is None:
            nodes.append(TreeNode(label, {}, (), {}, error))
            continue
        defines = defines_by_node[label]
        overridden: dict[str, tuple[str, ...]] = {}
        for pointer, scope in defines.items():
            if scope != SCOPE_CASCADING:
                continue
            deeper = tuple(
                other
                for other, other_defines in defines_by_node.items()
                if _is_descendant(other, label) and pointer in other_defines
            )
            if deeper:
                overridden[pointer] = deeper
        nodes.append(TreeNode(label, defines, ignored_by_node[label], overridden))
    return nodes


def scan_tree(
    vault_root: Path, model: dict[str, FieldSpec] | None = None
) -> list[TreeNode]:
    """Every configured folder (has `.wiki/sync.yaml`) with what it defines,
    which deeper folders override each cascading pointer, and which of its keys
    are silently ignored. A broken file yields an `error` node — the scan never
    aborts (unlike `show`, which must not lie about ONE folder's effective view).
    Bounded by `walk_vault_tree`'s `_TREE_WALK_CAP` — a truncated scan stays
    silent here (this narrow API has no truncation slot); `/api/tree` surfaces
    the real flag by calling `walk_vault_tree` + `scan_tree_from_walk` directly."""
    walked, _truncated = walk_vault_tree(vault_root)
    return scan_tree_from_walk(walked, model)
