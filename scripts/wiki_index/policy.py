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


# -----------------------------------------------------------------------------
# TASK 050 (R-5/R-6) — derived trust tier (external < internal < verified)
# -----------------------------------------------------------------------------

TRUST_TIERS: tuple[str, ...] = ("external", "internal", "verified")
"""Ordered low→high. MIN-rule (Q-050-1): origin taints — a page that is both
external-origin AND verified stays ``external``."""

_HTTP_PREFIXES = ("http://", "https://")

EXTERNAL_PROVENANCE_KEYS: tuple[str, ...] = (
    "source", "Source", "SOURCE",
    "sources", "Sources", "SOURCES",
    "url", "Url", "URL")
"""TASK 061 / R-061-3 (+ the 061 VDD fix-loop, H2) — the ONE source of truth for
the frontmatter keys whose ``http(s)://`` value marks a page as EXTERNAL origin.

RENDERED INTO BOTH HALVES of the Q-050-3 alignment contract: the Python
:func:`_is_external` below AND the ``_EXTERNAL_ORIGIN_SQL`` literal in
``sqlite_repository/_search.py``. The parametrized alignment test in
``tests/test_trust_tier.py`` is driven from this same tuple *and from the
declared VALUE SHAPES below*, so the two halves and their test move together or
not at all — neither a new key nor a new shape can drift them apart.

**``sources`` (PLURAL) is here because it is the framework's OWN canonical
provenance key** — ``IndexRepository.all_cited_sources`` harvests ``sources[]``,
and ``wiki-sync``'s D2a provenance detector defaults to
``fields: (source, sources)``. The trust predicate had simply forgotten it: **81
LIVE pages carry ``sources:``**, and every one of them derived ``internal``.

**VALUE SHAPES — the predicate is shape-complete, and the shapes are ENUMERATED
(not assumed).** A key's value marks the page external when it is:

1. a TEXT scalar with an ``http(s)://`` prefix — ``source: https://x/a``;
2. a LIST containing an http(s) TEXT scalar — ``sources: ["https://a", …]``
   (**1 live page**: a partnership note whose provenance is two external URLs);
3. a LIST containing an OBJECT with an http(s) TEXT scalar under one of *these
   same keys* — ``sources: [{id, url: "https://…", file}]`` (**16 live pages**:
   the TASK 023 ``{id, url, file}`` element that
   ``generate-detailed-meeting-summary`` emits, mirrored by ``all_cited_sources``).

Shapes 2 and 3 were the H2 fail-open: the pre-fix predicate required
``isinstance(val, str)`` on BOTH halves, so **17 live pages whose provenance is
an external URL derived ``internal`` and sailed through ``--min-trust
internal``** — the filter whose entire purpose is the H-6 contract. The two
halves *agreed* (they were "aligned"), and agreement is not the security
property: **fail-CLOSED is.** ``docs/architectures/security.md`` had even listed
"list-valued ``source:`` — accepted, the derivation reads scalars" as an accepted
residual; it was not acceptable, and it is now closed.

**BOUNDED, and the boundary is STATED** (depth ≤ 3 containers, no recursion — a
``json_tree`` walk would be unbounded on the hot search path). NOT external, on
BOTH halves, and pinned by tests so the limit stays visible rather than merely
true:

- a top-level OBJECT-valued key — ``source: {url: "https://…"}`` (**0 live pages**;
  no tool emits it);
- an http(s) URL nested deeper than a list-of-objects — ``sources: [[…]]``,
  ``sources: [{meta: {url: …}}]`` (**0 live pages**);
- an object member under a NON-provenance key — ``sources: [{href: "https://…"}]``
  (the inner key set IS this constant, so ``href``/``link`` do not count).

NEVER re-enumerate these keys anywhere else: import the constant. (The key list
had already been copy-pasted across 6+ surfaces, and that duplication is exactly
what let the halves and the prose drift. ``tests/test_trust_key_single_source``
is the executable gate proving ``scripts/`` enumerates them here and nowhere
else.)

Every entry MUST be a bare identifier (``[A-Za-z_][A-Za-z0-9_]*``): it is
interpolated into SQL *text* as a quoted literal (an ``IN ('source', …)`` member
of ``_EXTERNAL_ORIGIN_SQL``; before the H2 rewrite, a ``$.<key>`` JSON path), so
a key carrying a quote would be an injection through our own source. Enforced at
import, below — a ``raise``, not an ``assert``.

**Why CASE VARIANTS are ENUMERATED and not case-FOLDED** (TASK 061-06, Q-061-2).
Not a performance choice — an ALIGNMENT one: both halves must render from ONE
list. *Q-061-2's stated rationale has been partly OVERTAKEN by the H2 rewrite,
and says so here rather than quietly rotting:* it argued that a fold "needs
``json_each`` + ``lower(key)`` **in SQL only**", i.e. that folding would make the
halves structurally asymmetric. The SQL half is a ``json_each`` member walk now
anyway (it had to be, to see inside a list), so a true fold — ``lower(je.key) IN
(…)`` in SQL, ``k.lower() in {…}`` in Python — would today be *symmetric*, and
would additionally close the typo class. That is a **deliberate follow-up, not a
silent widening**: it flips the pinned ``uRL:`` case and reverses a RESOLVED open
question, so it belongs in its own change with its own review. Enumeration holds
here. (LIKE's ASCII-ci fold covers the VALUE, so ``HTTP://`` always matched —
only the KEY was ever case-sensitive.)

**What this closes, honestly.** Two fail-OPEN leaks, both verified against the
LIVE DB (read-only census), both invisible to reasoning and caught only by a
grep:

- 19 pages carried ``Source:`` (a case variant) — closed by TASK 061-06.
- **17 pages carry an external URL under a list-valued ``sources:``** — closed
  here (shapes 2/3 above). LIVE external count: **720 → 737** of 3267 pages.

It does **not** close the CLASS. A typo-shaped key (``uRL:``, ``Source_URL:``)
still fails open — no tool emits those. ``SOURCE``/``Url``/``Sources``/``SOURCES``
have **0** live pages: cheap defense-in-depth, and deliberately NOT a P-5
violation (P-5 is about speculative *indexes*; these are strings in a tuple, and
the SQL cost is now FLAT in the key count — see ``_EXTERNAL_ORIGIN_SQL``).

**Known residual — Q-061-4** (still OPEN — and its own census was wrong).
Vault-specific provenance keys are *different keys*, not case variants and not
value shapes, and still derive ``internal``. **The live population is 9 PAGES,
not the 18 that the TASK 061 spec, this docstring and security.md all claimed**:
each of the 9 carries ``youtube:`` *and* ``teachable:``, and "18" was two
KEY-occurrence counts (9 + 9) summed as though they were disjoint PAGE sets —
the same count-the-wrong-noun bug TASK 061 exists to kill, one layer down. Of the
9, **1** already derives ``external`` via another key, so **8 pages actually fail
open**. That set is DISJOINT from the 17 above (checked, not assumed: none of the
9 carries a ``sources:`` array), so the H2 fix neither closes nor shrinks it.
Deferred by **MECHANISM** (it needs a per-vault ``external_keys:`` config surface,
which does not belong in a fix task) — **not** by defect. Test-PINNED in
``tests/test_trust_tier.py::test_vault_specific_provenance_key_still_internal_q0614``:
when Q-061-4 lands, that assertion FLIPS to ``external``."""

