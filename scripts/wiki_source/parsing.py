"""Frontmatter + body parsing helpers for source adapters."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import frontmatter  # python-frontmatter
from slugify import slugify

from scripts.wiki_index.layout import COURSE_TIER_DIR, VAULT_TIER_PROJECT
from scripts.wiki_index.layout_config import RefRule

_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")


class FrontmatterParseError(ValueError):
    """Raised when YAML frontmatter is malformed or absent where required."""


class MissingRequiredFieldError(ValueError):
    """Raised when a required frontmatter field is absent."""


def parse_frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    """Parse markdown file → (frontmatter_dict, body_text). Raises
    FrontmatterParseError on YAML errors. Empty/missing frontmatter → ({}, full_text)."""
    try:
        post = frontmatter.load(path)
    except Exception as e:
        raise FrontmatterParseError(f"{path}: {e}") from e
    return dict(post.metadata), post.content


_H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)


def first_h1(body: str) -> str | None:
    """PW-F title-source: the first ATX `# Heading` in the body, or None.
    Used by frontmatter synthesis to title a frontmatter-less note (obsidian-
    personal); falls back to the filename stem when absent."""
    m = _H1_RE.search(body)
    return m.group(1).strip() if m else None


def compute_file_hash(body: str | bytes) -> str:
    """SHA-256 hex digest of body. str→encoded as UTF-8."""
    if isinstance(body, str):
        body = body.encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def extract_wiki_links(body: str) -> list[tuple[str, int, str]]:
    """Find `[[link]]` and `[[link|display]]` patterns in body. Returns list of
    `(target_slug, line_number, source_quote)`. Source quote = the matching
    line truncated to 200 chars.

    Karpathy path — byte-identical to the historical behaviour; kept distinct
    from `extract_refs` (TASK 012 / PW-D) so the single-rule wiki-link output
    cannot drift. `extract_refs` with the karpathy wiki-link rule reproduces this
    (asserted in tests/test_ref_extraction.py)."""
    out: list[tuple[str, int, str]] = []
    for i, line in enumerate(body.splitlines(), start=1):
        for m in _WIKILINK_RE.finditer(line):
            target = m.group(1).strip()
            if not target:
                continue
            quote = line.strip()[:200]
            out.append((target, i, quote))
    return out


def _stem_transform(target: str) -> str:
    """`transform: stem` — reduce a markdown-link href to its basename without
    extension (`foo/bar.md#section` → `bar`)."""
    return Path(target.split("#", 1)[0]).stem


def extract_refs(body: str, rules: Sequence[RefRule]) -> list[tuple[str, int, str]]:
    """Config-driven cross-reference extraction (TASK 012 / PW-D). Iterates the
    layout's `ref_extraction[]` rules; returns `(target, line_number, quote)` —
    the same shape as `extract_wiki_links`. Per-rule `target_group` selects the
    capture group; `transform: stem` reduces a path/href to its basename.

    The karpathy config carries only the wiki-link rule, so its output equals
    `extract_wiki_links`. The ReDoS budget gate (layout_config) vets each
    operator-supplied `regex` at config-load; the patterns here are pre-vetted by
    that gate before this function ever runs."""
    compiled = [(re.compile(r.regex), r.target_group, r.transform) for r in rules]
    out: list[tuple[str, int, str]] = []
    for i, line in enumerate(body.splitlines(), start=1):
        quote = line.strip()[:200]
        for pattern, group, transform in compiled:
            for m in pattern.finditer(line):
                target = m.group(group).strip()
                if transform == "stem":
                    target = _stem_transform(target)
                target = target.strip()
                if target:
                    out.append((target, i, quote))
    return out


def derive_slug(path: Path, vault_root: Path) -> tuple[str, str]:
    """Derive (slug, project) from a file path.

    project = slugified course-directory name if `path` lives under
    `<vault>/Lessons/<Course>/…`; else `VAULT_TIER_PROJECT` sentinel
    (`layout.py`). Slug = file stem (without .md).
    """
    slug = path.stem
    try:
        rel = path.relative_to(vault_root)
    except ValueError:
        return slug, VAULT_TIER_PROJECT
    parts = rel.parts
    if len(parts) >= 2 and parts[0] == COURSE_TIER_DIR:
        course_name = parts[1]
        project = slugify(course_name, lowercase=True, separator="-")
        return slug, project
    return slug, VAULT_TIER_PROJECT
