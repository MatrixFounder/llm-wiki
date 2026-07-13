"""TASK 058 — human-readable markdown sidecars for `wiki-config` (`--report`).

Stdout stays the one-line JSON envelope (repo contract); operators get readable
tables here (wiki-lint `--report` precedent). Everything interpolated from the
vault is data: folder labels come from our own walk (`relative_to().as_posix()`),
values are rendered through a compact JSON dump — never raw text from files.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ._provenance import FolderProvenance, TreeNode, resolve_origin
from ._uimodel import build_ui_model, resolve_description


def _fmt_value(value: Any) -> str:
    """Compact single-line cell rendering; pipes escaped for md tables."""
    out = json.dumps(value, ensure_ascii=False)
    if len(out) > 60:
        out = out[:57] + "..."
    return out.replace("|", "\\|")


def _flatten(effective: Any, pointer: str, out: list[tuple[str, Any]]) -> None:
    if isinstance(effective, dict):
        for key, child in effective.items():
            _flatten(child, f"{pointer}/{key}", out)
        return
    out.append((pointer, effective))


def render_show_report(prov: FolderProvenance, vault_root: Path) -> str:
    lines: list[str] = [
        f"# wiki-config show — `{prov.folder}`",
        "",
        f"Vault: `{vault_root}`",
        "",
        "| key | value | origin | shadows |",
        "|---|---|---|---|",
    ]
    rows: list[tuple[str, Any]] = []
    for key, block in prov.effective.items():
        _flatten(block, f"/{key}", rows)
    for pointer, value in rows:
        # A nested pointer with no own origin entry (e.g. the leaves of a
        # configured root-only block like /transcript_dedup/enabled) inherits
        # the NEAREST ancestor pointer's origin instead of rendering blank.
        origin = resolve_origin(prov.origins, pointer)
        origin_label = origin.origin if origin else ""
        if origin and origin.scope == "root-only":
            origin_label += " (root-only)"
        shadows = ", ".join(origin.shadows) if origin and origin.shadows else ""
        lines.append(
            f"| `{pointer}` | {_fmt_value(value)} | {origin_label} | {shadows} |"
        )
    # TASK 061 / R-061-6 — what each key MEANS, from the schema (`zones:` says
    # ADVISORY here too). A SECTION, not a 5th table column: `_fmt_value` clips
    # cells at 60 chars, and a truncated advisory ("ADVISORY — not enfor...") is
    # a lossy render of an honesty fix — the same disease one layer down.
    # Per-row (not per-schema-key) so the list is a direct lookup for the table
    # above, nearest-ancestor resolved for pointers outside the model.
    model = build_ui_model()
    described = [(ptr, resolve_description(model, ptr)) for ptr, _ in rows]
    described = [(ptr, text) for ptr, text in described if text]
    if described:
        lines += ["", "## What these keys mean", ""]
        lines += [f"- `{ptr}` — {text}" for ptr, text in described]
    if prov.levels:
        lines += ["", "## Configured levels", ""]
        for lvl in prov.levels:
            lines.append(f"- `{lvl.file}` — defines {len(lvl.defines)} key(s)"
                         + (f", **ignores {len(lvl.ignored)}**" if lvl.ignored else ""))
    for warning in prov.warnings:
        keys = ", ".join(f"`{k}`" for k in warning.get("keys", []))
        lines += ["", f"> ⚠ **{warning['code']}** at `{warning['level']}`: {keys} — "
                      f"{warning.get('hint', '')}"]
    return "\n".join(lines) + "\n"


def render_tree_report(nodes: list[TreeNode], vault_root: Path) -> str:
    lines: list[str] = [
        "# wiki-config tree",
        "",
        f"Vault: `{vault_root}` — {len(nodes)} configured folder(s)",
        "",
    ]
    for node in nodes:
        lines.append(f"## `{node.folder}`")
        if node.error:
            lines.append(f"- **ERROR** `{node.error.get('code', '')}` "
                         f"({node.error.get('reason', '')}): {node.error.get('detail', '')}")
            lines.append("")
            continue
        for pointer, scope in node.defines.items():
            row = f"- `{pointer}` ({scope})"
            deeper = node.overridden_by.get(pointer)
            if deeper:
                row += " — overridden by " + ", ".join(f"`{d}`" for d in deeper)
            lines.append(row)
        for key in node.ignored:
            lines.append(f"- ⚠ `{key}` — **ignored here** (root-only key in a subfolder)")
        if not node.defines and not node.ignored:
            lines.append("- (empty config)")
        lines.append("")
    return "\n".join(lines) + "\n"