_PROVENANCE_KEY_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

if not all(_PROVENANCE_KEY_RE.fullmatch(k) for k in EXTERNAL_PROVENANCE_KEYS):
    # A `raise`, not an `assert`: `python -O` strips asserts, and a guard on a
    # SQL-text interpolation must not evaporate under an optimisation flag.
    raise ValueError(
        "EXTERNAL_PROVENANCE_KEYS entries must be bare identifiers — they are "
        "interpolated into a SQL '$.<key>' JSON path")


def _is_http_scalar(val: object) -> bool:
    """A TEXT scalar carrying an EXACT ``http://``/``https://`` prefix.

    Never bare ``http`` (``httpx://`` must not match). ``.lower()`` mirrors
    SQLite ``LIKE``'s default ASCII-ci fold, so ``HTTP://`` matches on both
    halves. The SQL mirror is ``je.type = 'text' AND je.value LIKE 'http(s)://%'``
    — the ``type`` guard is what makes ``isinstance(val, str)`` the right Python
    twin (a JSON number/bool/null is not a text scalar on either side)."""
    return isinstance(val, str) and val.lower().startswith(_HTTP_PREFIXES)


def _member_is_external(member: object) -> bool:
    """One MEMBER of a list-valued provenance key (shapes 2 and 3 of
    :data:`EXTERNAL_PROVENANCE_KEYS`): an http(s) scalar, or an OBJECT carrying
    one under a provenance key — the TASK 023 ``{id, url, file}`` element that
    ``generate-detailed-meeting-summary`` emits and ``all_cited_sources`` reads.

    The inner key set IS the same constant (never a second list — that is how
    the halves drifted in the first place). Deliberately does NOT recurse: a
    member that is itself a list/nested object is NOT external. That bound is
    what keeps the SQL mirror a fixed 3-level walk instead of a ``json_tree``
    recursion on the hot search path — see the boundary stated on the constant."""
    if _is_http_scalar(member):
        return True
    if isinstance(member, dict):
        return any(_is_http_scalar(member.get(k))
                   for k in EXTERNAL_PROVENANCE_KEYS)
    return False


