"""`.wiki/sync.yaml` loader for `wiki-sync` (TASK 018 / R-11).

A SEPARATE config system from the per-vault identity (`config_loader.py`) and the
per-layout grammar (`layout_config.py`). The file is OPTIONAL — a vault with no
`.wiki/sync.yaml` uses the built-in defaults.

Security posture (locked across two adversarial gates — SEC-N3): the file is
operator-authored but treated as untrusted input. Two defenses, applied in this
order in `load_sync_config`:
  1. a 256 KiB `stat().st_size` cap *before* the file is read; and
  2. a `SafeLoader` subclass (`_NoAliasSafeLoader`) that REFUSES any YAML
     anchor/alias node — `yaml.safe_load` alone still *expands* aliases, so a
     232-byte "billion-laughs" bomb would explode into ~10⁶ nodes. The config is
     a flat glob-string mapping; anchors have no legitimate use here.
The schema (`config/sync-config.schema.yaml`) is STRICT (`additionalProperties:
false`), so a misspelled key is `INVALID_SYNC_CONFIG` (exit 6); the error message
never echoes the offending value (CWE-209/CWE-117).

Bead 03 (STUB): the dataclass, the error type, the size constant, the loader
returning defaults, and the `_NoAliasSafeLoader` class shell. Bead 04 (LOGIC)
fills in the size-cap, the anchor-ban, and jsonschema validation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from scripts.wiki_index.security import PathTraversalError, validate_inside_vault

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SCHEMA_PATH = _REPO_ROOT / "config" / "sync-config.schema.yaml"

# Defense (1): refuse any `.wiki/sync.yaml` larger than this BEFORE reading it.
WIKI_SYNC_CONFIG_MAX_BYTES = 256 * 1024


class SyncConfigError(ValueError):
    """A `.wiki/sync.yaml` that fails the size cap, the anchor-ban, or the strict
    schema. Carries a stable ``code`` (always ``"INVALID_SYNC_CONFIG"``) + a short
    ``detail`` that NEVER contains the offending config value (CWE-209/CWE-117) —
    the CLI maps it to exit 6."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class SyncConfig:
    """The merged `.wiki/sync.yaml` the dispatcher consumes.

    The `extensions_*` tuples are operator OVERRIDES that *extend* the built-in
    routing sets in `scripts/wiki_skills/_sync.py` (they never shrink them)."""

    zones: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    tag_namespace: str = "wiki"
    extensions_convert: tuple[str, ...] = field(default_factory=tuple)
    extensions_text: tuple[str, ...] = field(default_factory=tuple)
    extensions_skip: tuple[str, ...] = field(default_factory=tuple)


class _NoAliasSafeLoader(yaml.SafeLoader):
    """A `SafeLoader` that REFUSES YAML anchors/aliases.

    `yaml.safe_load` is safe against arbitrary object construction but it STILL
    expands aliases — a 232-byte billion-laughs bomb explodes into ~10⁶ nodes
    before any of our validation runs (SEC-N3). We refuse at *compose* time:
      * an `AliasEvent` (a `*ref` use) → refuse before the referenced node is
        ever duplicated; and
      * an `anchor` on any event (a `&name` definition) → refuse before it is
        registered, so even an *unused* anchor is rejected.
    The config is a flat glob-string mapping; anchors have no legitimate use.
    """

    def compose_node(
        self, parent: yaml.nodes.Node | None, index: int
    ) -> yaml.nodes.Node | None:
        if self.check_event(yaml.events.AliasEvent):  # type: ignore[no-untyped-call]
            raise SyncConfigError("INVALID_SYNC_CONFIG", "yaml alias is not allowed")
        event = self.peek_event()  # type: ignore[no-untyped-call]
        if getattr(event, "anchor", None) is not None:
            raise SyncConfigError("INVALID_SYNC_CONFIG", "yaml anchor is not allowed")
        return super().compose_node(parent, index)


_VALIDATOR: Draft202012Validator | None = None


def _get_validator() -> Draft202012Validator:
    """Module-level singleton (mirrors `layout_config._get_validator`): read +
    meta-validate the static schema + build the validator ONCE per process."""
    global _VALIDATOR
    if _VALIDATOR is None:
        schema_doc = yaml.safe_load(_SCHEMA_PATH.read_text(encoding="utf-8"))
        if not isinstance(schema_doc, dict):
            raise SyncConfigError("INVALID_SYNC_CONFIG", "schema is not a mapping")
        Draft202012Validator.check_schema(schema_doc)
        _VALIDATOR = Draft202012Validator(
            {**schema_doc, "$ref": "#/$defs/SyncConfig"}
        )
    return _VALIDATOR


