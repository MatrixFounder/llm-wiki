"""`wiki-reindex` CLI — real impl per tasks-001-30 (--full) and 001-31 (--delta)."""

from __future__ import annotations

import argparse
import sys

from scripts.wiki_index.factory import make_repo
from scripts.wiki_index.layout import GLOBAL_VAULT_SENTINEL
from scripts.wiki_index.reindex import reindex_delta, reindex_full
from scripts.wiki_skills._common import emit


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="wiki-reindex")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--full", action="store_true",
                      help="Class A→B full reconstruction.")
    mode.add_argument("--delta", action="store_true",
                      help="mtime-based incremental update.")
    scope = p.add_mutually_exclusive_group(required=True)
    scope.add_argument("--vault", default=None, help="vault_id to reindex.")
    scope.add_argument("--all-vaults", action="store_true",
                       help="Reindex every registered vault sequentially.")
    p.add_argument("--db-path", default=None)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    factory_vault = args.vault or GLOBAL_VAULT_SENTINEL
    config: dict[str, str] = {"vault_id": factory_vault}
    if args.db_path:
        config["db_path"] = args.db_path
    repo = make_repo(config)
    try:
        if args.all_vaults:
            # TASK 021 (MED): honour --delta across all vaults (was silently --full).
            run = reindex_delta if args.delta else reindex_full
            results = [run(repo, v.vault_id) for v in repo.list_vaults()]
            envelope: dict[str, object] = {
                "action": "reindexed",
                "scope": "all-vaults",
                "mode": "delta" if args.delta else "full",
                "vaults_processed": len(results),
                "slug_collisions": [c for r in results for c in r["slug_collisions"]],
                "results": results,
            }
            if args.delta:
                envelope["touched"] = sum(r["touched"] for r in results)
                envelope["deleted"] = sum(r["deleted"] for r in results)
            else:
                envelope["pages_indexed"] = sum(r["pages"] for r in results)
            return emit(envelope)
        if args.full:
            return emit(reindex_full(repo, args.vault))
        # --delta (task-001-31)
        return emit(reindex_delta(repo, args.vault))
    finally:
        repo.close()


if __name__ == "__main__":
    sys.exit(main())
