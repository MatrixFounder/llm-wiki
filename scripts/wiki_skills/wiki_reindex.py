"""`wiki-reindex` CLI — real impl per tasks-001-30 (--full) and 001-31 (--delta)."""

from __future__ import annotations

import argparse
import sys

from scripts.wiki_index.factory import make_repo
from scripts.wiki_index.layout import GLOBAL_VAULT_SENTINEL
from scripts.wiki_index.reindex import reindex_delta, reindex_full
from scripts.wiki_skills._common import build_repo_config, emit, resolve_vault_root_for_cli


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
    p.add_argument("--vault-root", default=None,
                   help="Vault root (resolve a local index_db); walks up from CWD when omitted.")
    p.add_argument("--db-path", default=None)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    factory_vault = args.vault or GLOBAL_VAULT_SENTINEL
    config = build_repo_config(  # TASK 022
        factory_vault, vault_root=resolve_vault_root_for_cli(args),
        db_path_flag=args.db_path)
    repo = make_repo(config)
    try:
        # DF-074-4 (family sweep) — the DAL raises `ValueError("vault_id=… not registered")`
        # from `reindex_full`/`reindex_delta`, and nothing caught it: a typo'd `--vault` exited
        # **1 with NO envelope and a raw traceback that echoed the vault_id**, for plain user
        # input. Under the family convention that this repo just made normative, `1` means "a
        # bug in the CLI" — so the operator was told to file a bug about their own typo.
        # Guard here rather than catching the ValueError, so the refusal is deliberate and the
        # DAL keeps its invariant. `--all-vaults` iterates the registry and cannot be unknown.
        if not args.all_vaults and args.vault is not None \
                and repo.get_vault(args.vault) is None:
            return emit({"error": "VAULT_NOT_FOUND", "field": "vault",
                         "reason": "no such vault is registered in this index"}, 6)
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
                # TASK 030 / AC-1.4: summed total only — per-vault rel lists stay
                # inside results[] (a flat cross-vault list would lose attribution).
                envelope["new_path_ingested_total"] = sum(
                    len(r["new_path_ingested"]) for r in results)
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
