"""`wiki-alias` CLI — TASK 005 / R-5.1, R-5.2.

Register / remove / list aliases for an entity. An alias is Class A canonical
(entity-page frontmatter `aliases:`) + Class B mirror (`entity_aliases`). A
surface that already resolves to a *different* entity is rejected with
ALIAS_COLLISION (the hard `(vault_id, alias)` PK).

Exit codes: 0 ok · 2 INVALID_ARG · 3 ENTITY_NOT_FOUND · 4 ENTITY_FILE_MISSING ·
5 ALIAS_COLLISION.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import frontmatter

from scripts.wiki_index.factory import make_repo
from scripts.wiki_index.security import PathTraversalError
from scripts.wiki_index.sqlite_repository import AliasCollisionError
from scripts.wiki_skills._common import atomic_write_text, emit, resolve_entity_file

_ALIAS_TYPES = (
    "spelling_variant", "translation", "nickname",
    "acronym", "former_name", "product_codename",
)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="wiki-alias")
    p.add_argument("slug", help="Canonical entity slug (or an existing alias).")
    p.add_argument("--vault", required=True, help="Vault id.")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--add", metavar="SURFACE", help="Register an alias.")
    g.add_argument("--remove", metavar="SURFACE", help="Drop an alias.")
    g.add_argument("--list", action="store_true", help="List the entity's aliases.")
    p.add_argument("--type", choices=_ALIAS_TYPES, default="spelling_variant",
                   help="alias_type for --add (Class B only; default spelling_variant).")
    p.add_argument("--db-path", default=None)
    return p


def _validate_surface(s: str) -> str | None:
    """Strip + length-cap + reject control chars/newlines (CWE-117 hygiene).
    Returns the cleaned surface, or None if invalid."""
    s = s.strip()
    if not s or len(s) > 200 or any(ord(c) < 32 for c in s):
        return None
    return s


def _sync_alias_frontmatter(path: Path, surface: str, *, add: bool) -> bool:
    post = frontmatter.load(str(path))
    raw = post.metadata.get("aliases")
    aliases = list(raw) if isinstance(raw, list) else []
    if add:
        if surface in aliases:
            return False
        aliases.append(surface)
    else:
        if surface not in aliases:
            return False
        aliases = [a for a in aliases if a != surface]
    post.metadata["aliases"] = aliases
    atomic_write_text(path, frontmatter.dumps(post))
    return True


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    config: dict[str, str] = {"vault_id": args.vault}
    if args.db_path:
        config["db_path"] = args.db_path
    repo = make_repo(config)
    try:
        ent = repo.resolve_entity(args.vault, args.slug)
        if ent is None:
            return emit({"error": "ENTITY_NOT_FOUND", "field": "slug",
                         "reason": "no such entity in vault"}, 3)
        slug = ent.slug

        if args.list:
            return emit({"slug": slug, "aliases": repo.list_aliases(args.vault, slug)})

        try:
            path = resolve_entity_file(repo, args.vault, slug)
        except PathTraversalError:
            return emit({"error": "ENTITY_FILE_MISSING", "field": "slug",
                         "reason": "entity file missing on disk or outside vault; "
                                   "run wiki-reindex --delta"}, 4)
        if path is None:
            return emit({"error": "ENTITY_NOT_FOUND", "field": "slug",
                         "reason": "no such entity in vault"}, 3)

        if args.add is not None:
            surface = _validate_surface(args.add)
            if surface is None:
                return emit({"error": "INVALID_ARG", "field": "add",
                             "reason": "alias surface empty, too long, or has control chars"}, 2)
            if surface in repo.list_aliases(args.vault, slug):
                return emit({"slug": slug, "alias": surface, "action": "unchanged"})
            # Collision pre-check (resolve_entity = slug/alias; find_entity_by_name
            # = display name). A surface that already resolves to / names a
            # DIFFERENT entity would hijack that entity's resolution → refuse.
            conflict = repo.resolve_entity(args.vault, surface)
            if conflict is not None and conflict.slug != slug:
                return emit({"error": "ALIAS_COLLISION", "field": "add",
                             "reason": f"surface already resolves to entity "
                                       f"{conflict.slug!r}"}, 5)
            # DF-5: surface already resolves to THIS entity (own slug / own
            # alias) → redundant self-alias, no-op rather than a duplicate row.
            if conflict is not None and conflict.slug == slug:
                return emit({"slug": slug, "alias": surface, "action": "unchanged"})
            # DF-4: surface equals a DIFFERENT entity's canonical name → would
            # hijack searches for that name. resolve_entity does not see names.
            name_owner = repo.find_entity_by_name(args.vault, surface)
            if name_owner is not None and name_owner != slug:
                return emit({"error": "ALIAS_COLLISION", "field": "add",
                             "reason": f"surface is the name of entity "
                                       f"{name_owner!r}"}, 5)
            # Class A first, then DB mirror.
            _sync_alias_frontmatter(path, surface, add=True)
            try:
                repo.add_alias(args.vault, surface, slug, args.type)
            except AliasCollisionError as e:
                return emit({"error": "ALIAS_COLLISION", "field": "add",
                             "reason": f"surface already resolves to entity "
                                       f"{e.conflicting_slug!r}"}, 5)
            return emit({"slug": slug, "alias": surface, "action": "added"})

        # --remove
        surface = _validate_surface(args.remove)
        if surface is None:
            return emit({"error": "INVALID_ARG", "field": "remove",
                         "reason": "alias surface empty, too long, or has control chars"}, 2)
        if surface not in repo.list_aliases(args.vault, slug):
            return emit({"slug": slug, "alias": surface, "action": "unchanged"})
        _sync_alias_frontmatter(path, surface, add=False)
        repo.remove_alias(args.vault, surface)
        return emit({"slug": slug, "alias": surface, "action": "removed"})
    finally:
        repo.close()


if __name__ == "__main__":
    sys.exit(main())
