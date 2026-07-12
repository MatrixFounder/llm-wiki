"""TASK 061 / R-061-3 (TC-04-3) — "grep, don't believe", made executable.

The external-provenance key list drifted (a `Source:`-keyed page derived
`internal` while a `source:`-keyed one derived `external`) precisely BECAUSE the
list was copy-pasted across 6+ surfaces — two of them executable
(`policy._is_external` and the `_EXTERNAL_ORIGIN_SQL` literal), the rest prose.
`policy.EXTERNAL_PROVENANCE_KEYS` is now the single source of truth, and both
halves are RENDERED from it.

This module is the gate that KEEPS it single: it re-runs the census on every
CI run so a future copy-paste is a red test, not a silent fail-open. Reasoning
never caught this class of bug in TASK 061 — a grep caught it every time.
"""

from __future__ import annotations

import re
from pathlib import Path

from scripts.wiki_index.policy import EXTERNAL_PROVENANCE_KEYS

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
_OWNER = _SCRIPTS / "wiki_index" / "policy.py"

# The shape of a RE-ENUMERATION in code: two provenance-key string literals
# adjacent, separated only by a comma — `("source", "URL", ...)`, `["url",
# "Url"]`. A dict (`{"source": x, "url": y}`) does NOT match: the colon+value
# breaks the adjacency, so a legitimate per-key lookup is never flagged.
_TUPLE_ENUM_RE = re.compile(
    r"""(['"])(?:source|url)\1\s*,\s*(['"])(?:source|url)\2""", re.IGNORECASE)

# The shape of a re-enumeration in PROSE (a docstring/comment re-listing the
# SQL JSON paths, which is how `repository.py` and `policy.py` themselves drifted
# out of sync with the code beneath them): two `$.<key>` paths in a short span.
# The SQL builder's `'$.{k}'` TEMPLATE is not a key and does not match.
_PATH_ENUM_RE = re.compile(
    r"""\$\.(?:source|url)\b.{0,60}?\$\.(?:source|url)\b""",
    re.IGNORECASE | re.DOTALL)


def _py_files() -> list[Path]:
    return sorted(
        p for p in _SCRIPTS.rglob("*.py") if "__pycache__" not in p.parts)


def test_the_gate_is_not_vacuous() -> None:
    """POSITIVE CONTROL — the disease TASK 061 exists to cure is a check that
    examined NOTHING and reported green. So prove, before trusting any
    all-clear below, that (a) the walk actually finds the source tree and
    (b) each regex genuinely DETECTS the shape it claims to police — by firing
    on the one file that legitimately carries the enumeration.

    Without (a) a bad glob silently passes forever; without (b) a typo in the
    pattern silently passes forever."""
    files = _py_files()
    assert len(files) > 50, f"scripts/ walk found only {len(files)} files"
    assert _OWNER in files

    owner_src = _OWNER.read_text(encoding="utf-8")
    assert _TUPLE_ENUM_RE.search(owner_src), (
        "the tuple-enumeration regex no longer matches the ONE legitimate "
        "enumeration in policy.py — the gate below would be vacuous")
    # And the prose regex must be able to fire at all (self-test on a literal
    # of the exact shape the two docstrings used to carry).
    assert _PATH_ENUM_RE.search("``$.source``/``$.URL``/``$.url``")


def test_provenance_keys_are_enumerated_in_exactly_one_file() -> None:
    """TC-04-3 — no file in `scripts/` other than `policy.py` may enumerate the
    external-provenance keys, in code OR in prose. Both halves of the Q-050-3
    contract (`policy._is_external`, `_search._EXTERNAL_ORIGIN_SQL`) and every
    docstring must REFERENCE `EXTERNAL_PROVENANCE_KEYS`, never re-list it."""
    offenders: list[str] = []
    for path in _py_files():
        if path == _OWNER:
            continue
        src = path.read_text(encoding="utf-8")
        rel = path.relative_to(_SCRIPTS.parent)
        for label, rx in (("code tuple/list", _TUPLE_ENUM_RE),
                          ("docstring/comment", _PATH_ENUM_RE)):
            for m in rx.finditer(src):
                line = src[: m.start()].count("\n") + 1
                offenders.append(f"{rel}:{line} ({label}): {m.group(0)!r}")
    assert not offenders, (
        "the external-provenance keys are enumerated outside policy.py — "
        "import `policy.EXTERNAL_PROVENANCE_KEYS` instead (this duplication is "
        "exactly what let the SQL and Python halves drift apart):\n  "
        + "\n  ".join(offenders))


def test_keys_are_sql_safe_identifiers() -> None:
    """Each key is interpolated into a FIXED `$.<key>` JSON path inside SQL
    TEXT (no bind param is possible for a json path in the LIKE-disjunct form),
    so a key carrying a quote would be an injection through our own source.
    `policy` raises at import if this is violated; this pins the contract."""
    ident = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
    assert EXTERNAL_PROVENANCE_KEYS
    for key in EXTERNAL_PROVENANCE_KEYS:
        assert ident.fullmatch(key), key
    assert len(set(EXTERNAL_PROVENANCE_KEYS)) == len(EXTERNAL_PROVENANCE_KEYS)
