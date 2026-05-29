"""`wiki-merge` CLI — TASK 005 / R-4.7.

Fold a duplicate entity (`from`) into the canonical one (`into`): the
duplicate's surfaces become aliases of the survivor (the alias table IS the
redirect — no `[[...]]` wikilink rewriting, C-7), refs are re-pointed, and the
`from` page is deleted so a full reindex cannot re-materialise it.

Write order is **Class A first** (C-8): append `into.aliases`, delete the
`from` page, THEN the single-transaction `merge_entities` DB mirror. If the DB
mirror fails after the file ops, the state is recoverable via
`wiki-reindex --delta` (Class A is canonical) → MERGE_MIRROR_FAILED.

Exit codes: 0 ok (incl. --dry-run) · 2 INVALID_ARG · 3 ENTITY_NOT_FOUND ·
4 ENTITY_FILE_MISSING · 5 INVALID_MERGE · 6 MERGE_MIRROR_FAILED.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import frontmatter

from scripts.wiki_index.factory import make_repo
from scripts.wiki_index.security import PathTraversalError
from scripts.wiki_skills._common import (
    atomic_write_text,
    emit,
    resolve_entity_file,
    sanitize_alias_surface,
)

_log = logging.getLogger("wiki_merge")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="wiki-merge")
    p.add_argument("from_slug", help="Duplicate entity to fold away.")
    p.add_argument("into_slug", help="Canonical entity to keep.")
    p.add_argument("--vault", required=True, help="Vault id.")
    p.add_argument("--dry-run", action="store_true",
                   help="Report what would move; write nothing.")
    p.add_argument("--db-path", default=None)
    return p


def _append_aliases(path: Path, surfaces: list[str]) -> None:
    post = frontmatter.load(str(path))
    raw = post.metadata.get("aliases")
    aliases = list(raw) if isinstance(raw, list) else []
    changed = False
    for s in surfaces:
        if s and s not in aliases:
            aliases.append(s)
            changed = True
    if changed:
        post.metadata["aliases"] = aliases
        atomic_write_text(path, frontmatter.dumps(post))


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    config: dict[str, str] = {"vault_id": args.vault}
    if args.db_path:
        config["db_path"] = args.db_path
    repo = make_repo(config)
    try:
        from_ent = repo.resolve_entity(args.vault, args.from_slug)
        into_ent = repo.resolve_entity(args.vault, args.into_slug)
        if from_ent is None:
            return emit({"error": "ENTITY_NOT_FOUND", "field": "from_slug",
                         "reason": "no such entity in vault"}, 3)
        if into_ent is None:
            return emit({"error": "ENTITY_NOT_FOUND", "field": "into_slug",
                         "reason": "no such entity in vault"}, 3)
        from_slug, into_slug = from_ent.slug, into_ent.slug
        if from_slug == into_slug:
            return emit({"error": "INVALID_MERGE", "field": "from_slug",
                         "reason": "cannot merge an entity into itself"}, 5)

        from_aliases = repo.list_aliases(args.vault, from_slug)
        # F4 (vdd-multi): sanitize surfaces before they land in into's Class A
        # frontmatter — DB-stored aliases were only edge-stripped at ingest, so
        # drop control chars + cap length (defense-in-depth at this egress).
        redirect_surfaces = [
            s for s in (sanitize_alias_surface(x)
                        for x in [from_slug, from_ent.name, *from_aliases]) if s
        ]

        if args.dry_run:
            refs = repo.get_backlinks(args.vault, from_slug)
            return emit({
                "from": from_slug, "into": into_slug, "dry_run": True,
                "refs_repointed": len(refs),
                "aliases_absorbed": len({s for s in redirect_surfaces if s}),
            })

        # Class A FIRST (C-8): locate both pages, append into.aliases, delete from page.
        try:
            into_path = resolve_entity_file(repo, args.vault, into_slug)
            from_path = resolve_entity_file(repo, args.vault, from_slug)
        except PathTraversalError:
            return emit({"error": "ENTITY_FILE_MISSING", "field": "from_slug",
                         "reason": "an entity file is missing on disk or outside "
                                   "vault; run wiki-reindex --delta"}, 4)
        if into_path is None or from_path is None:
            return emit({"error": "ENTITY_NOT_FOUND",
                         "reason": "entity row vanished mid-merge"}, 3)

        _append_aliases(into_path, redirect_surfaces)
        os.unlink(from_path)

        # Class B mirror (single transaction). On failure the Class A mutation
        # already landed → recoverable via `wiki-reindex --delta`.
        try:
            report = repo.merge_entities(args.vault, from_slug, into_slug)
        except Exception:
            # F7 (vdd-multi): log the cause to stderr for diagnosis (NEVER into
            # the JSON envelope — CWE-209). Class A already landed, so the state
            # is recoverable via `wiki-reindex --delta`.
            _log.warning("merge_entities DB mirror failed for %s→%s",
                         from_slug, into_slug, exc_info=True)
            return emit({"error": "MERGE_MIRROR_FAILED", "field": "into_slug",
                         "reason": "Class A merge applied but the DB mirror failed; "
                                   "run wiki-reindex --delta to reconcile"}, 6)

        return emit({
            "from": from_slug, "into": into_slug, "action": "merged",
            "refs_repointed": report.refs_repointed,
            "aliases_absorbed": report.aliases_absorbed,
            "aliases_skipped": report.aliases_skipped,
        })
    finally:
        repo.close()


if __name__ == "__main__":
    sys.exit(main())
