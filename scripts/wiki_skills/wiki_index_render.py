"""`wiki-index-render` CLI — real impl per task-001-26."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from scripts.wiki_index.factory import make_repo
from scripts.wiki_index.layout_config import resolve_layout_config
from scripts.wiki_index.models import LogEvent
from scripts.wiki_index.security import PathTraversalError, validate_inside_vault
from scripts.wiki_index.sqlite_repository import SQLiteRepository
from scripts.wiki_index.rendering import (
    apply_auto_block,
    atomic_write,
    extract_custom_sections,
    render_and_write_auto_indexes,
    render_concept_mentions_body,
    render_index,
)
from scripts.wiki_skills._common import (
    AUTO_MENTIONS_NAME,
    build_repo_config,
    emit,
    resolve_vault_root_for_cli,
)
from scripts.wiki_skills.wiki_index_upsert import upsert_one


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="wiki-index-render")
    p.add_argument("--vault", required=True, help="vault_id.")
    p.add_argument("--output", default=None,
                   help="Output path (default: <vault_root>/index.md).")
    p.add_argument("--auto-indexes", action="store_true",
                   help="Render the layout's auto_indexes[] targets (PW-H, e.g. "
                        "docs/KNOWN_ISSUES.md) instead of index.md.")
    p.add_argument("--concept-mentions", action="store_true",
                   help="TASK 047 — regenerate each concept page's BEGIN-AUTO:mentions block "
                        "(the sources that reference it) from page_entity_refs; re-indexes each "
                        "rewritten page so it leaves no hash-mismatch drift.")
    p.add_argument("--vault-root", default=None,
                   help="Vault root (resolve a local index_db); walks up from CWD when omitted.")
    p.add_argument("--db-path", default=None)
    return p


def _render_concept_mentions(
    repo: SQLiteRepository, vault_id: str, vault_root: Path,
) -> tuple[list[str], list[str]]:
    """Regenerate every concept page's `BEGIN-AUTO:mentions` block. Only pages whose bytes
    actually change are rewritten + re-indexed (so `pages.file_hash` stays in sync → no spurious
    `hash-mismatch` drift). Idempotent — a second run with no new refs writes nothing.
    Returns `(updated_slugs, missing_slugs)` (missing = DB row whose `.md` is absent on disk)."""
    updated: list[str] = []
    missing: list[str] = []
    for slug, _project, file_path in repo.concept_pages(vault_id):
        page_path = vault_root / file_path
        # H-6 / R-26 containment: the DB-stored `file_path` is untrusted on egress. Refuse a
        # path that escapes the vault (parent-symlink or `..`) or a symlinked leaf BEFORE any
        # read/write, mirroring wiki_verify_multi._read_page_text + the entity writer. A poisoned
        # / missing row is skipped (recorded in `missing`), never followed out of the vault.
        try:
            validate_inside_vault(page_path, vault_root)
        except (PathTraversalError, FileNotFoundError, OSError):
            missing.append(slug)
            continue
        if page_path.is_symlink():
            missing.append(slug)
            continue
        existing = page_path.read_text(encoding="utf-8")
        body = render_concept_mentions_body(repo, vault_id, slug)
        new_md = apply_auto_block(existing, AUTO_MENTIONS_NAME, body)
        if new_md != existing:
            atomic_write(page_path, new_md)
            upsert_one(vault_id, page_path, vault_root, repo)   # re-index → refresh file_hash + refs
            updated.append(slug)
    return updated, missing


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
        if args.concept_mentions:
            if not isinstance(repo, SQLiteRepository):
                return emit({"error": "NOT_SUPPORTED",
                             "message": "--concept-mentions requires a SQLite index"},
                            exit_code=6)
            updated, missing = _render_concept_mentions(repo, args.vault, vault.root_path)
            repo.append_log_event(LogEvent(
                vault_id=args.vault, event_ts=datetime.now(), event_type="reindex",
                subject="concept-mentions render",
                pages_created_json=[], pages_updated_json=updated,
                details_json={"updated_count": len(updated)},
            ))
            return emit({"action": "rendered-concept-mentions", "vault_id": args.vault,
                         "updated": updated, "updated_count": len(updated), "missing": missing})
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
