"""TASK 058 — the self-contained HTML config report (`wiki-config report`).

ONE static file: inline CSS/JS, CSP `default-src 'none'` (no network fetch is
possible even if a folder name smuggles a URL), no CDN, dark/light via
`prefers-color-scheme`. Works with JS disabled (native <details>); the ~90
lines of vanilla JS only add filter / expand-collapse-all / copy buttons.

Every interpolated string is UNTRUSTED: `html.escape` on all of them (folder
names carry Cyrillic/spaces/quotes in real vaults), NFC-normalized for display,
`shlex.quote` when composing suggested shell commands. Deterministic output
(NO timestamp; stable casefold ordering) → snapshot-testable, clean re-render
diffs on iCloud.

The content is 100% derived from the UI model + provenance engine + linter —
a new schema field shows up here with zero changes to this module (R-058-10).
"""

from __future__ import annotations

import html
import json
import shlex
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scripts.wiki_index.sync_config import SyncConfigError

from ._findings import ConfigFinding
from ._provenance import compute_folder_provenance, resolve_origin, scan_tree
from ._report_md import _flatten
from ._uimodel import build_ui_model, resolve_description

_MAX_NODES = 5000


@dataclass
class FolderSection:
    label: str  # "." for root
    status: str = "ok"  # ok | invalid | unreadable
    has_config: bool = False  # this folder carries its own .wiki/sync.yaml
    error_detail: str = ""
    rows: list[dict[str, Any]] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)
    commands: list[tuple[str, str]] = field(default_factory=list)  # (title, cmd)


@dataclass
class ReportModel:
    vault_root: str
    folders: list[FolderSection] = field(default_factory=list)
    errors: int = 0
    warnings: int = 0
    truncated: bool = False


def build_report_model(
    vault_root: Path,
    findings: list[ConfigFinding],
    *,
    all_folders: bool = False,
) -> ReportModel:
    """The configured spine (folders that HAVE a sync.yaml, root always) with
    per-key provenance rows + that folder's findings + copy-paste commands."""
    model = ReportModel(vault_root=str(vault_root))
    by_file: dict[str, list[ConfigFinding]] = {}
    for finding in findings:
        by_file.setdefault(finding.file, []).append(finding)
        if finding.kind.severity == "error":
            model.errors += 1
        elif finding.kind.severity == "warning":
            model.warnings += 1

    # The configured spine: folders that HAVE a sync.yaml, plus all their
    # ANCESTORS (so the nav reads as a hierarchy, not disjoint leaves), plus
    # the root. Unconfigured siblings stay hidden unless --all-folders.
    labels = {n.folder for n in scan_tree(vault_root)}
    for label in list(labels):
        parts = label.split("/")
        for i in range(1, len(parts)):
            labels.add("/".join(parts[:i]))
    labels.add(".")
    if all_folders:
        import os

        count = 0
        for dirpath, dirnames, _files in os.walk(vault_root, followlinks=False):
            dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
            rel = Path(dirpath).relative_to(vault_root).as_posix()
            labels.add("." if rel == "." else rel)
            count += 1
            if count >= _MAX_NODES:
                model.truncated = True
                break

    root_arg = shlex.quote(str(vault_root))
    # ONE schema parse (not one per folder) + one memo of loaded ancestor
    # raws (the vault root, above all, would otherwise reload once per row).
    ui_model = build_ui_model()
    raw_cache: dict[Path, dict[str, Any] | SyncConfigError] = {}
    for label in sorted(labels, key=str.casefold):
        section = FolderSection(label=label)
        folder = vault_root if label == "." else vault_root / label
        section.has_config = (folder / ".wiki" / "sync.yaml").is_file()
        try:
            prov = compute_folder_provenance(
                folder, vault_root, model=ui_model, raw_cache=raw_cache)
            rows: list[tuple[str, Any]] = []
            for key, block in prov.effective.items():
                _flatten(block, f"/{key}", rows)
            for pointer, value in rows:
                # A nested pointer with no own origin entry (e.g. the leaves of
                # a root-only block like /transcript_dedup/enabled) inherits
                # the NEAREST ancestor pointer's origin — otherwise it renders
                # as an anonymous inherited badge (real-vault dogfood bug).
                origin = resolve_origin(prov.origins, pointer)
                section.rows.append({
                    "pointer": pointer,
                    "value": json.dumps(value, ensure_ascii=False),
                    "origin": origin.origin if origin else "",
                    "scope": origin.scope if origin else "",
                    "shadows": list(origin.shadows) if origin else [],
                    # TASK 061 / R-061-6 — what the key MEANS, from the schema.
                    # NEAREST-ANCESTOR resolved (the `resolve_origin` line above
                    # is the precedent): a row pointer outside the model must
                    # inherit, not silently render "".
                    "description": resolve_description(ui_model, pointer),
                })
        except SyncConfigError as exc:
            section.status = "invalid"
            section.error_detail = exc.detail
        file_rel = ".wiki/sync.yaml" if label == "." else f"{label}/.wiki/sync.yaml"
        for finding in by_file.get(file_rel, []):
            section.findings.append(finding.to_json())
            if finding.code == "UNREADABLE":
                section.status = "unreadable"
        folder_arg = shlex.quote(label)
        section.commands = [
            ("Show provenance",
             f"wiki-config show {folder_arg} --vault-root {root_arg}"),
            ("Validate this subtree",
             f"wiki-config validate {folder_arg} --vault-root {root_arg}"),
        ]
        if any(f["tier"] in ("safe", "confirm") for f in section.findings):
            section.commands.append(
                ("Repair (plan first)",
                 f"wiki-config fix --dry-run --vault-root {root_arg}"))
        if section.status == "ok" and not section.has_config:
            section.commands.append(
                ("Quick setup from a template",
                 f"wiki-config init {folder_arg} --template meeting-zone "
                 f"--vault-root {root_arg}"))
        model.folders.append(section)
    return model


