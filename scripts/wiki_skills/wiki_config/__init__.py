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

from ._backups import list_backups, restore_backup, write_backup
from ._doctor import apply_plans, build_plans, render_fix_report
from ._edit import EditDowngrade, PointerEdit, rewrite_text
from ._findings import (
    ConfigFinding,
    TAXONOMY,
    histogram,
    render_findings_report,
    sort_findings,
)
from ._lint import lint_vault
from ._templates import (
    TemplateError,
    discover_templates,
    render_for_init,
    top_level_blocks,
)
from ._uimodel import SCOPE_ROOT_ONLY, build_ui_model
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


def _cmd_doctor(args: argparse.Namespace) -> int:
    vault_root = _resolve_vault_root(args)
    if vault_root is None:
        return emit({"error": "VAULT_ROOT_NOT_FOUND",
                     "hint": "pass --vault-root or run inside a vault"}, 2)
    findings, files_checked = lint_vault(vault_root)
    findings = sort_findings(findings)
    plans, manual = build_plans(findings, vault_root)
    envelope: dict[str, Any] = {
        "action": "doctored",
        "vault_root": str(vault_root),
        "files_checked": files_checked,
        "plans": [p.to_json() for p in plans],
        "manual": [f.to_json() for f in manual],
        **histogram(findings),
    }
    report_path = _maybe_report(
        args, render_fix_report(plans, manual, [], str(vault_root)))
    if report_path:
        envelope["report"] = report_path
    return emit(envelope)


