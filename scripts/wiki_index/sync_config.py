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


# --------------------------------------------------------------------------- #
# Resummarize policy (TASK 019) — typed, frozen mirror of `$def Resummarize`.
# Built bead 01 (dataclasses + schema); populated by the loader in bead 02.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class MirrorKey:
    """Extended D2b key extraction (TASK 019 / Q-019-5). Separate regex per side
    (raw filenames vs summary filenames may differ) composed via a `string.Template`
    over named groups; `flags` ∈ {ignorecase, unicode}."""

    raw_regex: str | None = None
    summary_regex: str | None = None
    template: str | None = None
    flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class MirrorConfig:
    """D2b structural-mirror detector. `match`: `stem-relpath` (1:1, same stem) or
    `group-key` (N:1, key shared across many raw → one summary). `summary_dir: "."`
    = the raw file's own folder (same-dir office↔md case)."""

    enabled: bool = False
    raw_dirs: tuple[str, ...] = ("_raw", "_transcripts")
    summary_dir: str = "_summary"
    summary_ext: str = ".md"
    match: str = "group-key"
    group_key: str | None = None
    key: MirrorKey | None = None


@dataclass(frozen=True)
class ProvenanceConfig:
    """D2a provenance detector — a page's frontmatter `fields` cites the raw file
    by `match` (vault-rel-path | basename)."""

    enabled: bool = False
    fields: tuple[str, ...] = ("source", "sources")
    match: str = "vault-rel-path"


@dataclass(frozen=True)
class DetectConfig:
    """The detector union. Default (when `detect` omitted, OQ-5) = source_state only."""

    source_state: bool = True
    provenance_ref: ProvenanceConfig = field(default_factory=ProvenanceConfig)
    mirror: MirrorConfig = field(default_factory=MirrorConfig)


@dataclass(frozen=True)
class ResummarizeConfig:
    """The re-summarization policy (TASK 019). `mode` ∈ {if-missing, always, never}."""

    mode: str = "if-missing"
    detect: DetectConfig = field(default_factory=DetectConfig)


@dataclass(frozen=True)
class TranscriptDedupConfig:
    """TASK 023 — transcript FORMAT dedup. When several caption/transcript formats
    of the same recording coexist, ingest only the highest-preference one. `None`
    on `SyncConfig` (block absent) ≡ disabled (back-compat). `identity` ∈
    {stem, before-first-dot}; `prefer_ext` is most-preferred-first."""

    enabled: bool = False
    prefer_ext: tuple[str, ...] = (".txt", ".vtt", ".srt")
    identity: str = "stem"


@dataclass(frozen=True)
class SummarizeConfig:
    """TASK 046 P3 — per-zone distil knobs wiki-sync passes to the delegated wiki-import.
    `profile` resolves to the wiki-import `--kind` (`auto` → wiki-import auto-detects;
    `meeting`/`lesson` → pyramid grammar; `article` → article wrapper). The defaults below
    are EXACTLY the P2 hardcoded delegate (auto / no diagrams / concepts ON / no subdir), so
    a vault with no `summarize:` block is byte-identical to P2 (back-compat / R-12)."""

    profile: str = "auto"
    diagrams: bool = False
    extract_concepts: bool = True
    target_subdir: str = ""