def _validate(merged: dict[str, Any]) -> None:
    """Strict-validate `merged` against #/$defs/SyncConfig. Raises
    `SyncConfigError` naming the JSON pointer only — NEVER the offending value
    (CWE-209/CWE-117)."""
    errors = sorted(
        _get_validator().iter_errors(merged), key=lambda e: list(e.absolute_path)
    )
    if errors:
        pointers = sorted({
            "/" + "/".join(str(p) for p in e.absolute_path) if e.absolute_path else "/"
            for e in errors
        })
        raise SyncConfigError(
            "INVALID_SYNC_CONFIG",
            "schema validation failed at: " + ", ".join(pointers),
        )


def load_sync_config(vault_root: Path) -> SyncConfig:
    """Load `<vault_root>/.wiki/sync.yaml`, or return defaults if absent.

    Order is load-bearing: (1) size cap before read; (2) anchor-ban parse;
    (3) strict schema validation. Raises `SyncConfigError` (→ exit 6) on any
    failure, never echoing the offending value.
    """
    path = vault_root / ".wiki" / "sync.yaml"
    if not path.is_file():
        return SyncConfig()

    # (0) symlink containment (O_NOFOLLOW posture, matching the walk +
    # `_common.resolve_entity_file`). Two layers (critic-security MED): (a) refuse
    # a symlinked LEAF `sync.yaml`; (b) resolve the FULL path + re-validate it is
    # inside the vault, so a symlinked *parent* `.wiki/` dir cannot redirect
    # `stat()`/`read_text` to an arbitrary out-of-vault YAML.
    if path.is_symlink():
        raise SyncConfigError("INVALID_SYNC_CONFIG", "config is a symlink")
    try:
        validate_inside_vault(path, vault_root)
    except PathTraversalError as exc:
        raise SyncConfigError(
            "INVALID_SYNC_CONFIG", "config resolves outside the vault"
        ) from exc
    except OSError as exc:
        raise SyncConfigError(
            "INVALID_SYNC_CONFIG", "config path is unresolvable"
        ) from exc

    # (1) size cap — refuse BEFORE reading the bytes.
    if path.stat().st_size > WIKI_SYNC_CONFIG_MAX_BYTES:
        raise SyncConfigError("INVALID_SYNC_CONFIG", "config exceeds the 256 KiB cap")

    # (2) anchor-ban parse. The parse of an UNTRUSTED file must never propagate
    # an internal error: besides `yaml.YAMLError`, PyYAML's *composer* is
    # genuinely recursive (one Python frame per nesting level), so a sub-cap but
    # deeply-nested anchorless payload (e.g. `zones: ` + `[`×2000) raises
    # `RecursionError` (a `RuntimeError`, NOT a `YAMLError`) — the size cap alone
    # does not bound nesting (critic-security HIGH). We map every non-
    # `SyncConfigError` parse failure to the controlled `INVALID_SYNC_CONFIG`
    # (exit 6, no traceback → no CWE-209 leak, never crashes the batch).
    raw_text = path.read_text(encoding="utf-8")
    try:
        raw = yaml.load(raw_text, Loader=_NoAliasSafeLoader)  # noqa: S506 (custom safe loader)
    except SyncConfigError:
        raise
    except (yaml.YAMLError, RecursionError, ValueError) as exc:
        # Never echo file content (CWE-209/CWE-117).
        raise SyncConfigError("INVALID_SYNC_CONFIG", "config is not parseable") from exc
    if raw is None:
        return SyncConfig()
    if not isinstance(raw, dict):
        raise SyncConfigError("INVALID_SYNC_CONFIG", "config must be a YAML mapping")

    # (3) strict schema.
    _validate(raw)

    ext = raw.get("extensions") or {}
    return SyncConfig(
        zones=tuple(raw.get("zones") or ()),
        exclude=tuple(raw.get("exclude") or ()),
        tag_namespace=str(raw.get("tag_namespace") or "wiki"),
        extensions_convert=tuple(ext.get("convert") or ()),
        extensions_text=tuple(ext.get("text") or ()),
        extensions_skip=tuple(ext.get("skip") or ()),
    )
