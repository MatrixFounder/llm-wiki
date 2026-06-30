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


# --- TASK 047: shared concept-mentions AUTO-block format ---------------------
# Pure string helpers shared by `write_concept_page` (seeds the block on create) and
# `rendering.render_concept_mentions_body` (regenerates it) so a seeded block is
# byte-identical to a rendered one. Kept here (the neutral leaf both already import) to
# respect the _pages.py "no import another skill / no rendering edge" dependency rule.

AUTO_MENTIONS_NAME = "mentions"
_MENTIONS_HEADING = "## Mentions across sources"


def wrap_auto_block(name: str, body: str) -> str:
    """The full `<!-- BEGIN-AUTO:name -->\\n<body>\\n<!-- END-AUTO:name -->` text."""
    return f"<!-- BEGIN-AUTO:{name} -->\n{body}\n<!-- END-AUTO:{name} -->"


def format_concept_mentions_body(source_slugs: list[str]) -> str:
    """The AUTO-block BODY for a concept's mentions: the heading + one `- [[slug]]` per
    source (caller dedups+sorts; sanitized on egress). Heading-only when empty — the block
    is always present, never absent."""
    lines = [_MENTIONS_HEADING, ""]
    lines += [f"- [[{sanitize_markdown_text(s)}]]" for s in source_slugs]
    return "\n".join(lines).rstrip()


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


def build_repo_config(
    vault_id: str, *, vault_root: Path | None, db_path_flag: str | None
) -> dict[str, Any]:
    """TASK 022 — the DB resolution chain → a `factory.make_repo` config dict.

    Precedence **`--db-path` flag > `index_db` (WIKI_SCHEMA.md) > global**: an explicit
    flag wins; else, if a `vault_root` is known, a declared `index_db` is resolved
    (`config_loader.resolve_index_db_path`); else the dict carries no `db_path` and
    `make_repo` falls back to the global DB — byte-identical to the pre-TASK-022 behaviour.
    `make_repo` is UNCHANGED: it still applies the R-03 iCloud guard + global fallback to
    whatever `db_path` (if any) this helper sets. `config_loader` is imported **lazily**
    inside the body (no top-level `_common → wiki_index` edge — `rendering` imports `_common`).
    """
    cfg: dict[str, Any] = {"vault_id": vault_id}
    if db_path_flag:
        cfg["db_path"] = db_path_flag
        return cfg
    if vault_root is not None:
        from scripts.wiki_index.config_loader import (
            ConfigValidationError,
            resolve_index_db_path,
        )
        from scripts.wiki_index.layout import GLOBAL_VAULT_SENTINEL
        # vdd-multi HIGH-L1: only honour a vault's index_db when the root belongs to the
        # addressed vault (a CWD walk-up must not redirect a by-id command to a different
        # vault's DB). The global sentinel ("all") opts out of the check — island intent.
        expected = None if vault_id == GLOBAL_VAULT_SENTINEL else vault_id
        try:
            resolved = resolve_index_db_path(vault_root, expected_vault_id=expected)
        except ConfigValidationError:
            # vdd-multi MED-2: a malformed/unsafe index_db must fail as a clean JSON
            # envelope (the orchestrator parses stdout), never a raw traceback. The value
            # is NOT echoed (CWE-209). Centralised here so all CLIs inherit it.
            emit({"error": "INVALID_INDEX_DB", "field": "index_db",
                  "reason": "index_db is unsafe or malformed (escapes the vault, is a "
                            "symlink, or is an absolute path outside the framework's "
                            "app-data dir without WIKI_ALLOW_ABSOLUTE_INDEX_DB)",
                  "hint": "If this vault's index_db is an absolute path (e.g. an iCloud "
                          "vault whose DB must live outside iCloud), re-run with "
                          "WIKI_ALLOW_ABSOLUTE_INDEX_DB=1, or set it once in your shell "
                          "profile / .claude settings `env`. Absolute paths under the OS "
                          "app-data dir (…/Application Support, …/.local/share, %APPDATA%) "
                          "are trusted automatically."},
                 exit_code=6)
            raise SystemExit(6)
        if resolved is not None:
            cfg["db_path"] = str(resolved)
    return cfg


def resolve_vault_root_for_cli(args: Any) -> Path | None:
    """TASK 022 — resolve a CLI's `vault_root` BEFORE `make_repo`, so a vault-local
    `index_db` is honoured (the ordering inversion). Precedence: an explicit
    `--vault-root` flag → a walk-up from CWD to the nearest `WIKI_SCHEMA.md`
    (`config_loader.find_vault_root`, like `.git`/`.obsidian`) → `None`.

    `None` is the global-DB case (no flag, not inside a vault) — `build_repo_config`
    then injects no `db_path` and `make_repo` falls back to global (byte-identity). Used
    uniformly by every subcommand so `record`/`apply` resolve the SAME local DB as
    `scan`/`prepare` (no split-brain). `config_loader` is imported lazily.
    """
    flag = getattr(args, "vault_root", None)
    if flag:
        return Path(flag)
    from scripts.wiki_index.config_loader import (
        VaultRootNotFoundError,
        find_vault_root,
    )
    try:
        return find_vault_root(Path.cwd())
    except (VaultRootNotFoundError, OSError):  # OSError: CWD deleted (vdd-multi LOW)
        return None
