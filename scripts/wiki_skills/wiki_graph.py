"""`wiki-graph` CLI (TASK 032 / R-032-5, ADR-004 D6) — READ-ONLY event-graph
traversal over the typed page-to-page edges (implements/supersedes/causes/related
+ their auto-derived inverses). Three subcommands:

  wiki-graph backlinks <slug> [--kind K]                  # inbound refs
  wiki-graph neighbors <slug> [--kind K] [--direction D]  # one-hop in/out/both
  wiki-graph chain     <slug>  --kind K  [--direction D] [--depth N]  # bounded BFS

Injection-safe (TASK 013 posture): `--kind` is allow-list-validated against the v6
edge ref_types; the slug is a BOUND param to the DAL (never string-composed); an
error envelope never echoes the offending value (CWE-117/209). `--depth` is capped
(DoS bound) and the BFS is cycle-safe (DAL `edge_chain`). Read-only — no DB writes.

Exit codes: 0 ok · 2 INVALID_KIND / MISSING_KIND / INVALID_DEPTH · 6 VAULT_NOT_FOUND.
"""

from __future__ import annotations

import argparse
import sys

from scripts.wiki_index.factory import make_repo
from scripts.wiki_index.reindex import _INVERSE_REF_TYPE
from scripts.wiki_skills._common import (
    build_repo_config,
    emit,
    resolve_vault_root_for_cli,
)

# The typed-edge ref_types wiki-graph traverses (allow-list for --kind). DERIVED
# from reindex._INVERSE_REF_TYPE (the single source of truth — the inverse-closed
# set + symmetric `related`) so new edge kinds (TASK 034: invalidated-by/activated-by/
# uses/owns + inverses) are admitted automatically and the two can never drift.
_EDGE_KINDS = tuple(sorted(_INVERSE_REF_TYPE))
_MAX_DEPTH = 16


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="wiki-graph", description="Read-only event-graph traversal (TASK 032).")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("backlinks", "neighbors", "chain"):
        sp = sub.add_parser(name)
        sp.add_argument("slug")
        sp.add_argument("--vault", required=True, help="vault_id to query.")
        sp.add_argument("--project", default="_vault_",
                        help="page project (default '_vault_'). REQUIRED for the "
                             "outbound side on non-flat (project_pattern) layouts — "
                             "`refs_from`/neighbors filter on the exact project.")
        sp.add_argument("--kind", default=None,
                        help="edge ref_type to filter/traverse (chain: required).")
        sp.add_argument("--db-path", default=None)
        sp.add_argument("--vault-root", default=None)
        if name == "neighbors":
            sp.add_argument("--direction", choices=["in", "out", "both"], default="both")
        if name == "chain":
            sp.add_argument("--direction", choices=["in", "out"], default="out")
            sp.add_argument("--depth", type=int, default=8)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    # --kind allow-list (no echo of an invalid value — CWE-209).
    if args.kind is not None and args.kind not in _EDGE_KINDS:
        return emit({"error": "INVALID_KIND", "valid": list(_EDGE_KINDS)}, 2)
    if args.cmd == "chain":
        if args.kind is None:
            return emit({"error": "MISSING_KIND",
                         "hint": "chain requires --kind <edge>"}, 2)
        if args.depth < 1:
            return emit({"error": "INVALID_DEPTH", "hint": "--depth must be >= 1"}, 2)
    config = build_repo_config(
        args.vault, vault_root=resolve_vault_root_for_cli(args),
        db_path_flag=args.db_path)
    repo = make_repo(config)
    try:
        if repo.get_vault(args.vault) is None:
            return emit({"error": "VAULT_NOT_FOUND", "vault": args.vault}, 6)
        if args.cmd == "backlinks":
            refs = repo.get_backlinks(args.vault, args.slug, args.kind)
            return emit({
                "action": "backlinks", "slug": args.slug, "kind": args.kind,
                "backlinks": [
                    {"page_slug": r.page_slug, "page_project": r.page_project,
                     "ref_type": r.ref_type} for r in refs],
            })
        if args.cmd == "neighbors":
            refs = repo.neighbors(
                args.vault, args.slug, args.project, args.direction, args.kind)
            return emit({
                "action": "neighbors", "slug": args.slug,
                "direction": args.direction, "kind": args.kind,
                "neighbors": [
                    {"page_slug": r.page_slug, "entity_slug": r.entity_slug,
                     "ref_type": r.ref_type} for r in refs],
            })
        # chain
        depth = min(args.depth, _MAX_DEPTH)
        chain = repo.edge_chain(args.vault, args.slug, args.kind, args.direction, depth)
        return emit({
            "action": "chain", "slug": args.slug, "kind": args.kind,
            "direction": args.direction, "depth": depth,
            "chain": [{"slug": s, "depth": d} for s, d in chain],
        })
    finally:
        repo.close()


if __name__ == "__main__":
    sys.exit(main())
