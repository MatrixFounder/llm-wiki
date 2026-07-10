"""TASK 058 — the sync.yaml template registry + `init` composition.

Registry: builtin `templates/sync-profiles/<name>.yaml` (shipped, read-only) +
operator templates in `<vault>/.wiki/templates/*.yaml`. Metadata lives in a
STRICT comment header parsed with anchored regexes BEFORE any YAML load:

    # wiki-config template: <name> v<semver>
    # level: root|subfolder|any
    # var <name> (regex|string): <desc> [default: <val>]
    # purpose: <one line>

Vault templates run the same hardening as sync.yaml at discovery time (size
cap, symlink refusal, anchor ban via the render gate); a name collision with a
builtin is resolved builtin-wins (the vault copy is listed `shadowed` — a vault
file must not impersonate a shipped profile). Variables substitute via
`string.Template` with single-quote escaping; `regex`-kind values pass the
ReDoS load-gate; every rendered result runs the FULL hardened gate BEFORE any
write. The written file keeps the template's own header line — `wiki-config
validate` compares it against the registry for TEMPLATE_DRIFT.
"""

from __future__ import annotations

import re
import string
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.wiki_index.layout_config import is_pattern_redos_safe
from scripts.wiki_index.sync_config import (
    WIKI_SYNC_CONFIG_MAX_BYTES,
    SyncConfigError,
)

from ._edit import gate_text
from ._uimodel import _REPO_ROOT

BUILTIN_DIR = _REPO_ROOT / "templates" / "sync-profiles"
VAULT_TEMPLATE_DIR = ".wiki/templates"
SCHEMA_JSON = _REPO_ROOT / "config" / "sync-config.schema.json"
MODELINE_PREFIX = "# yaml-language-server: $schema="

_HEADER_RE = re.compile(r"^# wiki-config template: (?P<name>[a-z0-9][a-z0-9-]*) v(?P<ver>\d+\.\d+\.\d+)\s*$")
_LEVEL_RE = re.compile(r"^# level: (?P<level>root|subfolder|any)\s*$")
_VAR_RE = re.compile(
    r"^# var (?P<name>[A-Za-z_][A-Za-z0-9_]*)"
    r"(?: \((?P<kind>regex|string)\))?: "
    r"(?P<desc>.*?)(?: \[default: (?P<default>.*)\])?\s*$"
)
_PURPOSE_RE = re.compile(r"^# purpose: (?P<purpose>.+?)\s*$")

# The drift probe reads THIS line back out of a generated sync.yaml.
TEMPLATE_STAMP_RE = _HEADER_RE


@dataclass(frozen=True)
class TemplateVar:
    name: str
    kind: str  # string | regex
    description: str
    default: str | None


@dataclass(frozen=True)
class SyncTemplate:
    name: str
    version: str
    level: str  # root | subfolder | any
    purpose: str
    variables: tuple[TemplateVar, ...]
    body: str
    source: str  # builtin | vault
    valid: bool = True
    shadowed: bool = False
    error: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name, "version": self.version, "level": self.level,
            "source": self.source, "valid": self.valid, "shadowed": self.shadowed,
            "purpose": self.purpose,
            "required_vars": [
                {"name": v.name, "kind": v.kind, "default": v.default,
                 "description": v.description}
                for v in self.variables
            ],
            **({"error": self.error} if self.error else {}),
        }


class TemplateError(ValueError):
    """Registry/render failure with a stable code; `detail` is value-free."""

    def __init__(self, code: str, detail: str, **data: Any) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
        self.data = data


def _parse_template_text(text: str, source: str) -> SyncTemplate:
    header = level = purpose = None
    variables: list[TemplateVar] = []
    for line in text.splitlines():
        if not line.startswith("#"):
            break
        if header is None and (m := _HEADER_RE.match(line)):
            header = (m.group("name"), m.group("ver"))
            continue
        if level is None and (m := _LEVEL_RE.match(line)):
            level = m.group("level")
            continue
        if m := _VAR_RE.match(line):
            variables.append(TemplateVar(
                name=m.group("name"), kind=m.group("kind") or "string",
                description=m.group("desc"), default=m.group("default"),
            ))
            continue
        if purpose is None and (m := _PURPOSE_RE.match(line)):
            purpose = m.group("purpose")
    if header is None or level is None:
        raise TemplateError("TEMPLATE_HEADER_INVALID",
                            "missing '# wiki-config template:' or '# level:' header")
    return SyncTemplate(
        name=header[0], version=header[1], level=level, purpose=purpose or "",
        variables=tuple(variables), body=text, source=source,
    )


def _load_template_file(path: Path, source: str) -> SyncTemplate:
    if path.is_symlink():
        raise TemplateError("TEMPLATE_UNSAFE", "template is a symlink")
    if path.stat().st_size > WIKI_SYNC_CONFIG_MAX_BYTES:
        raise TemplateError("TEMPLATE_UNSAFE", "template exceeds the 256 KiB cap")
    tpl = _parse_template_text(path.read_text(encoding="utf-8"), source)
    # Discovery-time render check with defaults: an unusable template is listed
    # `valid: false` instead of exploding at init time.
    try:
        defaults = {v.name: v.default or "" for v in tpl.variables}
        gate_text(substitute_vars(tpl, defaults))
    except (SyncConfigError, TemplateError) as exc:
        return SyncTemplate(**{**tpl.__dict__, "valid": False,
                               "error": getattr(exc, "detail", "render failed")})
    return tpl