def _cmd_fix(args: argparse.Namespace) -> int:
    import json

    vault_root = _resolve_vault_root(args)
    if vault_root is None:
        return emit({"error": "VAULT_ROOT_NOT_FOUND",
                     "hint": "pass --vault-root or run inside a vault"}, 2)
    expected_hashes: dict[str, str] | None = None
    if args.from_plan:
        try:
            sidecar = json.loads(Path(args.from_plan).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return emit({"error": "PLAN_UNREADABLE", "field": "from-plan"}, 2)
        findings = [
            ConfigFinding(
                code=str(e.get("code", "")), system=str(e.get("system", "sync")),
                file=str(e.get("file", "")), pointer=str(e.get("pointer", "")),
                message=str(e.get("message", "")),
                data=dict(e.get("data") or {}),
                file_hash=e.get("file_hash"),
            )
            for e in sidecar
            if isinstance(e, dict) and str(e.get("code", "")) in TAXONOMY
        ]
        expected_hashes = {
            f.file: f.file_hash for f in findings
            if f.file_hash and f.system == "sync" and f.kind.tier != "manual"
        }
    else:
        findings, _checked = lint_vault(vault_root)
        findings = sort_findings(findings)
    plans, manual = build_plans(findings, vault_root)
    results, diffs, exit_code = apply_plans(
        vault_root, plans,
        yes=bool(args.yes), dry_run=bool(args.dry_run),
        no_backup=bool(args.no_backup), expected_hashes=expected_hashes,
    )
    if expected_hashes is not None and any(r.status == "drifted" for r in results):
        drifted = next(r for r in results if r.status == "drifted")
        return emit({"error": "CONFIG_DRIFTED", "file": drifted.file,
                     "hint": "the file changed since the plan was made — re-run "
                             "doctor and fix from a fresh plan"}, 2)
    envelope: dict[str, Any] = {
        "action": "fixed",
        "vault_root": str(vault_root),
        "dry_run": bool(args.dry_run),
        "files": [r.to_json() for r in results],
        "manual": [f.code for f in manual],
    }
    report_path = _maybe_report(
        args, render_fix_report(plans, manual, diffs, str(vault_root)))
    if report_path:
        envelope["report"] = report_path
    return emit(envelope, 0 if args.dry_run else exit_code)


def _cmd_restore(args: argparse.Namespace) -> int:
    vault_root = _resolve_vault_root(args)
    if vault_root is None:
        return emit({"error": "VAULT_ROOT_NOT_FOUND",
                     "hint": "pass --vault-root or run inside a vault"}, 2)
    folder = _resolve_folder(args.folder, vault_root)
    if folder is None:
        return emit({"error": "FOLDER_NOT_FOUND", "field": "folder"}, 2)
    entries = list_backups(folder)
    if args.list:
        return emit({"action": "backups",
                     "folder": args.folder,
                     "backups": [e.__dict__ for e in entries]})
    if not entries:
        return emit({"error": "NO_BACKUPS", "folder": args.folder}, 2)
    if args.to:
        matches = [e for e in entries if args.to in e.name]
        if len(matches) != 1:
            return emit({"error": "BACKUP_NOT_FOUND" if not matches
                         else "BACKUP_AMBIGUOUS", "field": "to",
                         "candidates": [e.name for e in matches][:5]}, 2)
        target = matches[0]
    else:
        target = entries[0]
    if not args.yes:
        return emit({"action": "restore-plan", "folder": args.folder,
                     "would_restore": target.name,
                     "hint": "re-run with --yes to overwrite the live sync.yaml "
                             "(the current file is backed up first)"}, 7)
    try:
        restored_from, backup_of_current = restore_backup(folder, target.name)
    except (FileNotFoundError, ValueError, OSError):
        return emit({"error": "RESTORE_FAILED", "folder": args.folder}, 5)
    from scripts.wiki_index.sync_config import _load_validated_raw

    valid = True
    try:
        _load_validated_raw(folder)
    except SyncConfigError:
        valid = False
    return emit({"action": "restored", "folder": args.folder,
                 "restored_from": restored_from,
                 "backup_of_current": backup_of_current,
                 "restored_file_valid": valid})


def _parse_cli_value(text: str) -> tuple[Any, bool]:
    """CLI value → YAML scalar or flat list of scalars. Returns (value, ok)."""
    import yaml as _yaml

    try:
        value = _yaml.safe_load(text)
    except _yaml.YAMLError:
        return None, False
    if isinstance(value, dict):
        return None, False
    if isinstance(value, list) and any(isinstance(i, (dict, list)) for i in value):
        return None, False
    return value, True


def _apply_single_edit(
    vault_root: Path, folder: Path, folder_arg: str, edit: PointerEdit,
    *, no_backup: bool,
) -> int:
    """Shared set/unset write path: sandwich + backup + TOCTOU + atomic write."""
    target = folder / ".wiki" / "sync.yaml"
    wiki_dir = folder / ".wiki"
    if wiki_dir.exists() and (wiki_dir.is_symlink() or not wiki_dir.is_dir()):
        return emit({"error": "WIKI_DIR_INVALID", "folder": folder_arg,
                     "hint": ".wiki exists but is not a plain directory"}, 2)
    existed = target.is_file()
    if existed and target.is_symlink():
        return emit({"error": "SYMLINK_REFUSED", "folder": folder_arg}, 2)
    before = target.read_text(encoding="utf-8") if existed else ""
    try:
        after = rewrite_text(before, [edit])
    except SyncConfigError as exc:
        return emit({"error": exc.code, "field": "sync-config",
                     "reason": exc.reason, "detail": exc.detail,
                     "hint": "the CURRENT file fails its gate — run "
                             "wiki-config doctor first"}, 6)
    except EditDowngrade as exc:
        code = 2 if "not present" in exc.detail else 6
        return emit({"error": "EDIT_REFUSED", "detail": exc.detail}, code)
    backup = None
    if existed and not no_backup:
        backup = write_backup(folder)
    if existed and target.read_text(encoding="utf-8") != before:
        return emit({"error": "CONFIG_DRIFTED", "folder": folder_arg}, 2)
    wiki_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(target, after)
    rel = target.relative_to(vault_root).as_posix()
    return emit({"action": edit.op, "file": rel, "pointer": edit.pointer,
                 "backup": backup})


def _cmd_report(args: argparse.Namespace) -> int:
    from ._report import build_report_model, render_html

    vault_root = _resolve_vault_root(args)
    if vault_root is None:
        return emit({"error": "VAULT_ROOT_NOT_FOUND"}, 2)
    findings, _checked = lint_vault(vault_root)
    model = build_report_model(vault_root, sort_findings(findings),
                               all_folders=bool(args.all_folders))
    out = Path(args.out) if args.out else vault_root / ".wiki" / "config-report.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(out, render_html(model))
    envelope: dict[str, Any] = {
        "action": "reported", "vault_root": str(vault_root), "out": str(out),
        "folders": len(model.folders),
        "errors": model.errors, "warnings": model.warnings,
    }
    if args.md:
        from ._report_md import render_tree_report

        from scripts.wiki_skills._common import wrap_auto_block

        md_body = render_tree_report(scan_tree(vault_root), vault_root)
        atomic_write_text(Path(args.md),
                          wrap_auto_block("config-overview", md_body.rstrip()) + "\n")
        envelope["md"] = args.md
    if args.open:
        import webbrowser

        webbrowser.open(out.resolve().as_uri())
        envelope["opened"] = True
    return emit(envelope)


def _cmd_templates(args: argparse.Namespace) -> int:
    vault_root = _resolve_vault_root(args)  # optional for listing builtins
    registry = discover_templates(vault_root)
    return emit({"action": "templates",
                 "templates": [t.to_json() for t in registry.values()]})


def _parse_vars(pairs: list[str] | None) -> dict[str, str] | None:
    out: dict[str, str] = {}
    for pair in pairs or []:
        if "=" not in pair:
            return None
        key, _, value = pair.partition("=")
        out[key.strip()] = value
    return out


def _cmd_init(args: argparse.Namespace) -> int:
    from scripts.wiki_index.config_loader import deep_merge

    from ._edit import gate_text

    vault_root = _resolve_vault_root(args)
    if vault_root is None:
        return emit({"error": "VAULT_ROOT_NOT_FOUND"}, 2)
    folder = _resolve_folder(args.folder, vault_root)
    if folder is None:
        return emit({"error": "FOLDER_NOT_FOUND", "field": "folder"}, 2)
    registry = discover_templates(vault_root)
    template = registry.get(args.template)
    if template is None or not template.valid:
        return emit({"error": "TEMPLATE_NOT_FOUND" if template is None
                     else "TEMPLATE_INVALID",
                     "field": "template",
                     "available": sorted(n for n, t in registry.items() if t.valid)},
                    1)
    is_root = folder.resolve() == vault_root.resolve()
    if template.level == "root" and not is_root:
        return emit({"error": "TEMPLATE_LEVEL_MISMATCH",
                     "template": template.name,
                     "hint": "this template carries ROOT-ONLY keys that a "
                             "subfolder file silently ignores — init it at the "
                             "vault root ('.')"}, 2)
    supplied = _parse_vars(args.var)
    if supplied is None:
        return emit({"error": "INVALID_VAR", "field": "var",
                     "hint": "use --var name=value"}, 2)
    try:
        rendered = render_for_init(template, supplied)
        gate_text(rendered)  # a template bug / hostile var never reaches disk
    except TemplateError as exc:
        code = 6 if exc.code == "INVALID_TEMPLATE_VAR" else 2
        return emit({"error": exc.code, **exc.data}, code)
    except SyncConfigError as exc:
        return emit({"error": "TEMPLATE_RENDER_INVALID", "reason": exc.reason,
                     "detail": exc.detail}, 6)

    wiki_dir = folder / ".wiki"
    if wiki_dir.exists() and (wiki_dir.is_symlink() or not wiki_dir.is_dir()):
        return emit({"error": "WIKI_DIR_INVALID", "folder": args.folder}, 2)
    target = wiki_dir / "sync.yaml"
    note = ("subfolder template applied at the vault root (level 0 of the "
            "cascade — it becomes the vault default)"
            if template.level == "subfolder" and is_root else None)
    backup = None
    mode = "create"

    if target.is_file():
        if target.is_symlink():
            return emit({"error": "SYMLINK_REFUSED", "folder": args.folder}, 2)
        existing = target.read_text(encoding="utf-8")
        if args.force:
            mode = "force"
            if not args.no_backup:
                backup = write_backup(folder)
            final = rendered
        elif args.merge:
            mode = "merge"
            try:
                existing_raw = gate_text(existing)
            except SyncConfigError as exc:
                return emit({"error": exc.code, "reason": exc.reason,
                             "detail": exc.detail,
                             "hint": "the existing file fails its gate — run "
                                     "wiki-config doctor first"}, 6)
            rendered_raw = gate_text(rendered)
            blocks = top_level_blocks(rendered)
            missing = [k for k in rendered_raw if k not in existing_raw]
            if not missing:
                return emit({"action": "initialized", "mode": "merge",
                             "file": str(target.relative_to(vault_root)),
                             "merged_blocks": [],
                             "note": "existing file already covers every "
                                     "template block — nothing to merge"})
            appended = "".join(blocks[k] for k in missing if k in blocks)
            base = existing if existing.endswith("\n") else existing + "\n"
            final = base + "\n" + appended
            # planned semantics: template as BASE, existing wins wholesale —
            # only whole missing top-level blocks are added.
            planned = deep_merge({k: rendered_raw[k] for k in missing},
                                 existing_raw)
            try:
                verified = gate_text(final) == planned
            except SyncConfigError:
                verified = False
            if not verified:
                return emit({"error": "MERGE_UNVERIFIABLE",
                             "hint": "append-only merge could not be proven "
                                     "equivalent — apply the missing blocks by "
                                     "hand from the template file"}, 6)
            merged_blocks = missing
            if not args.no_backup:
                backup = write_backup(folder)
        else:
            return emit({"action": "init-plan", "error": "CONFIG_EXISTS",
                         "file": str(target.relative_to(vault_root)),
                         "hint": "re-run with --merge (append only the blocks "
                                 "the file lacks; existing keys win) or "
                                 "--force (replace, with backup)"}, 7)
    else:
        final = rendered
        wiki_dir.mkdir(parents=True, exist_ok=True)

    atomic_write_text(target, final)
    envelope: dict[str, Any] = {
        "action": "initialized", "mode": mode,
        "file": str(target.relative_to(vault_root)),
        "template": template.name, "version": template.version,
        "backup": backup,
    }
    if mode == "merge":
        envelope["merged_blocks"] = merged_blocks
    if note:
        envelope["note"] = note
    return emit(envelope)


def _cmd_set(args: argparse.Namespace) -> int:
    vault_root = _resolve_vault_root(args)
    if vault_root is None:
        return emit({"error": "VAULT_ROOT_NOT_FOUND"}, 2)
    folder = _resolve_folder(args.folder, vault_root)
    if folder is None:
        return emit({"error": "FOLDER_NOT_FOUND", "field": "folder"}, 2)
    model = build_ui_model()
    if args.pointer not in model:
        import difflib

        close = difflib.get_close_matches(args.pointer, list(model), 3, 0.4)
        return emit({"error": "UNKNOWN_POINTER", "field": "pointer",
                     "did_you_mean": close}, 2)
    top = "/" + args.pointer.lstrip("/").split("/")[0]
    spec = model[top]
    if spec.scope == SCOPE_ROOT_ONLY and folder.resolve() != vault_root.resolve():
        return emit({"error": "SCOPE_ROOT_ONLY", "pointer": args.pointer,
                     "hint": f"'{top.lstrip('/')}' is consumed ONLY from the "
                             "vault-root sync.yaml — set it there (wiki-config "
                             "set . ...), a subfolder copy is silently ignored"}, 2)
    value, ok = _parse_cli_value(args.value)
    if not ok:
        return emit({"error": "INVALID_VALUE", "field": "value",
                     "hint": "pass a YAML scalar or a flat list of scalars"}, 2)
    return _apply_single_edit(vault_root, folder, args.folder,
                              PointerEdit("set", args.pointer, value),
                              no_backup=bool(args.no_backup))


def _cmd_unset(args: argparse.Namespace) -> int:
    vault_root = _resolve_vault_root(args)
    if vault_root is None:
        return emit({"error": "VAULT_ROOT_NOT_FOUND"}, 2)
    folder = _resolve_folder(args.folder, vault_root)
    if folder is None:
        return emit({"error": "FOLDER_NOT_FOUND", "field": "folder"}, 2)
    if not (folder / ".wiki" / "sync.yaml").is_file():
        return emit({"error": "NO_CONFIG", "folder": args.folder}, 2)
    return _apply_single_edit(vault_root, folder, args.folder,
                              PointerEdit("unset", args.pointer),
                              no_backup=bool(args.no_backup))


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

    doctor = sub.add_parser(
        "doctor",
        help="validate + a tiered repair PLAN (read-only; diffs via --report)",
    )
    doctor.add_argument("--vault-root", default=None)
    doctor.add_argument("--report", default=None,
                        help="write plans + manual findings as markdown")
    doctor.set_defaults(func=_cmd_doctor)

    fix = sub.add_parser(
        "fix",
        help="apply repair plans: SAFE tier always, CONFIRM tier with --yes "
             "(without --yes: safe applied, confirm listed, exit 7)",
    )
    fix.add_argument("--vault-root", default=None)
    fix.add_argument("--from-plan", default=None,
                     help="a validate --json-sidecar file; enables the "
                          "all-or-nothing hash drift pre-check (CONFIG_DRIFTED)")
    fix.add_argument("--yes", action="store_true",
                     help="also apply confirm-tier fixes")
    fix.add_argument("--dry-run", action="store_true",
                     help="plan only, write nothing, exit 0")
    fix.add_argument("--no-backup", action="store_true",
                     help="skip the .wiki/backups/ copy before writes")
    fix.add_argument("--report", default=None,
                     help="write plans + applied unified diffs as markdown")
    fix.set_defaults(func=_cmd_fix)

    restore = sub.add_parser(
        "restore",
        help="restore a folder's sync.yaml from .wiki/backups/ "
             "(reversible: the current file is backed up first)",
    )
    restore.add_argument("folder")
    restore.add_argument("--vault-root", default=None)
    restore.add_argument("--list", action="store_true",
                         help="list available backups, restore nothing")
    restore.add_argument("--to", default=None,
                         help="a backup name or unique timestamp fragment "
                              "(default: the newest backup)")
    restore.add_argument("--yes", action="store_true",
                         help="actually overwrite (without it: plan + exit 7)")
    restore.set_defaults(func=_cmd_restore)

    set_cmd = sub.add_parser(
        "set",
        help="set one key by JSON pointer (comment-preserving; schema-gated; "
             "refuses a root-only key in a subfolder)",
    )
    set_cmd.add_argument("folder", help="'.' = vault root")
    set_cmd.add_argument("pointer", help="e.g. /summarize/profile")
    set_cmd.add_argument("value", help="YAML scalar or flat list, e.g. meeting")
    set_cmd.add_argument("--vault-root", default=None)
    set_cmd.add_argument("--no-backup", action="store_true")
    set_cmd.set_defaults(func=_cmd_set)

    unset_cmd = sub.add_parser(
        "unset",
        help="remove one key by JSON pointer (comment-preserving where possible)",
    )
    unset_cmd.add_argument("folder")
    unset_cmd.add_argument("pointer")
    unset_cmd.add_argument("--vault-root", default=None)
    unset_cmd.add_argument("--no-backup", action="store_true")
    unset_cmd.set_defaults(func=_cmd_unset)

    init = sub.add_parser(
        "init",
        help="set a folder up from a named template (templates/sync-profiles/ "
             "+ <vault>/.wiki/templates/)",
    )
    init.add_argument("folder", help="'.' = vault root")
    init.add_argument("--template", required=True)
    init.add_argument("--var", action="append", default=None, metavar="NAME=VALUE",
                      help="template variable (repeatable); regex vars are "
                           "ReDoS-gated")
    mode_group = init.add_mutually_exclusive_group()
    mode_group.add_argument("--merge", action="store_true",
                            help="existing file: append only the top-level "
                                 "blocks it lacks (existing keys win)")
    mode_group.add_argument("--force", action="store_true",
                            help="existing file: replace it (backup taken)")
    init.add_argument("--no-backup", action="store_true")
    init.add_argument("--vault-root", default=None)
    init.set_defaults(func=_cmd_init)

    templates = sub.add_parser(
        "templates",
        help="list available sync.yaml templates (builtin + vault)",
    )
    templates.add_argument("--vault-root", default=None)
    templates.set_defaults(func=_cmd_templates)

    report = sub.add_parser(
        "report",
        help="render ONE self-contained HTML report: folder tree + per-key "
             "inheritance badges + findings with copy-paste fix commands",
    )
    report.add_argument("--vault-root", default=None)
    report.add_argument("--out", default=None,
                        help="output path (default <vault>/.wiki/config-report.html)")
    report.add_argument("--open", action="store_true",
                        help="open the report in the default browser")
    report.add_argument("--all-folders", action="store_true",
                        help="include unconfigured folders too (capped)")
    report.add_argument("--md", default=None,
                        help="also write a markdown overview (AUTO-block wrapped) "
                             "to this vault-visible path for viewing in Obsidian")
    report.set_defaults(func=_cmd_report)

    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":  # pragma: no cover
    import sys

    sys.exit(main())
