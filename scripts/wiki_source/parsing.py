"""Frontmatter + body parsing helpers for source adapters."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

import frontmatter  # python-frontmatter
from slugify import slugify

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


def compute_file_hash(body: str | bytes) -> str:
    """SHA-256 hex digest of body. str→encoded as UTF-8."""
    if isinstance(body, str):
        body = body.encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def extract_wiki_links(body: str) -> list[tuple[str, int, str]]:
    """Find `[[link]]` and `[[link|display]]` patterns in body. Returns list of
    `(target_slug, line_number, source_quote)`. Source quote = the matching
    line truncated to 200 chars."""
    out: list[tuple[str, int, str]] = []
    for i, line in enumerate(body.splitlines(), start=1):
        for m in _WIKILINK_RE.finditer(line):
            target = m.group(1).strip()
            if not target:
                continue
            quote = line.strip()[:200]
            out.append((target, i, quote))
    return out


def derive_slug(path: Path, vault_root: Path) -> tuple[str, str]:
    """Derive (slug, project) from a file path.

    project='<course-slug>' if path is under `<vault>/Lessons/<Course>/...`;
    else '_vault_' sentinel. Slug = file stem (without .md). Project name is
    kebab-slugified.
    """
    slug = path.stem
    try:
        rel = path.relative_to(vault_root)
    except ValueError:
        return slug, "_vault_"
    parts = rel.parts
    if len(parts) >= 2 and parts[0] == "Lessons":
        course_name = parts[1]
        project = slugify(course_name, lowercase=True, separator="-")
        return slug, project
    return slug, "_vault_"