@dataclass(frozen=True)
class SyncConfig:
    """The merged `.wiki/sync.yaml` the dispatcher consumes.

    The `extensions_*` tuples are operator OVERRIDES that *extend* the built-in
    routing sets in `scripts/wiki_skills/_sync.py` (they never shrink them).
    `resummarize` (TASK 019) is the OPT-IN re-summarization policy; `None` ≡ the
    TASK 018 behavior (back-compat / byte-identity). `transcript_dedup` (TASK 023)
    is the OPT-IN transcript-format dedup; `None` ≡ disabled."""

    zones: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    tag_namespace: str = "wiki"
    extensions_convert: tuple[str, ...] = field(default_factory=tuple)
    extensions_text: tuple[str, ...] = field(default_factory=tuple)
    extensions_skip: tuple[str, ...] = field(default_factory=tuple)
    resummarize: ResummarizeConfig | None = None
    transcript_dedup: TranscriptDedupConfig | None = None
    summarize: SummarizeConfig | None = None


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
    raw = _load_validated_raw(vault_root)
    if not raw:
        return SyncConfig()
    ext = raw.get("extensions") or {}
    return SyncConfig(
        zones=tuple(raw.get("zones") or ()),
        exclude=tuple(raw.get("exclude") or ()),
        tag_namespace=str(raw.get("tag_namespace") or "wiki"),
        extensions_convert=tuple(ext.get("convert") or ()),
        extensions_text=tuple(ext.get("text") or ()),
        extensions_skip=tuple(ext.get("skip") or ()),
        resummarize=_parse_resummarize(raw.get("resummarize")),
        transcript_dedup=_parse_transcript_dedup(raw.get("transcript_dedup")),
        summarize=_parse_summarize(raw.get("summarize")),
    )


def _parse_summarize(block: Any) -> SummarizeConfig | None:
    """Build the typed `SummarizeConfig` from a schema-validated `summarize` block
    (`None` when absent ≡ the P2 defaults). Already strict-validated, so the enum/types
    are sound; apply the field defaults jsonschema does not inject."""
    if not block:
        return None
    return SummarizeConfig(
        profile=str(block.get("profile") or "auto"),
        diagrams=bool(block.get("diagrams", False)),
        extract_concepts=bool(block.get("extract_concepts", True)),
        target_subdir=str(block.get("target_subdir") or ""),
    )


def load_summarize_raw(root: Path) -> dict[str, Any] | None:
    """The RAW (un-parsed, schema-validated) ``summarize`` block of ``<root>/.wiki/sync.yaml``,
    or ``None`` if absent. The per-folder cascade resolver deep-merges these RAW dicts
    deepest-wins *before* applying defaults, so a folder override that sets only ``diagrams``
    INHERITS the parent's ``profile`` (partial override). Reuses ``_load_validated_raw``."""
    block = _load_validated_raw(root).get("summarize")
    return block if isinstance(block, dict) else None


def _parse_transcript_dedup(block: Any) -> TranscriptDedupConfig | None:
    """Build the typed `TranscriptDedupConfig` from a schema-validated
    `transcript_dedup` block (`None` when absent ≡ disabled). `prefer_ext` is
    lower-cased; an empty/missing list falls back to the (.txt, .vtt, .srt) default."""
    if not block:
        return None
    pe = block.get("prefer_ext")
    return TranscriptDedupConfig(
        enabled=bool(block.get("enabled", False)),
        prefer_ext=tuple(str(e).lower() for e in pe) if pe else (".txt", ".vtt", ".srt"),
        identity=str(block.get("identity") or "stem"),
    )


