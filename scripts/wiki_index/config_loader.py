"""Configuration loader — `load_config(cwd)` end-to-end.

Algorithm per R-01:
  1. Walk up from `cwd` looking for `WIKI_SCHEMA.md`. That's the vault root.
  2. Read `WIKI_SCHEMA.md` YAML frontmatter → base root config
     (provides `vault_id` per ADR-002 §D1.1, plus `schema_version`,
     `language`, `layout`).
  3. If `<vault_root>/CLAUDE.md` exists with a `wiki:` YAML block → overlay it
     on top of the base (operational fields: `paths`, `lint`, `transcript`).
  4. Walk up from `cwd` (stopping at vault root) looking for `.wiki.yaml`.
     If found → overlay as project override (per-course config).
  5. Validate the merged result against `config/wiki-config.schema.yaml`
     `#/$defs/WikiRootConfig`. Fail-fast on violation.
  6. Return the merged dict.

R-01.2 deep-merge semantic: nested dicts merged recursively; scalars and
lists are REPLACED (not concatenated) by the override layer.
R-01.3 fail-fast: ConfigValidationError exposes JSON pointer to offending field.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from scripts.wiki_index.layout import SCHEMA_FILE

# Repository-relative path to the schema (project root = parent of `scripts/`)
_SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent.parent / "config" / "wiki-config.schema.yaml"
)
_WIKI_SCHEMA_MARKER = SCHEMA_FILE
_PROJECT_OVERRIDE_MARKER = ".wiki.yaml"


class VaultRootNotFoundError(RuntimeError):
    """Raised when `find_vault_root` walks to filesystem root without finding
    `WIKI_SCHEMA.md`. Caller should surface as `MISSING_WIKI_SCHEMA` error
    (per ADR-002 §D1.1 fail-fast)."""


class ConfigValidationError(ValueError):
    """Raised when the merged config violates the JSON Schema. Message
    includes JSON pointer to the offending field per R-01.3."""


def find_vault_root(cwd: Path) -> Path:
    """Walk up from `cwd` until finding `WIKI_SCHEMA.md`. Returns the
    containing directory. Raises `VaultRootNotFoundError` if not found
    before the filesystem root."""
    current = cwd.resolve()
    while True:
        if (current / _WIKI_SCHEMA_MARKER).is_file():
            return current
        if current.parent == current:  # reached filesystem root
            raise VaultRootNotFoundError(
                f"No {_WIKI_SCHEMA_MARKER} found walking up from {cwd}"
            )
        current = current.parent


def find_project_root(cwd: Path, vault_root: Path) -> Path | None:
    """Walk up from `cwd` (stopping at `vault_root`) looking for `.wiki.yaml`.
    Returns the containing directory of the nearest override, or None if no
    `.wiki.yaml` is found between cwd and vault_root."""
    current = cwd.resolve()
    vault_root_resolved = vault_root.resolve()
    while True:
        if (current / _PROJECT_OVERRIDE_MARKER).is_file():
            return current
        if current == vault_root_resolved:
            return None
        if current.parent == current:
            return None
        current = current.parent


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split a markdown file into (frontmatter_dict, body). Returns ({}, text)
    if no frontmatter block is present."""
    if not text.startswith("---\n"):
        return {}, text
    parts = text.split("---\n", 2)
    if len(parts) < 3:
        return {}, text
    fm_text, body = parts[1], parts[2]
    fm = yaml.safe_load(fm_text) or {}
    if not isinstance(fm, dict):
        return {}, text
    return fm, body


_CLAUDE_WIKI_BLOCK = re.compile(
    r"^```yaml\s*\n(?P<yaml>.*?)\n```", re.DOTALL | re.MULTILINE
)


