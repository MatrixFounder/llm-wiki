"""TASK 058 — `wiki-config`: per-folder vault-config inspection CLI (18th wiki-* CLI).

Phase 1 surface: `show` (effective config + per-key provenance for one folder) and
`tree` (whole-vault override map). Later phases add validate / doctor / fix / set /
init / templates / restore / report / serve.

Contract (Decision-17): one JSON envelope on stdout via `_common.emit`, stable exit
codes (0 ok / 1 usage / 2 precondition / 6 validation), no DB access at all — the
tool must work with a broken or absent index (recovery scenario). Human-readable
output rides `--report <md>` sidecars (wiki-lint precedent), never stdout.

Provenance is computed WITHOUT touching the real resolver (`_resummarize.py` stays
byte-identical): `_provenance.py` replays the cascade with the same primitives and
is release-gated by an equivalence test against `resolve_policy`/`resolve_summarize`.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from scripts.wiki_index.config_loader import find_vault_root
from scripts.wiki_index.security import PathTraversalError, validate_inside_vault
from scripts.wiki_index.sync_config import SyncConfigError
from scripts.wiki_skills._common import atomic_write_text, emit

from ._findings import histogram, render_findings_report, sort_findings
from ._lint import lint_vault
from ._provenance import (
    FolderProvenance,
    TreeNode,
    compute_folder_provenance,
    scan_tree,
)
from ._report_md import render_show_report, render_tree_report


def _resolve_vault_root(args: argparse.Namespace) -> Path | None:
    """`--vault-root` flag → CWD walk-up to WIKI_SCHEMA.md → None."""
    flag = getattr(args, "vault_root", None)
    if flag:
        root = Path(flag)
        return root if root.is_dir() else None
    try:
        return find_vault_root(Path.cwd())
    except Exception:  # VaultRootNotFoundError | OSError (CWD deleted)
        return None


def _resolve_folder(folder_arg: str, vault_root: Path) -> Path | None:
    """Resolve a vault-relative or absolute folder argument to a contained,
    existing directory. Returns None when missing/escaping (caller → exit 2).
    The offending value is never echoed (CWE-209)."""
    raw = Path(folder_arg)
    candidate = raw if raw.is_absolute() else vault_root / raw
    try:
        resolved = validate_inside_vault(candidate, vault_root)
    except (PathTraversalError, OSError):
        return None
    return resolved if resolved.is_dir() else None


def _maybe_report(args: argparse.Namespace, text: str) -> str | None:
    """Write the markdown sidecar when `--report` was passed; returns the path
    echoed into the envelope (or None)."""
    report = getattr(args, "report", None)
    if not report:
        return None
    target = Path(report)
    atomic_write_text(target, text)
    return str(target)


def _cmd_show(args: argparse.Namespace) -> int:
    vault_root = _resolve_vault_root(args)
    if vault_root is None:
        return emit({"error": "VAULT_ROOT_NOT_FOUND",
                     "hint": "pass --vault-root or run inside a vault"}, 2)
    folder = _resolve_folder(args.folder, vault_root)
    if folder is None:
        return emit({"error": "FOLDER_NOT_FOUND", "field": "folder",
                     "hint": "folder must exist inside the vault"}, 2)
    try:
        prov: FolderProvenance = compute_folder_provenance(folder, vault_root)
    except SyncConfigError as exc:
        return emit({"error": exc.code, "field": "sync-config",
                     "level": getattr(exc, "level", None),
                     "reason": exc.reason, "detail": exc.detail}, 6)
    envelope: dict[str, Any] = {
        "action": "shown",
        "vault_root": str(vault_root),
        "folder": prov.folder,
        "effective": prov.effective,
        "provenance": {
            ptr: origin.to_json() for ptr, origin in prov.origins.items()
        },
        "levels": [lvl.to_json() for lvl in prov.levels],
        "warnings": [dict(w) for w in prov.warnings],
    }
    report_path = _maybe_report(args, render_show_report(prov, vault_root))
    if report_path:
        envelope["report"] = report_path
    return emit(envelope)


def _cmd_tree(args: argparse.Namespace) -> int:
    vault_root = _resolve_vault_root(args)
    if vault_root is None:
        return emit({"error": "VAULT_ROOT_NOT_FOUND",
                     "hint": "pass --vault-root or run inside a vault"}, 2)
    nodes: list[TreeNode] = scan_tree(vault_root)
    warnings = [
        {"code": "NON_CASCADING_KEY_IN_SUBFOLDER", "level": n.folder, "keys": list(n.ignored)}
        for n in nodes
        if n.ignored
    ]
    envelope: dict[str, Any] = {
        "action": "tree",
        "vault_root": str(vault_root),
        "files": len(nodes),
        "nodes": [n.to_json() for n in nodes],
        "warnings": warnings,
    }
    report_path = _maybe_report(args, render_tree_report(nodes, vault_root))
    if report_path:
        envelope["report"] = report_path
    return emit(envelope)


def _folder_label_of(file_rel: str) -> str | None:
    """The folder label a sync.yaml finding belongs to (None for other files)."""
    if file_rel == ".wiki/sync.yaml":
        return "."
    if file_rel.endswith("/.wiki/sync.yaml"):
        return file_rel[: -len("/.wiki/sync.yaml")]
    return None


def _cmd_validate(args: argparse.Namespace) -> int:
    import json

    vault_root = _resolve_vault_root(args)
    if vault_root is None:
        return emit({"error": "VAULT_ROOT_NOT_FOUND",
                     "hint": "pass --vault-root or run inside a vault"}, 2)
    findings, files_checked = lint_vault(vault_root)
    if args.folder:
        folder = _resolve_folder(args.folder, vault_root)
        if folder is None:
            return emit({"error": "FOLDER_NOT_FOUND", "field": "folder",
                         "hint": "folder must exist inside the vault"}, 2)
        rel = folder.relative_to(vault_root).as_posix()
        target = "." if rel == "." else rel

        def _in_scope(file_rel: str) -> bool:
            label = _folder_label_of(file_rel)
            if label is None:
                return True  # layout/identity findings are vault-global
            if target == "." or label == target:
                return True
            # ancestors of the target + its whole subtree
            return (label == "." or target.startswith(label + "/")
                    or label.startswith(target + "/"))

        findings = [f for f in findings if _in_scope(f.file)]
    findings = sort_findings(findings)
    hist = histogram(findings)
    errors = int(hist["by_severity"]["error"])
    warnings = int(hist["by_severity"]["warning"])
    gate = errors > 0 or (bool(args.strict) and warnings > 0)
    envelope: dict[str, Any] = {
        "action": "validated",
        "vault_root": str(vault_root),
        "files_checked": files_checked,
        "ok": errors == 0,
        "strict": bool(args.strict),
        **hist,
    }
    if args.json_sidecar:
        sidecar = Path(args.json_sidecar)
        atomic_write_text(
            sidecar,
            json.dumps([f.to_json() for f in findings], ensure_ascii=False, indent=2),
        )
        envelope["json_sidecar"] = str(sidecar)
    report_path = _maybe_report(args, render_findings_report(findings, str(vault_root)))
    if report_path:
        envelope["report"] = report_path
    return emit(envelope, 6 if gate else 0)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="wiki-config",
        description=(
            "Inspect per-folder `.wiki/sync.yaml` config: effective values, "
            "per-key inheritance provenance, and the vault-wide override map. "
            "NOT the vault identity config (WIKI_SCHEMA.md / "
            "config/wiki-config.schema.yaml) — use wiki-init for that."
        ),
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    show = sub.add_parser(
        "show",
        help="effective config + per-key provenance for one folder",
    )
    show.add_argument("folder", help="vault-relative (or absolute) folder; '.' = vault root")
    show.add_argument("--vault-root", default=None,
                      help="vault root (default: walk up from CWD to WIKI_SCHEMA.md)")
    show.add_argument("--report", default=None,
                      help="also write a human-readable markdown report to this path")
    show.set_defaults(func=_cmd_show)

    tree = sub.add_parser(
        "tree",
        help="whole-vault override map (which folder defines/overrides/ignores what)",
    )
    tree.add_argument("--vault-root", default=None,
                      help="vault root (default: walk up from CWD to WIKI_SCHEMA.md)")
    tree.add_argument("--report", default=None,
                      help="also write a human-readable markdown report to this path")
    tree.set_defaults(func=_cmd_tree)

    validate = sub.add_parser(
        "validate",
        help="all-findings lint over every config file in the vault "
             "(sync.yaml tree + layout.yaml + WIKI_SCHEMA.md/.wiki.yaml)",
    )
    validate.add_argument("folder", nargs="?", default=None,
                          help="optional folder: narrow sync findings to its "
                               "subtree + ancestor chain")
    validate.add_argument("--vault-root", default=None,
                          help="vault root (default: walk up from CWD)")
    validate.add_argument("--strict", action="store_true",
                          help="also gate (exit 6) on warning-severity findings")
    validate.add_argument("--json-sidecar", default=None,
                          help="write the full findings array (JSON) to this path")
    validate.add_argument("--report", default=None,
                          help="also write a grouped markdown report to this path")
    validate.set_defaults(func=_cmd_validate)

    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":  # pragma: no cover
    import sys

    sys.exit(main())
