"""R-07.4 + R-07.5 normalization for wiki-index-upsert.

R-07.4 (frontmatter type-mapping): translate file frontmatter `type:` to
the schema CHECK enum + tag marker. Source: TASK.md §6.1 mapping table.

R-07.5 (body normalization): strip ```mermaid``` fenced blocks and
`<!-- SECTION:* -->` HTML anchors from body BEFORE indexing in FTS5 / storing
in `body_excerpt`. Pinned regex with anti-tail-eat sanity check (unclosed
fence → fail-fast).
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from slugify import slugify

from scripts.wiki_index.layout import (
    CONCEPTS_SUBDIR,
    ENTITIES_SUBDIR,
    QUERIES_SUBDIR,
)


def _json_safe(value: Any) -> Any:
    """Recursively convert date/datetime to ISO strings. Required because
    python-frontmatter parses `date:` into datetime.date objects which
    `json.dumps` cannot serialize."""
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value

# -----------------------------------------------------------------------------
# R-07.5 — body normalization regex
# -----------------------------------------------------------------------------
_MERMAID_RE = re.compile(r"^```mermaid\s*\n.*?^```\s*$", re.DOTALL | re.MULTILINE)
_SECTION_RE = re.compile(r"<!--\s*SECTION:[a-z0-9_-]+\s*-->")
_MERMAID_OPEN_RE = re.compile(r"^```mermaid", re.MULTILINE)


class BodyNormalizationError(ValueError):
    """Anti-tail-eat: raised when `^```mermaid` openings exceed closed matches.
    Without this, a malformed fence would silently eat body to EOF."""


def normalize_body_for_fts(body: str) -> str:
    """Strip ```mermaid``` fences and `<!-- SECTION:* -->` anchors.

    Raises `BodyNormalizationError` if any mermaid fence is unclosed (sanity
    check vs anti-tail-eat regression — R-07.5 spec).
    """
    open_count = len(_MERMAID_OPEN_RE.findall(body))
    closed_count = len(_MERMAID_RE.findall(body))
    if open_count != closed_count:
        raise BodyNormalizationError(
            f"unclosed mermaid fence: {open_count} ``` mermaid opens vs "
            f"{closed_count} matched close fences"
        )
    out = _MERMAID_RE.sub("", body)
    out = _SECTION_RE.sub("", out)
    return out


# -----------------------------------------------------------------------------
# R-07.4 — frontmatter type-mapping (TASK.md §6.1)
# -----------------------------------------------------------------------------
TYPE_MAPPING: dict[str, tuple[str, str | None]] = {
    "summary": ("summary", None),
    "summary-light": ("summary", "summary-light"),
    "lesson-summary": ("summary", "lesson-summary"),
    "meeting-summary": ("summary", "meeting-summary"),
    "concept": ("concept", None),
    # wiki-ingest convention: _entities/*.md carry `type: external` (per
    # WIKI-INGEST-V1.1-CONTRACT). Page-display-wise these are concept-like
    # (definition + properties); the entities table holds entity-specific
    # metadata. So pages.type=concept, tag the page with `external` for
    # downstream filters.
    "external": ("concept", "external"),
    "person": ("concept", "person"),
    "company": ("concept", "company"),
    "product": ("concept", "product"),
    "group": ("concept", "group"),
    "query": ("query", None),
    "brief": ("brief", None),
    "research": ("research", None),
    "index": ("index", None),
}


class UnmappedTypeError(ValueError):
    """Raised when frontmatter `type` is not in TYPE_MAPPING table — caller
    must add it (Schema Change Request) or correct the source frontmatter."""


def _slugify_concept(c: str) -> str:
    """python-slugify with explicit kebab-case settings.

    Documented lossy: 'C++' → 'c'; 'OAuth 2.0' → 'oauth-2-0'."""
    return slugify(c, lowercase=True, separator="-",
                   regex_pattern=r"[^a-z0-9\-]")


_PATH_TYPE_FALLBACK: dict[str, str] = {
    CONCEPTS_SUBDIR: "concept",
    ENTITIES_SUBDIR: "external",
    # TASK 007 / R-6.5: a `_queries/<slug>.md` page missing an explicit
    # `type:` infers `query` from its directory (defensive — wiki-query
    # `apply` always writes `type: query`, but reindex of a hand-authored
    # query page stays robust).
    QUERIES_SUBDIR: "query",
}


def _infer_type_from_path(source_path: Path | None) -> str | None:
    """If ``source_path`` lives under ``_concepts/`` or ``_entities/`` and
    frontmatter has no ``type:``, return the implied raw type. Real vaults
    (esp. wiki-ingest output) often omit ``type:`` because the directory
    convention is self-documenting.
    """
    if source_path is None:
        return None
    for part in source_path.parts:
        if part in _PATH_TYPE_FALLBACK:
            return _PATH_TYPE_FALLBACK[part]
    return None


def normalize_frontmatter(
    fm: dict[str, Any], *, source_path: Path | None = None,
) -> tuple[dict[str, Any], str]:
    """Translate frontmatter via §6.1 mapping table.

    Returns `(updated_fm, db_type)`. `updated_fm` has:
      - tags = original tags + marker (if mapped) + slugified concepts; dedup
        preserving order.
      - concepts[] preserved verbatim if present.

    If ``type:`` is missing but ``source_path`` lives under ``_concepts/`` or
    ``_entities/``, the type is inferred from the directory (path-aware
    fallback for wiki-ingest-generated files that carry ``kind: concept``
    rather than ``type: concept``).
    """
    raw_type = fm.get("type")
    if not raw_type:
        inferred = _infer_type_from_path(source_path)
        if inferred:
            raw_type = inferred
    if not raw_type or raw_type not in TYPE_MAPPING:
        raise UnmappedTypeError(
            f"frontmatter type={raw_type!r} not in TYPE_MAPPING. Valid: "
            f"{sorted(TYPE_MAPPING)}"
        )
    db_type, marker = TYPE_MAPPING[raw_type]

    existing_tags: list[str] = list(fm.get("tags") or [])
    new_tags: list[str] = list(existing_tags)
    if marker and marker not in new_tags:
        new_tags.append(marker)
    for concept in fm.get("concepts") or []:
        if not isinstance(concept, str):
            continue
        slug = _slugify_concept(concept)
        if slug and slug not in new_tags:
            new_tags.append(slug)

    updated = _json_safe(dict(fm))
    assert isinstance(updated, dict)
    updated["tags"] = new_tags
    return updated, db_type