# --------------------------------------------------------------------------- #
# rendering
# --------------------------------------------------------------------------- #


def _esc(value: str) -> str:
    """Text-node escaping (&, <, > — quotes are inert in text content)."""
    return html.escape(unicodedata.normalize("NFC", value), quote=False)


def _esc_attr(value: str) -> str:
    """Attribute-value escaping (quotes included)."""
    return html.escape(unicodedata.normalize("NFC", value), quote=True)


def _anchor(label: str) -> str:
    import hashlib

    slug = "".join(ch if ch.isascii() and ch.isalnum() else "-" for ch in label)
    return f"f-{slug[:40]}-{hashlib.sha256(label.encode()).hexdigest()[:8]}"


_BADGE_CLASS = {
    "default": "b-default",
    "root": "b-root",
}

_CSS = """
:root{--bg:#fff;--fg:#0a0a0a;--muted:#6b7280;--card:#f8f9fb;--line:#e5e7eb;
--accent:#2563eb;--ok:#16a34a;--warn:#d97706;--err:#dc2626;--here:#16a34a;
--inh:#0d9488;--ign:#dc2626;--rootb:#2563eb;--def:#6b7280;
font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}
@media (prefers-color-scheme:dark){:root{--bg:#0b0e14;--fg:#e6e8ee;
--muted:#9aa4b2;--card:#131722;--line:#232a38}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg)}
header{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);
padding:.8rem 1.2rem;display:flex;gap:1rem;align-items:center;flex-wrap:wrap;z-index:2}
header h1{font-size:1rem;margin:0}header .muted{color:var(--muted);font-size:.8rem}
input#filter{background:var(--card);color:var(--fg);border:1px solid var(--line);
border-radius:.5rem;padding:.35rem .6rem;min-width:14rem}
button{background:var(--card);color:var(--fg);border:1px solid var(--line);
border-radius:.5rem;padding:.3rem .7rem;cursor:pointer;font-size:.8rem}
main{display:grid;grid-template-columns:minmax(14rem,20rem) 1fr;gap:1rem;
padding:1rem 1.2rem;max-width:90rem;margin:0 auto}
nav{position:sticky;top:3.6rem;align-self:start;max-height:calc(100vh - 5rem);
overflow:auto;border:1px solid var(--line);border-radius:.7rem;padding:.5rem}
nav a{display:flex;justify-content:space-between;gap:.5rem;color:var(--fg);
text-decoration:none;padding:.25rem .5rem;border-radius:.4rem;font-size:.85rem}
nav a:hover{background:var(--card)}
section.folder{border:1px solid var(--line);border-radius:.7rem;margin:0 0 1rem;
background:var(--card);overflow-x:auto}
section.folder>details>summary{cursor:pointer;padding:.7rem 1rem;font-weight:600}
.body{padding:0 1rem 1rem}
table{border-collapse:collapse;width:100%;font-size:.83rem}
th,td{text-align:left;padding:.3rem .5rem;border-bottom:1px solid var(--line);
vertical-align:top}code,pre{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
pre.cmd{background:var(--bg);border:1px solid var(--line);border-radius:.5rem;
padding:.5rem .7rem;display:flex;justify-content:space-between;gap:.6rem;
align-items:center;white-space:pre-wrap;word-break:break-all;font-size:.78rem}
.badge{display:inline-block;border-radius:.6rem;padding:.05rem .5rem;
font-size:.72rem;font-weight:600;color:#fff;white-space:nowrap}
.b-default{background:var(--def)}.b-root{background:var(--rootb)}
.b-here{background:var(--here)}.b-inherited{background:var(--inh)}
.b-ignored{background:var(--ign)}
.chip{font-size:.72rem;border-radius:.6rem;padding:.05rem .5rem;font-weight:600}
.c-ok{color:var(--ok)}.c-invalid,.c-unreadable{color:var(--err)}
.f-error{color:var(--err)}.f-warning{color:var(--warn)}.f-info{color:var(--muted)}
.muted{color:var(--muted)}
p.hint{color:var(--muted);font-size:.75rem;margin:.15rem 0 0;max-width:34rem;
font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}
"""