def resolve_index_db_path(
    vault_root: Path, *, expected_vault_id: str | None = None
) -> Path | None:
    """TASK 022 — resolve a vault's optional `index_db` (raw `WIKI_SCHEMA.md`
    frontmatter) to a DB `Path`, or `None` when unset.

    Reads `index_db` from the **RAW** frontmatter via `_split_frontmatter` — NOT
    `load_root_config`, so the `CLAUDE.md::wiki:` overlay is deliberately bypassed
    (single-redirect-surface decision, ARCHITECTURE Q-022-1). Two forms:

      * **relative** (default, e.g. `.wiki/index.db`) — resolved under `vault_root`;
        the leaf must NOT be a symlink and the **full** candidate must `resolve()`
        inside `vault_root` (vdd-multi HIGH-S1 — a parent-only check let a symlinked
        leaf escape into an arbitrary-write primitive).
      * **absolute / `~`** — gated behind `WIKI_ALLOW_ABSOLUTE_INDEX_DB` (vdd-multi
        HIGH-S2): `WIKI_SCHEMA.md` travels WITH the vault (clone/sync/handover), so it
        is NOT the same trust source as a `--db-path` flag typed this session; an
        ungated absolute path is an arbitrary-path write (`make_repo` mkdir+writes the
        schema). The iCloud guard still applies downstream in `factory.make_repo`.

    `expected_vault_id` (vdd-multi HIGH-L1): when the caller addresses a specific vault,
    the index_db at `vault_root` only applies if the root actually BELONGS to that vault —
    else a CWD walk-up (or a mismatched `--vault-root`) would silently open a DIFFERENT
    vault's DB. A mismatch → `None` (fall back to global). The global sentinel passes
    `None` here (the in-vault DB is wanted for an `--all` within the island).

    Raises `ConfigValidationError` (never echoing the value, CWE-209) on a NUL byte, a
    relative escape/symlink, or an ungated absolute. Missing key / non-string → `None`.
    """
    schema_path = vault_root / _WIKI_SCHEMA_MARKER
    if not schema_path.is_file():
        return None
    base, _ = _split_frontmatter(schema_path.read_text())  # RAW — bypass the overlay
    if (expected_vault_id is not None
            and base.get("vault_id") not in (None, expected_vault_id)):
        return None  # vault_root belongs to a DIFFERENT vault → not this command's DB
    val = base.get("index_db")
    if not isinstance(val, str) or not val.strip():
        return None
    # TASK 025 / R-1: the path-safety validation is shared with wiki-init's pre-write
    # guard. resolve_index_db_path owns the read + `expected_vault_id` short-circuit +
    # strip (above); the pure validator owns NUL / absolute-gate / symlink / escape.
    return validate_index_db_value(val.strip(), vault_root)


def validate_index_db_value(val: str, vault_root: Path) -> Path:
    """TASK 025 / R-1 — validate an already-``.strip()``-ed ``index_db`` VALUE (this does
    NOT read any file) and return the resolved DB ``Path`` it denotes. Shared by
    ``resolve_index_db_path`` (post-read) and ``wiki-init`` (PRE-WRITE guard, so a
    rejected value never half-mutates the Class-A ``WIKI_SCHEMA.md``). Raises
    ``ConfigValidationError`` (never echoing the value — CWE-209) on a NUL byte, an
    ungated absolute path, or a relative escape/symlink. Returns the value-dependent
    ``Path`` (``expanded`` for absolute, ``vault_root / expanded`` for relative) so the
    two callers cannot drift on which branch was taken.

      * absolute / ``~`` → gated behind ``WIKI_ALLOW_ABSOLUTE_INDEX_DB`` (vdd-multi
        HIGH-S2): ``WIKI_SCHEMA.md`` travels WITH the vault, so it is not the same trust
        source as a ``--db-path`` typed this session.
      * relative → leaf must NOT be a symlink AND the FULL candidate must ``resolve()``
        inside ``vault_root`` (vdd-multi HIGH-S1 — a parent-only check let a symlinked
        leaf escape into an arbitrary-write primitive).
    """
    if "\x00" in val:
        raise ConfigValidationError("index_db contains a NUL byte")
    expanded = Path(os.path.expanduser(val))  # `~` only; NO `$VAR` (env-in-config smell)
    if expanded.is_absolute():
        if os.environ.get("WIKI_ALLOW_ABSOLUTE_INDEX_DB", "").strip().lower() \
                not in {"1", "true", "yes", "on"}:
            raise ConfigValidationError(
                "absolute index_db requires WIKI_ALLOW_ABSOLUTE_INDEX_DB=1")
        return expanded
    # Relative → reject a symlinked leaf, then resolve the FULL candidate (catches a
    # symlinked leaf/middle/parent + embedded `..`) and require it inside the vault.
    cand = vault_root / expanded
    if cand.is_symlink():
        raise ConfigValidationError("index_db is a symlink")
    try:
        full_resolved = cand.resolve(strict=False)
        root_resolved = vault_root.resolve()
    except OSError:
        raise ConfigValidationError("index_db could not be resolved")
    if not full_resolved.is_relative_to(root_resolved):
        raise ConfigValidationError("index_db escapes the vault root")
    return cand


