"""`wiki-index-upsert` CLI — real impl per task-001-25.

R-07.4 type-mapping + R-07.5 body normalization centralized here.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from scripts.wiki_index.factory import make_repo
from scripts.wiki_index.layout import SCHEMA_FILE
from scripts.wiki_index.layout_config import (
    derive_discovered_page,
    resolve_layout_config,
)
from scripts.wiki_index.normalization import (
    BodyNormalizationError,
    UnmappedTypeError,
)
from scripts.wiki_index.reindex import derive_indexed_page
from scripts.wiki_skills._common import build_repo_config, emit
from scripts.wiki_source.base import SourceItem
from scripts.wiki_source.manual import ManualSourceAdapter


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="wiki-index-upsert")
    p.add_argument("--vault", required=True, help="vault_id.")
    p.add_argument("--source", required=True, help="Absolute path to markdown source.")
    p.add_argument("--db-path", default=None, help="Override DB path (testing).")
    p.add_argument("--vault-root", default=None,
                   help="Vault root path (default: walk up from --source).")
    return p


def _find_vault_root(src: Path) -> Path | None:
    """Walk up from src looking for the vault schema-marker file."""
    current = src.parent
    while True:
        if (current / SCHEMA_FILE).is_file():
            return current
        if current.parent == current:
            return None
        current = current.parent


def upsert_one(
    vault_id: str,
    src: Path,
    vault_root: Path,
    repo: Any,
) -> dict[str, Any]:
    """Programmatic entry-point for upserting a single page into the index.

    Accepts an already-open repo (caller owns lifecycle — does NOT close it).
    Returns the envelope dict with private '_exit_code' key (does NOT call emit()).
    main() pops '_exit_code' and calls emit() with the appropriate exit code.
    """
    # TASK 024 / Q-024-1: upsert is now LAYOUT-AWARE — it resolves the vault's
    # layout and routes through the SAME shared per-file derivation as `reindex`
    # (`derive_indexed_page`), so a single-file upsert files byte-identically to a
    # reindex (project via the layout's project_pattern, slug via slug_strategy,
    # type via the layout's type_mapping, refs via ref_extraction). Previously it
    # used `derive_slug`'s `_vault_` fallback + the karpathy module `TYPE_MAPPING`,
    # diverging on PARA/obsidian-personal vaults (→ `_vault_` rows + dup-on-reindex).
    adapter = ManualSourceAdapter()
    item = SourceItem(kind="manual", source_path=src, vault_root=vault_root,
                      vault_id=vault_id)
    config = resolve_layout_config(vault_root)
    disc = derive_discovered_page(src, vault_root, config)
    try:
        out, page, _updated_fm, refs = derive_indexed_page(
            adapter, item, config, disc, vault_id, cite_skipped=[])
    except (UnmappedTypeError, BodyNormalizationError) as e:
        return {"error": type(e).__name__, "message": str(e),
                "source": str(src), "_exit_code": 6}

    outcome = repo.upsert_page(page)
    if outcome != "unchanged":
        repo.replace_refs(vault_id, out.page_slug, out.project, refs)
    return {
        "action": outcome,
        "vault_id": vault_id,
        "slug": out.page_slug,
        "project": out.project,
        "refs_count": len(refs),
        "_exit_code": 0,
    }


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    src = Path(args.source).resolve(strict=True)
    if args.vault_root:
        vault_root = Path(args.vault_root).resolve(strict=True)
    else:
        found = _find_vault_root(src)
        if found is None:
            return emit({"error": "VAULT_ROOT_NOT_FOUND",
                         "from_path": str(src)}, exit_code=6)
        vault_root = found

    config = build_repo_config(  # TASK 022: vault_root already resolved above
        args.vault, vault_root=vault_root, db_path_flag=args.db_path)
    repo = make_repo(config)
    try:
        result = upsert_one(args.vault, src, vault_root, repo)
        exit_code: int = result.pop("_exit_code", 0)
        return emit(result, exit_code=exit_code)
    finally:
        repo.close()


if __name__ == "__main__":
    sys.exit(main())
