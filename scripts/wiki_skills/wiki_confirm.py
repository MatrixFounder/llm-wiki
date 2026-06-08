"""`wiki-confirm` CLI — TASK 005 / R-4.2, R-4.3, R-4.4.

Promote a candidate entity → confirmed (`--undo` reverses), or bulk-promote by
mention threshold (`--auto [--threshold N] [--dry-run]`). Confirm-state is
Class A canonical (entity-page frontmatter `is_candidate`), so this writes the
frontmatter FIRST, then mirrors to the DB via `set_entity_candidate` (which
bypasses the upsert MIN() downgrade-guard — operator intent is authoritative).

Exit codes: 0 ok (incl. idempotent / dry-run) · 2 INVALID_ARG ·
3 ENTITY_NOT_FOUND · 4 ENTITY_FILE_MISSING.

NOTE: the optional `promote`/`demote` log_events row (Q5) is deferred — it
requires log.md bi-directional mirroring (M-2 contract), out of this bead's scope.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import frontmatter

from scripts.wiki_index.factory import make_repo
from scripts.wiki_index.security import PathTraversalError
from scripts.wiki_skills._common import atomic_write_text, build_repo_config, emit, resolve_entity_file, resolve_vault_root_for_cli


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="wiki-confirm")
    p.add_argument("slug", nargs="?", default=None,
                   help="Entity slug (or alias) to confirm. Omit with --auto.")
    p.add_argument("--vault", required=True, help="Vault id.")
    p.add_argument("--undo", action="store_true",
                   help="Demote confirmed → candidate (operator-explicit).")
    p.add_argument("--auto", action="store_true",
                   help="Bulk-promote candidates with mentions >= --threshold.")
    p.add_argument("--threshold", type=int, default=3,
                   help="Auto-promote mention threshold (default 3).")
    p.add_argument("--dry-run", action="store_true",
                   help="With --auto: report the would-promote set; write nothing.")
    p.add_argument("--vault-root", default=None,
                   help="Vault root (resolve a local index_db); walks up from CWD when omitted.")
    p.add_argument("--db-path", default=None)
    return p


def _sync_frontmatter_candidate(path: Path, *, candidate: bool) -> bool:
    """Set `is_candidate` in the entity-page frontmatter and add/remove the
    `candidate` tag. Returns True iff the file changed (idempotent otherwise)."""
    post = frontmatter.load(str(path))
    current = bool(post.metadata.get("is_candidate", False))
    raw_tags = post.metadata.get("tags")
    tags = list(raw_tags) if isinstance(raw_tags, list) else []
    new_tags = list(tags)
    if candidate:
        if "candidate" not in new_tags:
            new_tags.append("candidate")
    else:
        new_tags = [t for t in new_tags if t != "candidate"]
    if current == candidate and new_tags == tags:
        return False
    post.metadata["is_candidate"] = candidate
    if new_tags or "tags" in post.metadata:
        post.metadata["tags"] = new_tags
    atomic_write_text(path, frontmatter.dumps(post))
    return True


def _run_single(repo: object, args: argparse.Namespace) -> int:
    ent = repo.resolve_entity(args.vault, args.slug)  # type: ignore[attr-defined]
    if ent is None:
        return emit({"error": "ENTITY_NOT_FOUND", "field": "slug",
                     "reason": "no such entity in vault"}, 3)
    slug = ent.slug  # canonicalize (slug arg may have been an alias)
    target_candidate = bool(args.undo)
    target_int = 1 if args.undo else 0
    try:
        path = resolve_entity_file(repo, args.vault, slug)
    except PathTraversalError:
        return emit({"error": "ENTITY_FILE_MISSING", "field": "slug",
                     "reason": "entity file missing on disk or outside vault; "
                               "run wiki-reindex --delta"}, 4)
    if path is None:
        return emit({"error": "ENTITY_NOT_FOUND", "field": "slug",
                     "reason": "no such entity in vault"}, 3)
    fm_changed = _sync_frontmatter_candidate(path, candidate=target_candidate)
    db_changed = repo.set_entity_candidate(args.vault, slug, target_int)  # type: ignore[attr-defined]
    return emit({
        "slug": slug,
        "status": "candidate" if target_candidate else "confirmed",
        "changed": fm_changed or db_changed,
    })


def _run_auto(repo: object, args: argparse.Namespace) -> int:
    # F6 (vdd-multi): a non-positive threshold would promote EVERY candidate
    # (mentions_count >= 0 is always true) — a mass-promotion footgun.
    if args.threshold < 1:
        return emit({"error": "INVALID_ARG", "field": "threshold",
                     "reason": "--threshold must be a positive integer (>= 1)"}, 2)
    if args.dry_run:
        would = repo.preview_promotable(args.vault, args.threshold)  # type: ignore[attr-defined]
        scanned = len(repo.list_candidates(args.vault))  # type: ignore[attr-defined]
        return emit({"action": "auto-promote", "dry_run": True,
                     "would_promote": would, "threshold": args.threshold,
                     "scanned": scanned})
    promoted = repo.auto_promote_candidates(args.vault, args.threshold)  # type: ignore[attr-defined]
    # Class A durability: flip the frontmatter of each promoted entity so a
    # full reindex does not revert it to candidate.
    synced: list[str] = []
    for slug in promoted:
        try:
            path = resolve_entity_file(repo, args.vault, slug)
        except PathTraversalError:
            path = None
        if path is not None:
            _sync_frontmatter_candidate(path, candidate=False)
            synced.append(slug)
    return emit({"action": "auto-promote", "promoted": promoted,
                 "frontmatter_synced": synced, "threshold": args.threshold})


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    config = build_repo_config(  # TASK 022
        args.vault, vault_root=resolve_vault_root_for_cli(args),
        db_path_flag=args.db_path)
    repo = make_repo(config)
    try:
        if args.auto:
            return _run_auto(repo, args)
        if not args.slug:
            return emit({"error": "INVALID_ARG", "field": "slug",
                         "reason": "a slug is required unless --auto is given"}, 2)
        return _run_single(repo, args)
    finally:
        repo.close()


if __name__ == "__main__":
    sys.exit(main())
