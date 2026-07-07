"""Policy-before-model retrieval scoping (TASK 049 / ADR-009 / ROADMAP R-16).

Pure module — no DB, no LLM (Decision-17). Resolves a vault's optional
``policy:`` block (``WIKI_SCHEMA.md`` frontmatter, read through the existing
``load_root_config`` overlay path) plus the ``--audience`` CLI flag into a
:class:`PolicyProfile`, and derives per-page effective levels.

Default OFF is load-bearing (NFR-1 byte-identity): no ``--audience`` flag AND
no declared ``policy.default_audience`` ⇒ :func:`resolve_policy` returns
``None`` and every caller changes nothing — no SQL clause, no hash fold, no
envelope field.

Activation precedence (Q-049-1): flag > declared ``default_audience`` (a
declared audience ALWAYS activates, even at the highest level — no max-level
special case) > OFF. A flag with no resolvable ``policy:`` block uses the
built-in ladder so ``--audience`` works out of the box.

CWE-209/117: every :class:`PolicyError` message names the offending FIELD
only — never the value.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

BUILTIN_LEVELS: tuple[str, ...] = ("public", "internal", "restricted")
_LEVEL_RE = re.compile(r"[a-z][a-z0-9_-]{0,15}")
_MAX_LEVELS = 16
_POLICY_KEYS = {"levels", "default_level", "default_audience"}


class PolicyError(ValueError):
    """Invalid policy config or audience value.

    ``field`` distinguishes the CLI envelope: ``"audience"`` → the operator's
    flag is wrong (``INVALID_AUDIENCE``); anything else → the vault's
    ``policy:`` block is malformed (``INVALID_POLICY``).
    """

    def __init__(self, message: str, *, field: str = "policy") -> None:
        super().__init__(message)
        self.field = field


@dataclass(frozen=True)
class PolicyProfile:
    """A resolved, ACTIVE scope: the ladder + the caller's audience level."""

    levels: tuple[str, ...]
    default_level: str
    audience: str


def _validate_level_name(name: object, field: str) -> str:
    if not isinstance(name, str) or not _LEVEL_RE.fullmatch(name):
        raise PolicyError(
            f"{field} must be a level name matching [a-z][a-z0-9_-]{{0,15}}",
            field=field,
        )
    return name


def parse_policy_block(raw: object) -> tuple[tuple[str, ...], str, str | None]:
    """Strict-validate a vault ``policy:`` mapping.

    Returns ``(levels, default_level, default_audience_or_None)``. A malformed
    block RAISES (fail loud — a vault that opted into policy must never
    silently degrade to OFF); messages never echo values (CWE-209).
    """
    if not isinstance(raw, dict):
        raise PolicyError("policy block must be a YAML mapping")
    if set(raw) - _POLICY_KEYS:
        raise PolicyError(
            "policy block carries an unknown key (allowed: levels, "
            "default_level, default_audience)")
    levels_raw = raw.get("levels")
    if (not isinstance(levels_raw, list) or not levels_raw
            or len(levels_raw) > _MAX_LEVELS):
        raise PolicyError(
            f"policy.levels must be a non-empty list of at most {_MAX_LEVELS} "
            "level names, ordered low to high")
    levels = tuple(
        _validate_level_name(x, "policy.levels entry") for x in levels_raw)
    if len(set(levels)) != len(levels):
        raise PolicyError("policy.levels contains a duplicate level name")
    default_level = _validate_level_name(
        raw.get("default_level", levels[0]), "policy.default_level")
    if default_level not in levels:
        raise PolicyError("policy.default_level is not one of policy.levels")
    raw_audience = raw.get("default_audience")
    default_audience: str | None = None
    if raw_audience is not None:
        default_audience = _validate_level_name(
            raw_audience, "policy.default_audience")
        if default_audience not in levels:
            raise PolicyError(
                "policy.default_audience is not one of policy.levels")
    return levels, default_level, default_audience


_POLICY_KEY_RE = re.compile(r"^policy\s*:", re.MULTILINE)


