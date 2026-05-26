"""`wiki-init` CLI — scaffold-new / register-existing / reconcile.

Real impl per tasks 001-21/22/23.

Exit codes:
  0 — success
  1 — usage error
  6 — MISSING_WIKI_SCHEMA / MISSING_VAULT_ID / INVALID_VAULT_ID /
      VAULT_ID_COLLISION / VAULT_NOT_REGISTERED / VAULT_NOT_FOUND
  7 — VAULT_RENAMED warning; requires --confirm to apply
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from string import Template
from typing import Any

import yaml

from scripts.wiki_index.factory import make_repo
from scripts.wiki_index.layout import SCAFFOLD_DIRS
from scripts.wiki_index.models import LogEvent, Vault

_VAULT_ID_RE = re.compile(r"^[a-z][a-z0-9-]{1,30}[a-z0-9]$")
_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"


def _validate_vault_id(vault_id: str) -> bool:
    if vault_id == "_global_":
        return True
    return bool(_VAULT_ID_RE.match(vault_id)) and "--" not in vault_id


def _emit(payload: dict[str, Any], exit_code: int = 0) -> int:
    print(json.dumps(payload, ensure_ascii=False))
    return exit_code


def _split_frontmatter(text: str) -> dict[str, Any]:
    if not text.startswith("---\n"):
        return {}
    parts = text.split("---\n", 2)
    if len(parts) < 3:
        return {}
    try:
        fm = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return {}
    return fm if isinstance(fm, dict) else {}


def _suggested_vault_id(vault_root: Path) -> str:
    base = vault_root.name.lower()
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    return base or "my-vault"


def scaffold_new(args: argparse.Namespace) -> int:
    # Require --vault explicitly. Silently defaulting to cwd ("." ) has
    # caused accidental scaffolds inside the project repo. Operator must
    # opt in to the target directory.
    if not args.vault:
        return _emit({
            "error": "MISSING_VAULT_ARG",
            "hint": "provide --vault <absolute path> (cwd default removed "
                    "to prevent accidental scaffolds in the project repo)",
        }, exit_code=1)
    vault_id = args.vault_id or _suggested_vault_id(Path(args.vault))
    if not _validate_vault_id(vault_id):
        return _emit({"error": "INVALID_VAULT_ID", "received": vault_id,
                      "pattern": _VAULT_ID_RE.pattern}, exit_code=6)
    vault_root = Path(args.vault).resolve()
    vault_root.mkdir(parents=True, exist_ok=True)
    for sub in SCAFFOLD_DIRS:
        (vault_root / sub).mkdir(parents=True, exist_ok=True)
    placeholders = {
        "vault_id": vault_id,
        "language": args.language or "en",
        "layout": args.layout or "per-project",
        "description": args.description or f"LLM Wiki vault: {vault_id}",
    }
    schema_path = vault_root / "WIKI_SCHEMA.md"
    if not schema_path.exists() or args.force:
        schema_path.write_text(
            Template((_TEMPLATES_DIR / "WIKI_SCHEMA.md.tmpl").read_text())
            .substitute(placeholders)
        )
    claude_path = vault_root / "CLAUDE.md"
    if not claude_path.exists() or args.force:
        claude_path.write_text(
            Template((_TEMPLATES_DIR / "CLAUDE.md.tmpl").read_text())
            .substitute(placeholders)
        )
    idx = vault_root / "00-Vault-Index" / "index.md"
    if not idx.exists():
        idx.write_text(f"# {vault_id} Index\n\nAuto-generated.\n")
    now = datetime.now()
    log_month = vault_root / "00-Vault-Index" / "log" / f"{now.strftime('%Y-%m')}.md"
    if not log_month.exists():
        log_month.write_text(f"# Log {now.strftime('%Y-%m')}\n\n")

    config: dict[str, Any] = {"vault_id": vault_id}
    if args.db_path:
        config["db_path"] = str(args.db_path)
    repo = make_repo(config)
    db_path = getattr(repo, "db_path", None)
    try:
        if repo.get_vault(vault_id) is None:
            repo.register_vault(Vault(
                vault_id=vault_id,
                name=placeholders["description"],
                root_path=vault_root,
                schema_version="2.0",
                registered_at=datetime.now(),
                config_json={"language": placeholders["language"],
                             "layout": placeholders["layout"]},
            ))
    finally:
        repo.close()
    return _emit({
        "action": "scaffolded",
        "vault_id": vault_id,
        "vault_root": str(vault_root),
        "db_path": str(db_path),
    })


def register_existing(args: argparse.Namespace) -> int:
    if not args.vault:
        return _emit({"error": "MISSING_VAULT_ARG",
                      "hint": "provide --vault <path>"}, exit_code=1)
    try:
        vault_root = Path(args.vault).resolve(strict=True)
    except FileNotFoundError:
        return _emit({"error": "VAULT_NOT_FOUND", "vault": str(args.vault)},
                     exit_code=6)
    schema_path = vault_root / "WIKI_SCHEMA.md"
    if not schema_path.is_file():
        return _emit({
            "error": "MISSING_WIKI_SCHEMA",
            "expected_path": str(schema_path),
            "hint": "Run wiki-ingest init or use --scaffold-new",
        }, exit_code=6)
    fm = _split_frontmatter(schema_path.read_text(encoding="utf-8"))
    vault_id = fm.get("vault_id")
    if not vault_id:
        return _emit({
            "error": "MISSING_VAULT_ID",
            "wiki_schema_path": str(schema_path),
            "suggested_vault_id": _suggested_vault_id(vault_root),
            "hint": "Add 'vault_id: <slug>' to WIKI_SCHEMA.md frontmatter "
                    "(ADR-002 §D1.1, no hash fallback).",
        }, exit_code=6)
    if not _validate_vault_id(vault_id):
        return _emit({
            "error": "INVALID_VAULT_ID",
            "received": vault_id,
            "pattern": _VAULT_ID_RE.pattern,
        }, exit_code=6)
    is_two_tier = any((vault_root / "Lessons").glob("*/WIKI_SCHEMA.md"))
    config: dict[str, Any] = {"vault_id": vault_id}
    if args.db_path:
        config["db_path"] = str(args.db_path)
    repo = make_repo(config)
    db_path = getattr(repo, "db_path", None)
    try:
        existing = repo.get_vault(vault_id)
        if existing is None:
            repo.register_vault(Vault(
                vault_id=vault_id,
                name=str(fm.get("description") or vault_id),
                root_path=vault_root,
                schema_version=str(fm.get("schema_version", "2.0")),
                registered_at=datetime.now(),
                config_json={"is_two_tier": is_two_tier,
                             "language": fm.get("language"),
                             "layout": fm.get("layout")},
            ))
            action = "registered"
        elif existing.root_path == vault_root:
            action = "already-registered"
        else:
            return _emit({
                "error": "VAULT_ID_COLLISION",
                "vault_id": vault_id,
                "existing_root_path": str(existing.root_path),
                "new_root_path": str(vault_root),
                "hint": "Pick a different vault_id, or run --reconcile if "
                        "this is a folder rename.",
            }, exit_code=6)
    finally:
        repo.close()
    return _emit({
        "action": action,
        "vault_id": vault_id,
        "vault_root": str(vault_root),
        "is_two_tier": is_two_tier,
        "db_path": str(db_path),
    })


def reconcile(args: argparse.Namespace) -> int:
    if not args.vault:
        return _emit({"error": "MISSING_VAULT_ARG"}, exit_code=1)
    vault_root = Path(args.vault).resolve(strict=True)
    schema_path = vault_root / "WIKI_SCHEMA.md"
    if not schema_path.is_file():
        return _emit({"error": "MISSING_WIKI_SCHEMA"}, exit_code=6)
    fm = _split_frontmatter(schema_path.read_text(encoding="utf-8"))
    new_vault_id = fm.get("vault_id")
    if not new_vault_id or not _validate_vault_id(new_vault_id):
        return _emit({"error": "INVALID_VAULT_ID", "received": new_vault_id},
                     exit_code=6)
    config: dict[str, Any] = {"vault_id": new_vault_id}
    if args.db_path:
        config["db_path"] = str(args.db_path)
    repo = make_repo(config)
    try:
        existing = repo.get_vault_by_root_path(vault_root)
        if existing is None:
            return _emit({
                "error": "VAULT_NOT_REGISTERED",
                "vault_root": str(vault_root),
                "hint": "Run --register-existing first",
            }, exit_code=6)
        if existing.vault_id == new_vault_id:
            return _emit({"action": "no-change", "vault_id": new_vault_id})
        if not args.confirm:
            return _emit({
                "warning": "VAULT_RENAMED",
                "old_vault_id": existing.vault_id,
                "new_vault_id": new_vault_id,
                "hint": "Re-run with --confirm to apply CASCADE rename",
            }, exit_code=7)
        old_vault_id = existing.vault_id
        repo.rename_vault(old_vault_id, new_vault_id)
        repo.append_log_event(LogEvent(
            vault_id=new_vault_id,
            event_ts=datetime.now(),
            event_type="reclassify",
            subject=f"vault rename {old_vault_id} → {new_vault_id}",
            pages_created_json=[],
            pages_updated_json=[],
            details_json={"old_vault_id": old_vault_id,
                          "new_vault_id": new_vault_id},
        ))
        return _emit({
            "action": "renamed",
            "old_vault_id": old_vault_id,
            "new_vault_id": new_vault_id,
        })
    finally:
        repo.close()


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="wiki-init",
                                description="Bootstrap or register a vault.")
    group = p.add_mutually_exclusive_group()
    group.add_argument("--scaffold-new", action="store_true",
                       help="Create a fresh vault layout (default).")
    group.add_argument("--register-existing", action="store_true",
                       help="Register an existing vault in the DB.")
    group.add_argument("--reconcile", action="store_true",
                       help="Reconcile a renamed vault (ADR-002 §D8).")
    p.add_argument("--vault", help="Absolute path to the vault root.")
    p.add_argument("--vault-id", help="Override vault_id (scaffold-new only).")
    p.add_argument("--db-path", help="Override default DB path (testing).")
    p.add_argument("--language", default=None)
    p.add_argument("--layout", default=None,
                   choices=["flat", "per-project"])
    p.add_argument("--description", default=None)
    p.add_argument("--force", action="store_true")
    p.add_argument("--confirm", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.register_existing:
        return register_existing(args)
    if args.reconcile:
        return reconcile(args)
    return scaffold_new(args)


if __name__ == "__main__":
    sys.exit(main())