_JS = """
const $=s=>document.querySelectorAll(s);
document.getElementById('filter').addEventListener('input',e=>{
  const q=e.target.value.toLowerCase();
  $('section.folder').forEach(s=>{s.style.display=
    s.dataset.label.toLowerCase().includes(q)?'':'none';});
  $('nav a').forEach(a=>{a.style.display=
    a.dataset.label.toLowerCase().includes(q)?'':'none';});
});
document.getElementById('expand').onclick=()=>$('section.folder details')
  .forEach(d=>d.open=true);
document.getElementById('collapse').onclick=()=>$('section.folder details')
  .forEach(d=>d.open=false);
$('pre.cmd button').forEach(b=>b.onclick=()=>{
  const t=b.previousElementSibling.textContent;
  if(navigator.clipboard&&navigator.clipboard.writeText)
    navigator.clipboard.writeText(t).then(()=>{b.textContent='✓';
      setTimeout(()=>b.textContent='copy',900);});
  else{const r=document.createRange();
    r.selectNodeContents(b.previousElementSibling);
    const sel=getSelection();sel.removeAllRanges();sel.addRange(r);}
});
"""


def _origin_badge(row: dict[str, Any], section_label: str) -> str:
    """default (built-in) / ROOT (root-only key) / HERE (defined at this level)
    / ↑ <ancestor> (inherited via the cascade, root included) / ⛔ IGNORED."""
    origin, scope = str(row["origin"]), str(row["scope"])
    if scope == "root-only":
        if origin == "default":
            return '<span class="badge b-default">default</span>'
        return '<span class="badge b-root">ROOT</span>'
    if origin == "default":
        return '<span class="badge b-default">default</span>'
    defined_here = origin == section_label or (
        section_label == "." and origin == "root")
    if defined_here:
        return '<span class="badge b-here">HERE</span>'
    return (f'<span class="badge b-inherited" '
            f'title="cascaded from an ancestor level">↑ {_esc(origin)}</span>')


def _row_html(row: dict[str, Any], section_label: str) -> str:
    badge = _origin_badge(row, section_label)
    shadows = ""
    if row["shadows"]:
        shadows = ('<span class="muted" title="levels this value overrides">'
                   + _esc(", ".join(str(s) for s in row["shadows"])) + "</span>")
    # The schema's own description, under the key — the `serve` editor renders
    # the SAME FieldSpec.description as a `.hint` (`_app_html.py`), so the two
    # surfaces now say the same thing from the same source. `.get` (not `[...]`)
    # keeps a hand-built row dict (tests, future callers) from raising.
    # `_esc`ed like everything else here: descriptions are repo-owned today, but
    # the XSS discipline of this module does not carve out exceptions.
    description = str(row.get("description") or "")
    hint = f'<p class="hint">{_esc(description)}</p>' if description else ""
    return ("<tr><td><code>" + _esc(str(row["pointer"])) + "</code>" + hint + "</td>"
            "<td><code>" + _esc(str(row["value"])) + "</code></td>"
            f"<td>{badge}</td><td>{shadows}</td></tr>")


