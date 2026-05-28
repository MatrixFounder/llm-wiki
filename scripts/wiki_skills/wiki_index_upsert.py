"""`wiki-index-upsert` CLI — real impl per task-001-25.

R-07.4 type-mapping + R-07.5 body normalization centralized here.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

from scripts.wiki_index.factory import make_repo
from scripts.wiki_index.layout import SCHEMA_FILE
from scripts.wiki_index.models import Page
from scripts.wiki_index.normalization import (
    BodyNormalizationError,
    UnmappedTypeError,
    normalize_body_for_fts,
    normalize_frontmatter,
)
from scripts.wiki_skills._common import emit
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

    config: dict[str, str] = {"vault_id": args.vault}
    if args.db_path:
        config["db_path"] = args.db_path
    repo = make_repo(config)
    try:
        adapter = ManualSourceAdapter()
        item = SourceItem(kind="manual", source_path=src, vault_root=vault_root,
                          vault_id=args.vault)
        out = adapter.fetch(item)
        try:
            updated_fm, db_type = normalize_frontmatter(
                out.frontmatter, source_path=src,
            )
            normalized_body = normalize_body_for_fts(out.body_text)
        except (UnmappedTypeError, BodyNormalizationError) as e:
            return emit({"error": type(e).__name__, "message": str(e),
                         "source": str(src)}, exit_code=6)

        title = str(updated_fm.get("title") or out.page_slug)
        tldr_raw = updated_fm.get("tldr")
        tldr_val = tldr_raw if isinstance(tldr_raw, str) else None
        date_val: date | None = None
        fm_date = updated_fm.get("date")
        if isinstance(fm_date, date):
            date_val = fm_date
        elif isinstance(fm_date, str):
            try:
                date_val = date.fromisoformat(fm_date)
            except ValueError:
                date_val = None
        last_modified = datetime.fromtimestamp(src.stat().st_mtime)
        tags = list(updated_fm.get("tags") or [])

        page = Page(
            vault_id=args.vault,
            slug=out.page_slug,
            project=out.project,
            type=db_type,  # type: ignore[arg-type]
            title=title,
            file_path=str(src.relative_to(vault_root)),
            tldr=tldr_val,
            date=date_val,
            last_modified=last_modified,
            file_hash=out.file_hash,
            frontmatter_json=updated_fm,
            body_excerpt=normalized_body[:1000],
            tags=tags,
        )
        outcome = repo.upsert_page(page)
        if outcome != "unchanged":
            repo.replace_refs(args.vault, out.page_slug, out.project, out.refs)
        return emit({
            "action": outcome,
            "vault_id": args.vault,
            "slug": out.page_slug,
            "project": out.project,
            "refs_count": len(out.refs),
        })
    finally:
        repo.close()


if __name__ == "__main__":
    sys.exit(main())