def discover_templates(vault_root: Path | None = None) -> dict[str, SyncTemplate]:
    """name → template; builtin wins a name collision (vault copy `shadowed`)."""
    registry: dict[str, SyncTemplate] = {}
    if BUILTIN_DIR.is_dir():
        for path in sorted(BUILTIN_DIR.glob("*.yaml")):
            try:
                tpl = _load_template_file(path, "builtin")
            except (TemplateError, OSError):
                continue  # a broken SHIPPED template is a repo bug; skip quietly
            registry[tpl.name] = tpl
    if vault_root is not None:
        vdir = vault_root / VAULT_TEMPLATE_DIR
        if vdir.is_dir():
            for path in sorted(vdir.glob("*.yaml")):
                try:
                    tpl = _load_template_file(path, "vault")
                except (TemplateError, OSError):
                    tpl = SyncTemplate(
                        name=path.stem, version="0.0.0", level="any", purpose="",
                        variables=(), body="", source="vault", valid=False,
                        error="header/hardening failure",
                    )
                if tpl.name in registry:
                    registry[f"{tpl.name} (vault)"] = SyncTemplate(
                        **{**tpl.__dict__, "shadowed": True})
                else:
                    registry[tpl.name] = tpl
    return registry


def _escape_single_quoted(value: str) -> str:
    """Template bodies put `${var}` INSIDE single-quoted YAML scalars; the only
    escape needed there is `'` → `''`."""
    return value.replace("'", "''")


def check_var_values(tpl: SyncTemplate, supplied: dict[str, str]) -> None:
    """Names + safety. Raises TemplateError (names only, values never echoed)."""
    known = {v.name for v in tpl.variables}
    unknown = sorted(set(supplied) - known)
    if unknown:
        raise TemplateError("UNKNOWN_VAR", "unknown --var name(s)", vars=unknown)
    missing = sorted(
        v.name for v in tpl.variables
        if v.default is None and v.name not in supplied
    )
    if missing:
        raise TemplateError("REQUIRED_VAR_MISSING", "missing required --var(s)",
                            vars=missing)
    for var in tpl.variables:
        if var.name not in supplied:
            continue
        value = supplied[var.name]
        if any(ord(ch) < 32 for ch in value):
            raise TemplateError("INVALID_TEMPLATE_VAR",
                                "control chars / newlines are not allowed",
                                vars=[var.name])
        if var.kind == "regex" and not is_pattern_redos_safe(value, operator=True):
            raise TemplateError("INVALID_TEMPLATE_VAR",
                                "regex var is uncompilable or exceeds the ReDoS "
                                "budget (value not echoed)", vars=[var.name])


def substitute_vars(tpl: SyncTemplate, supplied: dict[str, str]) -> str:
    values = {v.name: v.default or "" for v in tpl.variables}
    values.update(supplied)
    escaped = {k: _escape_single_quoted(v) for k, v in values.items()}
    try:
        return string.Template(tpl.body).substitute(escaped)
    except (KeyError, ValueError) as exc:
        raise TemplateError("TEMPLATE_RENDER_FAILED",
                            "placeholder substitution failed") from exc


def modeline() -> str:
    return f"{MODELINE_PREFIX}{SCHEMA_JSON.as_uri()}"


def render_for_init(tpl: SyncTemplate, supplied: dict[str, str]) -> str:
    """The final file text: editor modeline + rendered body (which keeps the
    template's own `# wiki-config template: <name> v<ver>` stamp — the
    TEMPLATE_DRIFT provenance; deliberately NO timestamp, so re-init is
    byte-identical). The result MUST still pass the caller's full gate."""
    check_var_values(tpl, supplied)
    body = substitute_vars(tpl, supplied)
    return f"{modeline()}\n{body}"


def top_level_blocks(text: str) -> dict[str, str]:
    """Top-level `key:` → its full text block (attached preceding comments +
    the key line + deeper-indented lines). Used by `init --merge` to append
    ONLY blocks the existing file lacks (existing file wins wholesale)."""
    lines = text.splitlines(keepends=True)
    blocks: dict[str, str] = {}
    pending_comments: list[str] = []
    current_key: str | None = None
    current: list[str] = []

    def flush() -> None:
        nonlocal current_key, current
        if current_key is not None:
            blocks[current_key] = "".join(current)
        current_key, current = None, []

    for line in lines:
        if line.startswith("#") or not line.strip():
            if current_key is not None and line.startswith(" "):
                current.append(line)
            else:
                flush()
                pending_comments.append(line)
            continue
        if not line.startswith(" ") and ":" in line:
            flush()
            current_key = line.split(":", 1)[0].strip().strip("'\"")
            current = pending_comments + [line]
            pending_comments = []
        elif current_key is not None:
            current.append(line)
        else:
            pending_comments = []
    flush()
    return blocks


def read_template_stamp(text: str) -> tuple[str, str] | None:
    """The `(name, version)` stamp of a generated sync.yaml, if present."""
    for line in text.splitlines():
        if m := TEMPLATE_STAMP_RE.match(line):
            return m.group("name"), m.group("ver")
        if not line.startswith("#") and line.strip():
            break
    return None
