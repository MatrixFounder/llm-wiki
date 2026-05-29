"""Private helpers shared across CLI scaffolds in this package.

Not exposed outside scripts/wiki_skills/. Underscore prefix marks intent.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


def emit(payload: dict[str, Any], exit_code: int = 0) -> int:
    """Print one-line JSON and return ``exit_code``.

    Default success: ``exit_code=0``. Error envelopes (payloads containing
    an ``"error"`` key) MUST pass a non-zero code so shell scripts and
    test harnesses can detect failures via ``$?``. Convention (matches
    ``wiki_init._emit``): ``6`` for validation/look-up errors, ``7`` for
    interactive-confirm-required warnings.
    """
    print(json.dumps(payload, ensure_ascii=False), file=sys.stdout)
    return exit_code


def sanitize_alias_surface(surface: str, *, cap: int = 200) -> str | None:
    """Lossy clean of an alias surface for Class A write-back: strip edges, drop
    control chars (`ord < 32`), cap length. Returns the cleaned surface or None
    if nothing usable remains. Used by the merge path (F4, vdd-multi) so aliases
    absorbed from the DB — which the ingest side only `.strip()`-ed — cannot
    carry control chars or unbounded length into `into`'s frontmatter."""
    surface = surface.strip()
    if not surface:
        return None
    surface = "".join(c for c in surface if ord(c) >= 32)[:cap]
    return surface or None


_LINE_LEADING_MD_ACTIVES = frozenset("#>|*+-~")


def sanitize_markdown_text(text: str) -> str:
    """Escape every markdown/HTML-active sequence so ``text`` renders as
    literal plain prose (text-only allowlist).

    Lifted to this neutral module (TASK 007 / Decision-16 — no skill imports
    another skill) so both ``wiki-extract-concepts`` (concept-page bodies,
    H-4) and ``wiki-query`` (the synthesised answer body, R-6.3 egress guard)
    share one implementation.

    Attacks closed (verbatim from the H-4 vdd-multi 2026-05-28 hardening):
      * ``<tag>`` / CDATA / HTML entity smuggling → ``&lt;...&gt;`` / ``&amp;...``
      * ``[text](javascript:...)`` / ``![img](data:...)`` → ``\\[...\\](...)``
      * ``[[wikilink]]`` → ``\\[\\[wikilink\\]\\]`` (Obsidian wikilink injection)
      * ```code``` / `````fence````` → ``\\`...\\``` (dataview / mermaid embeds)
      * Leading-line ``#``/``>``/``|``/``*``/``+``/``-``/``~`` → ``\\X``
    """
    s = (text
         .replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;"))
    s = s.replace("`", "\\`")
    s = s.replace("[", "\\[").replace("]", "\\]")
    out_lines: list[str] = []
    for line in s.split("\n"):
        stripped = line.lstrip()
        if stripped and stripped[0] in _LINE_LEADING_MD_ACTIVES:
            ws_len = len(line) - len(stripped)
            line = f"{line[:ws_len]}\\{stripped[0]}{stripped[1:]}"
        out_lines.append(line)
    return "\n".join(out_lines)


def atomic_write_text(target: Path, text: str) -> None:
    """Atomically write ``text`` to ``target`` (tempfile in the same dir +
    fsync + ``os.replace``). ``os.replace`` is ``rename(2)`` on POSIX — it does
    NOT follow a symlink at ``target``, so a swapped-in symlink cannot redirect
    the write outside the dir. Shared by the TASK 005 entity-resolution CLIs
    for Class A frontmatter mutation (same primitive as ``write_concept_page``).
    """
    fd, tmp_name = tempfile.mkstemp(
        dir=str(target.parent), prefix=".wiki-tmp-", suffix=".md"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, target)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def resolve_entity_file(repo: Any, vault_id: str, slug: str) -> Path | None:
    """Resolve an entity's Class A markdown file to a validated absolute path.

    Returns ``None`` if the entity has no row (caller → ``ENTITY_NOT_FOUND``).
    Raises ``PathTraversalError`` (from ``validate_inside_vault``, ``strict=True``)
    if the path escapes the vault OR does not exist on disk — the caller maps
    the latter to ``ENTITY_FILE_MISSING`` (DB/disk drift). Skills never build
    raw SQL: the relative path comes from ``repo.get_entity_file_path``.
    """
    from scripts.wiki_index.security import (
        PathTraversalError,
        validate_inside_vault,
    )

    rel = repo.get_entity_file_path(vault_id, slug)
    if rel is None:
        return None
    vault = repo.get_vault(vault_id)
    if vault is None:
        return None
    raw = Path(vault.root_path) / rel
    # F3 (vdd-multi): refuse a symlinked entity file — match the O_NOFOLLOW
    # posture of write_concept_page. validate_inside_vault(strict=True) already
    # blocks escapes OUTSIDE the vault; this additionally refuses a symlink AT
    # the entity-file path, closing the swap-page-for-symlink read/unlink vector
    # the confirm/alias/merge CLIs would otherwise follow.
    if raw.is_symlink():
        raise PathTraversalError(f"entity file is a symlink (refusing to follow): {rel}")
    return validate_inside_vault(raw, Path(vault.root_path))
