"""`wiki-index-render` CLI — real impl per task-001-26."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from scripts.wiki_index.factory import make_repo
from scripts.wiki_index.models import LogEvent
from scripts.wiki_index.rendering import (
    atomic_write,
    extract_custom_sections,
    render_index,
)
from scripts.wiki_skills._common import emit


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="wiki-index-render")
    p.add_argument("--vault", required=True, help="vault_id.")
    p.add_argument("--output", default=None,
                   help="Output path (default: <vault_root>/index.md).")
    p.add_argument("--db-path", default=None)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    config: dict[str, str] = {"vault_id": args.vault}
    if args.db_path:
        config["db_path"] = args.db_path
    repo = make_repo(config)
    try:
        vault = repo.get_vault(args.vault)
        if vault is None:
            return emit({"error": "VAULT_NOT_REGISTERED",
                         "vault_id": args.vault}, exit_code=6)
        output_path = (Path(args.output) if args.output
                       else vault.root_path / "index.md")
        preserve: dict[str, str] = {}
        if output_path.exists():
            preserve = extract_custom_sections(
                output_path.read_text(encoding="utf-8")
            )
        content = render_index(repo, args.vault, preserve_custom=preserve)
        atomic_write(output_path, content)
        page_count = content.count("- [[")
        repo.append_log_event(LogEvent(
            vault_id=args.vault,
            event_ts=datetime.now(),
            event_type="reindex",
            subject=f"index render → {output_path.name}",
            pages_created_json=[],
            pages_updated_json=[],
            details_json={"output_path": str(output_path),
                          "page_count": page_count},
        ))
        return emit({
            "action": "rendered",
            "vault_id": args.vault,
            "output_path": str(output_path),
            "page_count": page_count,
        })
    finally:
        repo.close()


if __name__ == "__main__":
    sys.exit(main())
