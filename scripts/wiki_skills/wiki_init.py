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
from scripts.wiki_index.layout import (
    COURSE_TIER_DIR,
    LOG_SUBDIR,
    SCAFFOLD_DIRS,
    SCHEMA_FILE,
    VAULT_INDEX_DIR,
)
from scripts.wiki_index.models import LogEvent, Vault

_VAULT_ID_RE = re.compile(r"^[a-z][a-z0-9-]{1,30}[a-z0-9]$")
_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"

# TASK 012 / R-X2.1: layout names accepted by --layout. `flat`/`per-project` are
# legacy aliases for the Karpathy grammar (they + `karpathy` get the two-tier
# page-subdir scaffold); `dev-project`/`obsidian-personal` index an existing tree.
_LAYOUT_CHOICES = ["flat", "per-project", "karpathy", "dev-project", "obsidian-personal"]
_KARPATHY_LAYOUTS = {"flat", "per-project", "karpathy"}


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


def _sanitize_desc(desc: str | None, vault_id: str) -> str:
    """Description for the templates' double-quoted YAML scalar (DF-3): drop the
    `"`/newlines that would break the quoted scalar (and thus the §D8
    rebuild-from-Class-A path)."""
    d = desc or f"LLM Wiki vault: {vault_id}"
    return d.replace('"', "'").replace("\n", " ").replace("\r", " ")


_AGENT_FILES_CONFIG = _TEMPLATES_DIR / "agent-files.yaml"


def _agent_file_specs() -> list[tuple[str, str]]:
    """``[(filename, template_name), …]`` for the configured vendors
    (``templates/agent-files.yaml`` — e.g. CLAUDE.md/Claude Code,
    GEMINI.md/Gemini CLI). Falls back to the Claude default if that config is
    missing/malformed, so a vault always gets at least a CLAUDE.md."""
    fallback = [("CLAUDE.md", "CLAUDE.md.tmpl")]
    try:
        doc = yaml.safe_load(_AGENT_FILES_CONFIG.read_text(encoding="utf-8"))
        vendors = doc["vendors"]
        order = doc.get("default_vendors") or list(vendors)
        specs = [(str(vendors[v]["filename"]), str(vendors[v]["template"])) for v in order]
        return specs or fallback
    except Exception:  # noqa: BLE001 — trusted repo file; any fault → safe default
        return fallback


def _write_agent_files(
    vault_root: Path, placeholders: dict[str, str], *, force: bool
) -> dict[str, str]:
    """Render one agent-instructions file PER configured vendor into the vault
    root (CLAUDE.md, GEMINI.md, …) so agents launched there get the wiki
    operating instructions. NON-destructive: writes each only if absent (or
    ``--force``) — never clobbers an operator's own file. Returns
    ``{filename: "written"|"exists"}``. Shared by `scaffold_new` and
    `register_existing` — a registered existing vault is otherwise agent-unusable
    (dogfood DF-018-INIT-1)."""
    out: dict[str, str] = {}
    for filename, template_name in _agent_file_specs():
        target = vault_root / filename
        if target.exists() and not force:
            out[filename] = "exists"
            continue
        # Per-vendor resilience: a missing/misconfigured template (or a stray `$`
        # in it) must NOT crash init — the vault is already registered and the
        # other vendors' files are unaffected. Record "error" and continue
        # (vdd-adversarial: missing-template FileNotFoundError used to crash
        # scaffold/register after the repo write, leaving a half-done state).
        try:
            rendered = Template(
                (_TEMPLATES_DIR / template_name).read_text(encoding="utf-8")
            ).substitute(placeholders)
        except (OSError, KeyError, ValueError):
            out[filename] = "error"
            continue
        target.write_text(rendered)
        out[filename] = "written"
    return out


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
    # TASK 012 / R-X2.1: only the Karpathy family gets the two-tier page-subdir
    # scaffold (_sources/_concepts/…). dev-project / obsidian-personal index an
    # EXISTING tree (docs/, numbered folders), so scaffolding Karpathy dirs into
    # a real repo would be wrong — write WIKI_SCHEMA.md + register only.
    _layout = args.layout or "per-project"
    _karpathy = _layout in _KARPATHY_LAYOUTS
    if _karpathy:
        for sub in SCAFFOLD_DIRS:
            (vault_root / sub).mkdir(parents=True, exist_ok=True)
    # DF-3 (dogfood): the description renders into a *double-quoted* YAML scalar
    # in the template (`description: "${description}"`). The old default
    # `LLM Wiki vault: {vault_id}` had an unquoted colon → invalid YAML →
    # MISSING_VAULT_ID on --register-existing (the §D8 rebuild-from-Class-A
    # path). Quoting fixes the colon; sanitize embedded `"`/newlines so the
    # quoted scalar stays well-formed even for an operator-supplied --description.
    _desc = _sanitize_desc(args.description, vault_id)
    placeholders = {
        "vault_id": vault_id,
        "language": args.language or "en",
        "layout": _layout,
        "description": _desc,
    }
    schema_path = vault_root / SCHEMA_FILE
    if not schema_path.exists() or args.force:
        schema_path.write_text(
            Template((_TEMPLATES_DIR / "WIKI_SCHEMA.md.tmpl").read_text())
            .substitute(placeholders)
        )
    agent_files = _write_agent_files(vault_root, placeholders, force=bool(args.force))
    if _karpathy:
        idx = vault_root / VAULT_INDEX_DIR / "index.md"
        if not idx.exists():
            idx.write_text(f"# {vault_id} Index\n\nAuto-generated.\n")
        now = datetime.now()
        log_month = (vault_root / VAULT_INDEX_DIR / LOG_SUBDIR /
                     f"{now.strftime('%Y-%m')}.md")
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
        "agent_files": agent_files,
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
    schema_path = vault_root / SCHEMA_FILE
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
    is_two_tier = any((vault_root / COURSE_TIER_DIR).glob(f"*/{SCHEMA_FILE}"))
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
    # Make the registered vault agent-workable: write the per-vendor agent files
    # (CLAUDE.md, GEMINI.md, …) from their templates if absent (non-destructive —
    # never clobber an operator's own file without --force). Without them, an
    # agent launched at the vault root has no wiki operating instructions
    # (DF-018-INIT-1).
    agent_files = _write_agent_files(
        vault_root,
        {
            "vault_id": vault_id,
            "language": str(fm.get("language") or "en"),
            "layout": str(fm.get("layout") or "per-project"),
            "description": _sanitize_desc(fm.get("description"), vault_id),
        },
        force=bool(args.force),
    )
    return _emit({
        "action": action,
        "vault_id": vault_id,
        "vault_root": str(vault_root),
        "is_two_tier": is_two_tier,
        "db_path": str(db_path),
        "agent_files": agent_files,
    })


def reconcile(args: argparse.Namespace) -> int:
    if not args.vault:
        return _emit({"error": "MISSING_VAULT_ARG"}, exit_code=1)
    vault_root = Path(args.vault).resolve(strict=True)
    schema_path = vault_root / SCHEMA_FILE
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
    p.add_argument("--layout", default=None, choices=_LAYOUT_CHOICES)
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
