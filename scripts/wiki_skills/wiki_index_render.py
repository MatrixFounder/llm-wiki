"""`wiki-index-render` CLI — real impl per task-001-26."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from scripts.wiki_index.factory import make_repo
from scripts.wiki_index.layout_config import resolve_layout_config
from scripts.wiki_index.models import LogEvent
from scripts.wiki_index.rendering import (
    atomic_write,
    extract_custom_sections,
    render_and_write_auto_indexes,
    render_index,
)
from scripts.wiki_skills._common import build_repo_config, emit, resolve_vault_root_for_cli


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="wiki-index-render")
    p.add_argument("--vault", required=True, help="vault_id.")
    p.add_argument("--output", default=None,
                   help="Output path (default: <vault_root>/index.md).")
    p.add_argument("--auto-indexes", action="store_true",
                   help="Render the layout's auto_indexes[] targets (PW-H, e.g. "
                        "docs/KNOWN_ISSUES.md) instead of index.md.")
    p.add_argument("--vault-root", default=None,
                   help="Vault root (resolve a local index_db); walks up from CWD when omitted.")
    p.add_argument("--db-path", default=None)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    config = build_repo_config(  # TASK 022
        args.vault, vault_root=resolve_vault_root_for_cli(args),
        db_path_flag=args.db_path)
    repo = make_repo(config)
    try:
        vault = repo.get_vault(args.vault)
        if vault is None:
            return emit({"error": "VAULT_NOT_REGISTERED",
                         "vault_id": args.vault}, exit_code=6)
        if args.auto_indexes:
            layout = resolve_layout_config(vault.root_path)
            written = render_and_write_auto_indexes(
                repo, args.vault, vault.root_path, layout,
                generated_at=datetime.now().isoformat(),
            )
            return emit({
                "action": "rendered-auto-indexes",
                "vault_id": args.vault,
                "outputs": written,
            })
        # LOW-2 (critic-security): `--output` is the operator's EXPLICIT, typed
        # choice of where to write index.md — intentionally NOT vault-bounded
        # (unlike the config-driven auto_indexes[].output, which a shared/committed
        # layout config controls and IS guarded by _safe_output_path). Bounding an
        # explicit CLI arg would break the legitimate "render my index elsewhere"
        # use case; the risk is an operator overwriting their own file. Left open.
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