def _value_is_external(val: object) -> bool:
    """The VALUE half of the predicate — shape-complete over the three shapes
    declared on :data:`EXTERNAL_PROVENANCE_KEYS` (scalar · list-of-scalars ·
    list-of-objects), and no others.

    Structurally mirrors the SQL ``EXISTS(json_each …)`` walk branch-for-branch:
    ``je.type='text'`` ↔ :func:`_is_http_scalar`; ``je.type='array' AND
    EXISTS(json_each(je.value))`` ↔ the ``isinstance(val, list)`` any()."""
    if _is_http_scalar(val):
        return True
    if isinstance(val, list):
        return any(_member_is_external(m) for m in val)
    return False


def _is_external(frontmatter: dict[str, Any] | None, file_path: str) -> bool:
    """External-origin predicate, ALIGNED with the SQL half (Q-050-3).

    A page is external when EITHER:

    - a key from :data:`EXTERNAL_PROVENANCE_KEYS` (the single source of truth —
      do not re-list them here) carries an http(s) URL in one of the VALUE
      SHAPES declared there (:func:`_value_is_external`); OR
    - the page file lives under a ``_raw/`` segment — ASCII-case-insensitive
      (``_RAW/``) to match SQLite ``LIKE``'s default fold. (A backstop only: no
      built-in layout indexes ``_raw/``, so 0 live pages are external by path.)

    Iterating the CONSTANT (not ``frontmatter.items()``) is the deliberate twin
    of SQL's ``je.key IN (…)`` case-SENSITIVE membership test — see the
    enumerate-vs-fold note on the constant."""
    if frontmatter:
        for key in EXTERNAL_PROVENANCE_KEYS:
            if _value_is_external(frontmatter.get(key)):
                return True
    fp = file_path.lower()
    return fp.startswith("_raw/") or "/_raw/" in fp


def trust_tier(
    frontmatter: dict[str, Any] | None, file_path: str, verified: bool,
) -> str:
    """A page's derived trust tier. ``verified`` = the caller resolved an
    inbound ``verifies`` ref for this page (batched —
    ``IndexRepository.find_verified_slugs``)."""
    if _is_external(frontmatter, file_path):
        return "external"          # MIN-rule: origin taints (Q-050-1)
    return "verified" if verified else "internal"