def load_root_config(vault_root: Path) -> dict[str, Any]:
    """Read vault root config from `WIKI_SCHEMA.md` frontmatter (base) and
    overlay an optional `CLAUDE.md::wiki:` YAML block if present.

    The WIKI_SCHEMA.md frontmatter is the source-of-truth for `vault_id`
    (ADR-002 §D1.1). The CLAUDE.md `wiki:` block carries operational fields
    (paths, lint, transcript) that the operator may override per vault.
    """
    schema_path = vault_root / _WIKI_SCHEMA_MARKER
    if not schema_path.is_file():
        raise VaultRootNotFoundError(f"{schema_path} does not exist")

    base, _ = _split_frontmatter(schema_path.read_text())
    if not isinstance(base, dict):
        raise ConfigValidationError(
            f"{schema_path}: frontmatter must be a YAML mapping"
        )

    # Optional CLAUDE.md::wiki: overlay
    claude_md = vault_root / "CLAUDE.md"
    if claude_md.is_file():
        text = claude_md.read_text()
        # Look for a `wiki:` YAML block. Two supported forms:
        #   (a) frontmatter with top-level `wiki:` key
        #   (b) inline fenced ```yaml ... ``` block containing `wiki:` mapping
        fm, _ = _split_frontmatter(text)
        if isinstance(fm.get("wiki"), dict):
            base = deep_merge(base, fm["wiki"])
        else:
            for m in _CLAUDE_WIKI_BLOCK.finditer(text):
                try:
                    block = yaml.safe_load(m.group("yaml"))
                except yaml.YAMLError:
                    continue
                if isinstance(block, dict) and isinstance(block.get("wiki"), dict):
                    base = deep_merge(base, block["wiki"])
                    break  # first matching block wins

    return base


def load_project_override(project_root: Path) -> dict[str, Any]:
    """Read `.wiki.yaml` from project_root and return its parsed dict. Empty
    file → empty dict."""
    override_path = project_root / _PROJECT_OVERRIDE_MARKER
    data = yaml.safe_load(override_path.read_text()) or {}
    if not isinstance(data, dict):
        raise ConfigValidationError(
            f"{override_path}: must be a YAML mapping at the top level"
        )
    return data


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursive merge with override semantics:
      - dicts: merged recursively
      - scalars and lists: override replaces base entirely
    Returns a new dict (no in-place mutation)."""
    result: dict[str, Any] = dict(base)
    for key, override_val in override.items():
        base_val = result.get(key)
        if isinstance(base_val, dict) and isinstance(override_val, dict):
            result[key] = deep_merge(base_val, override_val)
        else:
            result[key] = override_val
    return result


def _load_schema() -> dict[str, Any]:
    """Load the wiki-config schema document from `config/`."""
    raw = yaml.safe_load(_SCHEMA_PATH.read_text())
    if not isinstance(raw, dict):
        raise RuntimeError(f"{_SCHEMA_PATH}: schema must be a YAML mapping")
    return raw


def _validate_against_root_scope(merged: dict[str, Any]) -> None:
    """Validate `merged` against #/$defs/WikiRootConfig. Raises
    ConfigValidationError with a JSON pointer to the offending field on failure."""
    schema = _load_schema()
    root_scope = {**schema, "$ref": "#/$defs/WikiRootConfig"}
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(root_scope)
    errors = sorted(validator.iter_errors(merged), key=lambda e: list(e.absolute_path))
    if errors:
        msg_parts = []
        for err in errors:
            pointer = "/" + "/".join(str(p) for p in err.absolute_path) if err.absolute_path else "/"
            msg_parts.append(f"  at {pointer}: {err.message}")
        raise ConfigValidationError(
            "config validation failed:\n" + "\n".join(msg_parts)
        )


def load_config(cwd: Path) -> dict[str, Any]:
    """Walk up from `cwd`, parse WIKI_SCHEMA.md + optional CLAUDE.md::wiki: +
    optional `.wiki.yaml` project override; deep-merge; validate; return."""
    vault_root = find_vault_root(cwd)
    base = load_root_config(vault_root)
    base.setdefault("paths", {})  # paths defaults documented in schema; allow empty
    project_root = find_project_root(cwd, vault_root)
    if project_root is not None:
        override = load_project_override(project_root)
        base = deep_merge(base, override)
    _validate_against_root_scope(base)
    return base