def _section_html(section: FolderSection) -> str:
    anchor = _anchor(section.label)
    status_label = section.status if section.has_config or section.status != "ok" \
        else "inherited only"
    # `section.status` lands in an ATTRIBUTE (`class`), so it takes `_esc_attr`
    # (quote=True) like every other attribute here — `_esc` is quote=False and is
    # for TEXT nodes only. It is a closed set today (ok | invalid | unreadable), so
    # this is doctrine, not a live escape; the point of the doctrine is that the
    # NEXT status value does not have to be audited for it. Same shape as the
    # `f-{_esc_attr(severity)}` precedent below.
    chip = (f'<span class="chip c-{_esc_attr(section.status)}">'
            f'{_esc(status_label)}</span>')
    parts: list[str] = [
        f'<section class="folder" id="{anchor}" '
        f'data-label="{_esc_attr(section.label)}">',
        "<details open><summary>" + _esc(section.label) + f" {chip}</summary>",
        '<div class="body">',
    ]
    if section.status == "invalid":
        parts.append('<p class="f-error">config on this path fails its gate: '
                     + _esc(section.error_detail) + "</p>")
    if section.rows:
        parts.append("<table><thead><tr><th>key</th><th>value</th>"
                     "<th>origin</th><th>shadows</th></tr></thead><tbody>")
        parts += [_row_html(row, section.label) for row in section.rows]
        parts.append("</tbody></table>")
    if section.findings:
        parts.append("<h4>Findings</h4><ul>")
        for finding in section.findings:
            severity = str(finding.get("severity", "info"))
            pointer = str(finding.get("pointer") or "")
            parts.append(
                f'<li class="f-{_esc_attr(severity)}"><strong>'
                + _esc(str(finding.get("code", ""))) + "</strong>"
                + (f" <code>{_esc(pointer)}</code>" if pointer else "")
                + " — " + _esc(str(finding.get("message", ""))) + "</li>")
        parts.append("</ul>")
    if section.commands:
        parts.append("<h4>Commands</h4>")
        for title, cmd in section.commands:
            parts.append(f'<p class="muted">{_esc(title)}</p>'
                         f'<pre class="cmd"><span>{_esc(cmd)}</span>'
                         "<button>copy</button></pre>")
    parts.append("</div></details></section>")
    return "".join(parts)


def render_html(model: ReportModel) -> str:
    nav_items = []
    sections = []
    for section in model.folders:
        marks = ""
        if section.findings:
            worst = ("error" if any(f.get("severity") == "error"
                                    for f in section.findings)
                     else "warning" if any(f.get("severity") == "warning"
                                           for f in section.findings) else "info")
            marks = f'<span class="f-{worst}">⚠</span>'
        depth = 0 if section.label == "." else section.label.count("/") + 1
        name = section.label if depth <= 1 else section.label.rsplit("/", 1)[1]
        dot = "●" if section.has_config else '<span class="muted">○</span>'
        nav_items.append(
            f'<a href="#{_anchor(section.label)}" '
            f'style="padding-left:{0.5 + depth * 0.9:.1f}rem" '
            f'title="{_esc_attr(section.label)}" '
            f'data-label="{_esc_attr(section.label)}">'
            f"<span>{dot} {_esc(name)}</span>{marks}</a>")
        sections.append(_section_html(section))
    truncated = ('<p class="f-warning">tree truncated at '
                 f"{_MAX_NODES} folders</p>" if model.truncated else "")
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy"
 content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>wiki-config report</title><style>{_CSS}</style></head>
<body>
<header><h1>wiki-config report</h1>
<span class="muted">{_esc(model.vault_root)}</span>
<input id="filter" type="search" placeholder="filter folders…">
<button id="expand">expand all</button><button id="collapse">collapse all</button>
<span class="muted">errors: {model.errors} · warnings: {model.warnings}</span>
</header>
<main><nav>{"".join(nav_items)}</nav>
<div>{truncated}{"".join(sections)}</div></main>
<script>{_JS}</script></body></html>
"""