def load_vault_policy(
    vault_root: Path,
) -> tuple[tuple[str, ...], str, str | None] | None:
    """Read + validate the vault's ``policy:`` block, or ``None`` when the
    vault declares none (absent block, or no ``WIKI_SCHEMA.md`` — the caller
    may be outside any vault). A PRESENT-but-malformed block raises
    :class:`PolicyError` (never silent OFF) — and that guarantee covers
    CONFIG-LEVEL failures too (vdd-multi SEC-3 / logic-MED): when
    ``load_root_config`` itself errors (broken YAML/encoding/validation), we
    raw-scan ``WIKI_SCHEMA.md`` for a declared ``policy:`` key — visible
    declaration + unreadable config ⇒ fail LOUD, not silent OFF."""
    from scripts.wiki_index.config_loader import (
        ConfigValidationError,
        VaultRootNotFoundError,
        load_root_config,
    )

    try:
        cfg = load_root_config(vault_root)
    except VaultRootNotFoundError:
        return None  # not a vault — legitimately no policy
    except (ConfigValidationError, OSError, yaml.YAMLError,
            UnicodeDecodeError):
        # Config errored. If the raw schema file visibly declares a policy
        # block, the operator opted in — degrade LOUDLY (the scoped CLIs map
        # this to INVALID_POLICY; lint surfaces `invalid-policy`). Otherwise
        # the vault declares none → OFF, matching pre-049 behavior for
        # vaults with unrelated config damage.
        try:
            raw_text = (vault_root / "WIKI_SCHEMA.md").read_text(
                errors="replace")
        except OSError:
            return None
        if _POLICY_KEY_RE.search(raw_text):
            raise PolicyError(
                "vault config is unreadable while a policy block is "
                "declared; fix WIKI_SCHEMA.md / CLAUDE.md::wiki:")
        return None
    raw = cfg.get("policy")
    if raw is None:
        return None
    return parse_policy_block(raw)


def resolve_policy(
    vault_root: Path | None, audience_flag: str | None,
) -> PolicyProfile | None:
    """Resolve the ACTIVE profile per Q-049-1 precedence, or ``None`` = OFF.

    - ``--audience`` flag → active at that level (vault ladder when a
      ``policy:`` block resolves, else :data:`BUILTIN_LEVELS`).
    - else declared ``policy.default_audience`` → active.
    - else OFF.
    """
    block = load_vault_policy(vault_root) if vault_root is not None else None
    if audience_flag is not None:
        audience = _validate_level_name(audience_flag, "audience")
        if block is not None:
            levels, default_level = block[0], block[1]
        else:
            levels, default_level = BUILTIN_LEVELS, BUILTIN_LEVELS[0]
        if audience not in levels:
            raise PolicyError(
                "audience is not one of the vault's policy levels",
                field="audience")
        return PolicyProfile(
            levels=levels, default_level=default_level, audience=audience)
    if block is not None and block[2] is not None:
        return PolicyProfile(
            levels=block[0], default_level=block[1], audience=block[2])
    return None


def allowed_levels(profile: PolicyProfile) -> list[str]:
    """Levels visible to the profile: the ladder up to AND including the
    audience level (list order = declaration order)."""
    idx = profile.levels.index(profile.audience)
    return list(profile.levels[: idx + 1])


_NON_SCALAR_SENTINEL = "\x00non-scalar"
"""Returned for a non-string authored ``classification`` — can never appear in
a ladder (levels are ``[a-z]…``), so it FAILS CLOSED on the membership test,
matching the SQL predicate's behaviour (``CAST(3 AS TEXT) = '3'`` ∉ ladder).
Without this, a ``classification: 3`` page would be excluded by the SQL path
but leak through the Python ``get_page`` gates (edges / examined cites)."""

FOREIGN_UNCLASSIFIED_SENTINEL = "\x00foreign-unclassified"
"""Pass as ``default_level`` to :func:`effective_level` for a page from a
vault OTHER than the profile's home vault (vdd-multi SEC-2): the home vault's
``default_level`` must never be granted to another vault's UNLABELED pages —
an unclassified foreign page resolves to this non-ladder value and fails
closed, while an explicitly in-ladder-labeled foreign page still passes the
membership test. Mirrors the SQL ``CASE WHEN p.vault_id = ? THEN ? END``
scoped-default shape."""


def effective_level(frontmatter: dict[str, Any] | None, default_level: str) -> str:
    """A page's effective classification, ALIGNED with the SQL predicate
    ``COALESCE(CAST(json_extract($.classification) AS TEXT), default)``:

    - absent key / YAML ``null`` → ``default_level`` (null ≡ absent,
      arch-review LOW-4 — JSON null extracts to SQL NULL → COALESCE default);
    - a string → itself verbatim (an empty or out-of-ladder string then fails
      the membership test — fail closed, same as SQL);
    - any non-string scalar/container → a non-ladder sentinel (fails closed;
      SQL CASTs it to a text that is likewise never a declared level).

    The returned value is NOT checked against a ladder — callers do a
    membership test against ``allowed_levels``."""
    if not frontmatter:
        return default_level
    val = frontmatter.get("classification")
    if val is None:
        return default_level
    if isinstance(val, str):
        return val
    return _NON_SCALAR_SENTINEL