def _load_validated_raw(root: Path) -> dict[str, Any]:
    """Hardened read + strict-validate of ``<root>/.wiki/sync.yaml`` → the raw
    config dict (``{}`` if absent/empty). The order is load-bearing: (0) symlink
    containment, (1) 256 KiB size cap before read, (2) anchor-ban parse, (3) strict
    schema. Shared by ``load_sync_config`` (vault root) AND the TASK 019 per-folder
    cascade resolver — so EVERY override level inherits the SAME hardening. Raises
    ``SyncConfigError`` (→ exit 6) on any failure, never echoing the value."""
    path = root / ".wiki" / "sync.yaml"
    if not path.is_file():
        return {}

    # (0) symlink containment (O_NOFOLLOW posture). Two layers: (a) refuse a
    # symlinked LEAF `sync.yaml`; (b) resolve the FULL path + re-validate it is
    # inside `root`, so a symlinked parent `.wiki/` cannot redirect the read out.
    if path.is_symlink():
        raise SyncConfigError("INVALID_SYNC_CONFIG", "config is a symlink")
    try:
        validate_inside_vault(path, root)
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

    # (2) anchor-ban parse. PyYAML's composer is recursive, so a sub-cap but
    # deeply-nested anchorless payload raises `RecursionError` (not `YAMLError`) —
    # map every non-`SyncConfigError` parse failure to the controlled error.
    raw_text = path.read_text(encoding="utf-8")
    try:
        raw = yaml.load(raw_text, Loader=_NoAliasSafeLoader)  # noqa: S506 (custom safe loader)
    except SyncConfigError:
        raise
    except (yaml.YAMLError, RecursionError, ValueError) as exc:
        raise SyncConfigError("INVALID_SYNC_CONFIG", "config is not parseable") from exc
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise SyncConfigError("INVALID_SYNC_CONFIG", "config must be a YAML mapping")

    # (3) strict schema.
    _validate(raw)
    return raw


def load_resummarize_raw(root: Path) -> dict[str, Any] | None:
    """The RAW (un-parsed, schema-validated) ``resummarize`` block of
    ``<root>/.wiki/sync.yaml``, or ``None`` if absent. TASK 019: the cascade
    resolver deep-merges these RAW dicts deepest-wins *before* applying defaults,
    so a folder override that sets only ``mode`` correctly INHERITS the parent's
    ``detect`` (partial override). Reuses ``_load_validated_raw`` (all hardening)."""
    block = _load_validated_raw(root).get("resummarize")
    return block if isinstance(block, dict) else None


def _parse_resummarize(block: Any) -> ResummarizeConfig | None:
    """Build the typed `ResummarizeConfig` from a schema-validated `resummarize`
    block, applying the defaults jsonschema does NOT inject (TASK 019 / Q-019-2):
      * absent block → `None` (≡ TASK 018 / AC-7);
      * omitted `detect` → `{source_state: True}` only (OQ-5);
      * `mirror.match` defaults to `group-key` when `key`/`group_key` is supplied,
        else `stem-relpath`.
    `block` is already strict-validated by `_validate`, so shapes/enums are sound.
    """
    if block is None:
        return None
    mode = str(block.get("mode") or "if-missing")
    det = block.get("detect")
    if not isinstance(det, dict):
        return ResummarizeConfig(mode=mode, detect=DetectConfig())

    prov_raw = det.get("provenance_ref") or {}
    provenance = ProvenanceConfig(
        enabled=bool(prov_raw.get("enabled", False)),
        fields=tuple(prov_raw.get("fields") or ("source", "sources")),
        match=str(prov_raw.get("match") or "vault-rel-path"),
    )

    mir_raw = det.get("mirror") or {}
    key_raw = mir_raw.get("key")
    key = None
    if isinstance(key_raw, dict):
        key = MirrorKey(
            raw_regex=key_raw.get("raw_regex"),
            summary_regex=key_raw.get("summary_regex"),
            template=key_raw.get("template"),
            flags=tuple(key_raw.get("flags") or ()),
        )
    if "match" in mir_raw:
        match = str(mir_raw["match"])
    elif key is not None or mir_raw.get("group_key"):
        match = "group-key"
    else:
        match = "stem-relpath"
    mirror = MirrorConfig(
        enabled=bool(mir_raw.get("enabled", False)),
        raw_dirs=tuple(mir_raw.get("raw_dirs") or ("_raw", "_transcripts")),
        summary_dir=str(mir_raw.get("summary_dir") or "_summary"),
        summary_ext=str(mir_raw.get("summary_ext") or ".md"),
        match=match,
        group_key=mir_raw.get("group_key"),
        key=key,
    )
    return ResummarizeConfig(
        mode=mode,
        detect=DetectConfig(
            source_state=bool(det.get("source_state", True)),
            provenance_ref=provenance,
            mirror=mirror,
        ),
    )
