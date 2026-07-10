"""TASK 058 — the `wiki-config serve` inline web app (ONE self-contained page).

Vanilla JS, zero deps, no build step (explicit user decision over React/shadcn).
The FORM is rendered generically from `GET /api/schema` (the UI-model projection
of the sync-config schema): enum → <select>, boolean → tri-state select
(inherit/true/false), string → input (regex fields get a live tester), array →
one-item-per-line textarea. Field hints come from the schema `description`;
inherited values render as placeholders with the origin badge and an
"override here / reset" control; root-only fields are disabled outside the
vault root. A new schema field appears here with ZERO edits (R-058-10).

Real-vault feedback rounds (2026-07-11):
  * field labels are LEAF key names + a nesting breadcrumb (full pointers
    overflowed onto inputs); sub-block headings; clamped expandable hints;
    sticky action bar; taller multi-line list fields.
  * the nav shows the FULL folder hierarchy — configured folders highlighted,
    unconfigured dimmed-but-clickable (open → inherited values, Save = "Create
    override here"); configured folders carry "✕ delete config".
  * the tree is COLLAPSIBLE per folder (chevrons + collapse/expand-all,
    state persisted in localStorage), and unsaved edits are PER-FOLDER:
    switching folders keeps them, red dots mark dirty folders (a collapsed
    ancestor inherits the dot), a header "Save all (N)" flushes everything,
    and closing the tab with pending edits warns first.

Kept as a Python module holding one string so mypy/pytest cover its wiring;
the page itself is served by `_server.py` under a strict CSP.
"""

from __future__ import annotations

APP_HTML = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>wiki-config</title>
<style>
:root{
  --bg:#f6f7f9;--panel:#fff;--fg:#0f172a;--muted:#64748b;--line:#e2e8f0;
  --line-soft:#eef2f6;--accent:#2563eb;--accent-soft:#eff6ff;--ok:#16a34a;
  --warn:#d97706;--err:#dc2626;--here:#16a34a;--inh:#0d9488;--rootb:#2563eb;
  --def:#94a3b8;--shadow:0 1px 2px rgba(15,23,42,.05),0 4px 16px rgba(15,23,42,.06);
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Inter,sans-serif;
}
@media (prefers-color-scheme:dark){:root{
  --bg:#0b0e14;--panel:#11151f;--fg:#e6e9f0;--muted:#8b95a7;--line:#232a38;
  --line-soft:#1a2130;--accent:#3b82f6;--accent-soft:#12203a;--def:#5b6472;
  --shadow:0 1px 2px rgba(0,0,0,.4),0 6px 20px rgba(0,0,0,.35);
}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font-size:15px}
code,.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}

header{position:sticky;top:0;z-index:5;background:var(--panel);
  border-bottom:1px solid var(--line);padding:.6rem 1.4rem;display:flex;
  gap:1rem;align-items:center;box-shadow:var(--shadow)}
header h1{font-size:.95rem;margin:0;letter-spacing:.01em}
header .vault{color:var(--muted);font-size:.78rem;overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap;max-width:30rem}
#saveAll{margin-left:auto}
#saveAll[hidden]{display:none}
#status{font-size:.82rem;font-weight:600}
#status.ok{color:var(--ok)}#status.err{color:var(--err)}

main{display:grid;grid-template-columns:minmax(15rem,20rem) 1fr;gap:1.1rem;
  padding:1.1rem 1.4rem;max-width:92rem;margin:0 auto}
@media (max-width:880px){main{grid-template-columns:1fr}nav{position:static;max-height:none}}

nav{position:sticky;top:3.6rem;align-self:start;max-height:calc(100vh - 5rem);
  overflow:auto;background:var(--panel);border:1px solid var(--line);
  border-radius:.8rem;padding:.45rem;box-shadow:var(--shadow)}
.navhead{display:flex;align-items:center;gap:.4rem;padding:.2rem .4rem .45rem}
.navhead .navtitle{font-size:.7rem;text-transform:uppercase;letter-spacing:.08em;
  color:var(--muted);flex:1}
.navrow{display:flex;align-items:stretch}
.navrow .chev{background:none;border:0;color:var(--muted);cursor:pointer;
  width:1.3rem;flex:0 0 1.3rem;padding:0;font-size:.7rem;border-radius:.35rem}
.navrow .chev:hover{background:var(--line-soft);color:var(--fg)}
.navrow .chev.leaf{visibility:hidden;cursor:default}
.navrow .item{display:flex;flex:1;min-width:0;justify-content:space-between;
  gap:.5rem;text-align:left;background:none;border:0;color:var(--fg);
  padding:.34rem .5rem;font-size:.85rem;border-radius:.5rem;cursor:pointer;
  align-items:center}
.navrow .item span.nm{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.navrow .item:hover{background:var(--line-soft)}
.navrow .item.active{background:var(--accent-soft);color:var(--accent);font-weight:600}
.navrow .item.dim span.nm{color:var(--muted);font-weight:400}
.navrow .item.active.dim span.nm{color:var(--accent)}
.cfgdot{color:var(--accent);font-size:.6rem;vertical-align:middle}
.pdot{color:var(--err);font-size:.72rem;font-weight:700}
.navnote{font-size:.7rem;color:var(--muted);padding:.35rem .6rem}

#panel{background:var(--panel);border:1px solid var(--line);
  border-radius:.8rem;box-shadow:var(--shadow);min-height:22rem;
  display:flex;flex-direction:column;overflow:hidden}
.panelhead{padding:.9rem 1.3rem .0rem}
.panelhead h2{margin:0 0 .35rem;font-size:1.05rem;overflow-wrap:anywhere}
.confignote{font-size:.78rem;color:var(--muted);margin:.1rem 0 .6rem;
  display:flex;gap:.7rem;align-items:center;flex-wrap:wrap}
.tabs{display:flex;gap:.2rem;border-bottom:1px solid var(--line)}
.tabs button{background:none;border:0;border-bottom:2px solid transparent;
  color:var(--muted);padding:.5rem .9rem;font-size:.88rem;cursor:pointer;font-weight:600}
.tabs button.active{color:var(--accent);border-bottom-color:var(--accent)}
.panelbody{padding:1rem 1.3rem 1.2rem;overflow-y:auto}

fieldset{border:1px solid var(--line);border-radius:.7rem;margin:0 0 1.1rem;
  padding:.4rem 1.1rem .6rem;background:var(--panel)}
legend{font-weight:700;font-size:.92rem;padding:0 .45rem}
legend .scope{font-weight:500;font-size:.72rem;color:var(--muted)}
.subhead{font-size:.72rem;text-transform:uppercase;letter-spacing:.07em;
  color:var(--muted);padding:.8rem 0 .15rem;border-bottom:1px dashed var(--line-soft)}

.field{display:grid;grid-template-columns:minmax(9.5rem,14rem) minmax(12rem,1fr) auto;
  gap:.2rem .9rem;align-items:center;padding:.55rem 0;
  border-bottom:1px solid var(--line-soft)}
.field:last-child{border-bottom:0}
.fl{min-width:0;display:flex;flex-direction:column;gap:.1rem;padding-top:.15rem}
.fname{font-family:ui-monospace,Menlo,monospace;font-size:.84rem;font-weight:600;
  overflow-wrap:anywhere}
.fpath{font-size:.68rem;color:var(--muted);overflow-wrap:anywhere}
.fc{min-width:0}
.fb{display:flex;gap:.45rem;align-items:center;justify-content:flex-end;white-space:nowrap}
.hint{grid-column:1/-1;margin:.05rem 0 0;font-size:.75rem;color:var(--muted);
  line-height:1.45;display:-webkit-box;-webkit-line-clamp:2;
  -webkit-box-orient:vertical;overflow:hidden;cursor:default}
.hint.expandable{cursor:pointer}
.hint.open{-webkit-line-clamp:unset}
@media (max-width:1100px){
  .field{grid-template-columns:1fr auto}
  .fc{grid-column:1/-1}
}

input,select,textarea{background:var(--bg);color:var(--fg);
  border:1px solid var(--line);border-radius:.5rem;padding:.42rem .6rem;
  font-size:.86rem;width:100%;transition:border-color .12s, box-shadow .12s}
input:focus,select:focus,textarea:focus{outline:none;border-color:var(--accent);
  box-shadow:0 0 0 3px color-mix(in srgb, var(--accent) 18%, transparent)}
input::placeholder,textarea::placeholder{color:var(--muted);opacity:.8}
input:disabled,select:disabled,textarea:disabled{opacity:.55;cursor:not-allowed}
textarea{font-family:ui-monospace,Menlo,monospace;min-height:3rem;resize:vertical}
.field textarea{min-height:9rem;overflow-y:auto}
#yamlText{min-height:24rem;white-space:pre;font-size:.83rem;line-height:1.5}

.badge{display:inline-block;border-radius:999px;padding:.13rem .6rem;
  font-size:.68rem;font-weight:700;letter-spacing:.02em;color:#fff;white-space:nowrap}
.b-default{background:var(--def)}.b-root{background:var(--rootb)}
.b-here{background:var(--here)}.b-inherited{background:var(--inh)}
.b-disabled{background:var(--err)}

button.small{background:var(--panel);border:1px solid var(--line);color:var(--fg);
  border-radius:.45rem;padding:.2rem .6rem;font-size:.73rem;cursor:pointer}
button.small:hover{border-color:var(--accent);color:var(--accent)}
button.small.danger:hover{border-color:var(--err);color:var(--err)}
button.primary{background:var(--accent);border:0;color:#fff;border-radius:.55rem;
  padding:.5rem 1.3rem;font-weight:700;font-size:.88rem;cursor:pointer;
  box-shadow:var(--shadow)}
button.primary:disabled{opacity:.5;cursor:default;box-shadow:none}

.actions{position:sticky;bottom:0;background:var(--panel);
  border-top:1px solid var(--line);margin:0 -1.3rem -1.2rem;
  padding:.75rem 1.3rem;display:flex;gap:.9rem;align-items:center}
.actions .note{font-size:.76rem;color:var(--muted)}
#dirtyCount{font-size:.8rem;font-weight:600;color:var(--warn)}

.regex-test{display:flex;gap:.45rem;align-items:center;font-size:.74rem;
  color:var(--muted);margin-top:.35rem}
.regex-test input{max-width:15rem;padding:.25rem .5rem;font-size:.78rem}

.findings{margin-top:1.1rem}
.findings h3{font-size:.85rem;margin:.2rem 0 .5rem}
.finding{display:flex;gap:.6rem;align-items:baseline;flex-wrap:wrap;
  border:1px solid var(--line);border-left:3px solid var(--muted);
  border-radius:.5rem;padding:.5rem .8rem;margin:.4rem 0;font-size:.82rem}
.finding.f-error{border-left-color:var(--err)}
.finding.f-warning{border-left-color:var(--warn)}
.finding .code{font-weight:700}
.f-error .code{color:var(--err)}.f-warning .code{color:var(--warn)}
.f-info .code{color:var(--muted)}
.alert{border:1px solid var(--err);border-radius:.6rem;background:
  color-mix(in srgb, var(--err) 7%, var(--panel));padding:.7rem 1rem;
  font-size:.84rem;margin-bottom:1rem}
#tplRow{display:flex;gap:.6rem;align-items:center;margin:.15rem 0 .7rem;
  flex-wrap:wrap;font-size:.8rem}
#tplRow select{max-width:22rem;width:auto;padding:.25rem .5rem;font-size:.8rem}
.muted{color:var(--muted)}
#yamlVerdict{font-size:.8rem;margin:.5rem 0}
#yamlVerdict.bad{color:var(--err)}#yamlVerdict.good{color:var(--ok)}
</style></head>
<body>
<header><h1>wiki-config</h1><span id="vault" class="vault"></span>
<button class="primary" id="saveAll" hidden>Save all</button>
<span id="status"></span></header>
<main>
<nav>
  <div class="navhead"><span class="navtitle">Folders</span>
    <button class="small" id="expandAll" title="expand all">⊞</button>
    <button class="small" id="collapseAll" title="collapse all">⊟</button>
  </div>
  <div id="tree"></div>
</nav>
<div id="panel"><div class="panelbody"><p class="muted">Loading…</p></div></div>
</main>
<script>
"use strict";
const token = new URLSearchParams(location.hash.slice(1)).get("t") || "";
const HDR = {"X-Wiki-Config-Token": token};
const JHDR = {...HDR, "Content-Type": "application/json"};
let SCHEMA = [];            // [{pointer,kind,scope,enum,default,description,format}]
let FOLDER = null;          // /api/folder payload for the selected folder
let TREE = null;            // cached /api/tree payload
let SEL = ".";
const PENDING = new Map();  // rel -> Map(pointer -> {op,value}) — survives switching
const BASEHASH = new Map(); // rel -> file hash captured when the folder loaded
let COLLAPSED = new Set();

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s).replace(/[&<>"']/g,
  (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const api = async (path, opts) => {
  const r = await fetch(path, opts);
  const j = await r.json().catch(() => ({}));
  return {status: r.status, body: j};
};
const setStatus = (text, ok) => {
  const el = $("#status");
  el.textContent = text;
  el.className = ok ? "ok" : (ok === false ? "err" : "");
  if (text) setTimeout(() => { el.textContent = ""; el.className = ""; }, 5000);
};

// ---------- pending-edit state ----------------------------------------------
const pendingFor = (rel) => {
  if (!PENDING.has(rel)) PENDING.set(rel, new Map());
  return PENDING.get(rel);
};
const dirtyFolders = () =>
  [...PENDING.entries()].filter(([, m]) => m.size).map(([rel]) => rel);
window.addEventListener("beforeunload", (e) => {
  if (dirtyFolders().length) { e.preventDefault(); e.returnValue = ""; }
});

// ---------- data helpers ---------------------------------------------------
const byPointer = (obj, pointer) => pointer.split("/").filter(Boolean)
  .reduce((acc, part) => (acc && typeof acc === "object") ? acc[part] : undefined, obj);
const parts = (pointer) => pointer.split("/").filter(Boolean);
const topKey = (pointer) => parts(pointer)[0];
const leafKey = (pointer) => parts(pointer).at(-1);
const midPath = (pointer) => parts(pointer).slice(1, -1).join(" › ");
const isUnder = (rel, ancestor) =>
  ancestor === "." ? rel !== "." : rel !== ancestor && rel.startsWith(ancestor + "/");

// ---------- collapsible tree --------------------------------------------------
const lsKey = () => "wiki-config-collapsed:" + ((TREE && TREE.vault_root) || "");
const loadCollapsed = () => {
  try { COLLAPSED = new Set(JSON.parse(localStorage.getItem(lsKey()) || "[]")); }
  catch { COLLAPSED = new Set(); }
};
const saveCollapsed = () => {
  try { localStorage.setItem(lsKey(), JSON.stringify([...COLLAPSED])); }
  catch { /* private mode */ }
};

async function loadTree() {
  const {body} = await api("/api/tree", {headers: HDR});
  TREE = body;
  $("#vault").textContent = body.vault_root || "";
  loadCollapsed();
  renderTree();
}

function renderTree() {
  const folders = (TREE.folders && TREE.folders.length
    ? TREE.folders
    : [".", ...(TREE.nodes || []).map((n) => n.folder)]
        .map((rel) => ({rel, configured: true})))
    .slice().sort((a, b) => a.rel.localeCompare(b.rel));
  const rels = folders.map((f) => f.rel);
  const hasKids = (rel) => rels.some((r) => isUnder(r, rel));
  const hidden = (rel) => [...COLLAPSED].some((c) => isUnder(rel, c));
  const byRel = new Map((TREE.nodes || []).map((n) => [n.folder, n]));
  const tree = $("#tree");
  tree.innerHTML = "";
  folders.forEach(({rel, configured}) => {
    if (hidden(rel)) return;
    const node = byRel.get(rel);
    const marks = node && node.ignored && node.ignored.length ? "⛔"
      : (node && node.error ? "⚠" : "");
    const depth = rel === "." ? 0 : rel.split("/").length;
    const name = rel === "." ? "(vault root)" : rel.split("/").at(-1);
    const dot = configured ? '<span class="cfgdot">● </span>' : "";
    const kids = hasKids(rel);
    const row = document.createElement("div");
    row.className = "navrow";
    row.style.paddingLeft = (Math.max(0, depth - (rel === "." ? 0 : 1)) * 0.85) + "rem";
    const chev = document.createElement("button");
    chev.className = "chev" + (kids ? "" : " leaf");
    chev.textContent = COLLAPSED.has(rel) ? "▸" : "▾";
    chev.title = COLLAPSED.has(rel) ? "expand" : "collapse";
    if (kids) chev.onclick = (e) => {
      e.stopPropagation();
      COLLAPSED.has(rel) ? COLLAPSED.delete(rel) : COLLAPSED.add(rel);
      saveCollapsed();
      renderTree();
    };
    const item = document.createElement("button");
    item.className = "item" + (configured ? "" : " dim")
      + (rel === SEL ? " active" : "");
    item.title = rel + (configured ? " — has its own config" : " — inherited only");
    item.dataset.label = rel;
    item.innerHTML = `<span class="nm">${dot}${esc(name)}</span>`
      + `<span><span class="pdot" data-pdot="${esc(rel)}"></span> ${marks}</span>`;
    item.onclick = () => select(rel, item);
    row.appendChild(chev);
    row.appendChild(item);
    tree.appendChild(row);
  });
  if (TREE.truncated) {
    const note = document.createElement("div");
    note.className = "navnote";
    note.textContent = "tree truncated at 5000 folders";
    tree.appendChild(note);
  }
  const other = document.createElement("div");
  other.className = "navrow";
  other.innerHTML = `<button class="chev leaf">▸</button>
    <button class="item"><span class="nm muted">+ other folder…</span></button>`;
  other.querySelector(".item").onclick = () => {
    const rel = prompt("Vault-relative folder path:");
    if (rel) select(rel, null);
  };
  tree.appendChild(other);
  updateDots();
}

function updateDots() {
  const dirty = dirtyFolders();
  document.querySelectorAll("[data-pdot]").forEach((el) => {
    const rel = el.dataset.pdot;
    const own = dirty.includes(rel);
    // a COLLAPSED ancestor shows the dot for its hidden dirty descendants
    const below = COLLAPSED.has(rel) && dirty.some((d) => isUnder(d, rel));
    el.textContent = own ? "●" : (below ? "◦" : "");
    el.title = own ? "unsaved changes here"
      : (below ? "unsaved changes inside" : "");
  });
  const saveAll = $("#saveAll");
  if (saveAll) {
    saveAll.hidden = dirty.length === 0;
    saveAll.textContent = `Save all (${dirty.length})`;
  }
}

$("#expandAll").onclick = () => { COLLAPSED.clear(); saveCollapsed(); renderTree(); };
$("#collapseAll").onclick = () => {
  const rels = (TREE.folders || []).map((f) => f.rel);
  rels.forEach((rel) => {
    if (rels.some((r) => isUnder(r, rel)) && rel !== ".") COLLAPSED.add(rel);
  });
  saveCollapsed();
  renderTree();
};

async function select(label, btn) {
  SEL = label;
  document.querySelectorAll("nav .item").forEach((x) =>
    x.classList.toggle("active", btn ? x === btn : x.dataset.label === label));
  const {status, body} = await api(
    "/api/folder?rel=" + encodeURIComponent(label), {headers: HDR});
  if (status !== 200) { setStatus(body.error || "load failed", false); return; }
  FOLDER = body;
  BASEHASH.set(label, body.hash);
  renderPanel("form");
}

// ---------- panel -----------------------------------------------------------
function renderPanel(tab) {
  const panel = $("#panel");
  const broken = FOLDER.broken
    ? `<div class="alert">A config on this path fails its gate `
      + `(${esc(FOLDER.broken.reason || "")} at ${esc(FOLDER.broken.level || "?")}): `
      + `${esc(FOLDER.broken.detail || "")}. The form needs a valid cascade — `
      + `use the YAML tab or the doctor first.</div>`
    : "";
  const hasOwn = !!FOLDER.hash;
  const configNote = hasOwn
    ? `<div class="confignote"><span>● this folder has its own
        <code>.wiki/sync.yaml</code></span>
        <button class="small danger" id="deleteConfig"
          title="remove this folder's overrides — values fall back to the
inherited cascade; a backup is kept in .wiki/backups/">
          ✕ delete config (fall back to inherited)</button></div>`
    : `<div class="confignote"><span>○ no own config — the values below are
        INHERITED; editing + saving creates
        <code>${esc(FOLDER.rel === "." ? "" : FOLDER.rel + "/")}.wiki/sync.yaml</code>
        here</span></div>`;
  panel.innerHTML = `
    <div class="panelhead">
      <h2>${esc(FOLDER.rel === "." ? "(vault root)" : FOLDER.rel)}</h2>
      ${configNote}
      <div id="restoreRow"></div>
      <div id="tplRow"></div>
      <div class="tabs">
        <button id="tabForm" class="${tab === "form" ? "active" : ""}">Form</button>
        <button id="tabYaml" class="${tab === "yaml" ? "active" : ""}">YAML</button>
      </div>
    </div>
    <div class="panelbody">
      ${broken}
      <div id="tabBody"></div>
      <div id="findingsBox" class="findings"></div>
    </div>`;
  $("#tabForm").onclick = () => renderPanel("form");
  $("#tabYaml").onclick = () => renderPanel("yaml");
  const del = $("#deleteConfig");
  if (del) del.onclick = deleteConfig;
  if (tab === "form" && !FOLDER.broken) renderForm();
  else if (tab === "yaml") renderYaml();
  renderFindings();
  renderTemplates();
  renderRestore();
}

// ---------- schema-driven form ----------------------------------------------
function fieldState(spec) {
  const ownVal = FOLDER.own ? byPointer(FOLDER.own, spec.pointer) : undefined;
  const eff = byPointer(FOLDER.effective || {}, spec.pointer);
  const prov = (FOLDER.provenance || {})[spec.pointer] || {};
  const dirty = pendingFor(FOLDER.rel).get(spec.pointer);
  return {ownVal, eff, prov, dirty};
}

function badgeFor(spec, st) {
  if (spec.scope === "root-only" && !FOLDER.is_root)
    return '<span class="badge b-disabled">root-only</span>';
  if (st.dirty) return '<span class="badge b-here">edited</span>';
  if (st.ownVal !== undefined) return '<span class="badge b-here">HERE</span>';
  const origin = st.prov.origin || "default";
  if (origin === "default") return '<span class="badge b-default">default</span>';
  if (origin === "root" && spec.scope === "root-only")
    return '<span class="badge b-root">ROOT</span>';
  return `<span class="badge b-inherited" title="cascaded from ${esc(origin)}">`
    + `↑ ${esc(origin)}</span>`;
}

function inputFor(spec, st, id) {
  const disabled = (spec.scope === "root-only" && !FOLDER.is_root) ? "disabled" : "";
  const current = st.dirty && st.dirty.op === "set" ? st.dirty.value
    : (st.dirty && st.dirty.op === "unset" ? undefined
      : (st.ownVal !== undefined ? st.ownVal : undefined));
  const inherited = st.eff === undefined ? spec.default : st.eff;
  const placeholder = current === undefined
    ? `inherited: ${esc(JSON.stringify(inherited === undefined ? null : inherited))}`
    : "";
  if (spec.enum) {
    const opts = ['<option value="">(inherit: ' + esc(String(inherited ?? "—"))
      + ")</option>"]
      .concat(spec.enum.map((v) =>
        `<option value="${esc(v)}" ${current === v ? "selected" : ""}>${esc(v)}</option>`));
    return `<select id="${id}" ${disabled}>${opts.join("")}</select>`;
  }
  if (spec.kind === "boolean") {
    const sel = (v) => current === v ? "selected" : "";
    return `<select id="${id}" ${disabled}>
      <option value="">(inherit: ${esc(String(inherited ?? "—"))})</option>
      <option value="true" ${sel(true)}>true</option>
      <option value="false" ${sel(false)}>false</option></select>`;
  }
  if (spec.kind === "array") {
    const val = Array.isArray(current) ? current.join("\n") : "";
    return `<textarea id="${id}" rows="6" ${disabled} placeholder="${placeholder}"
      spellcheck="false" title="one item per line">${esc(val)}</textarea>`;
  }
  const val = current === undefined ? "" : String(current);
  return `<input id="${id}" ${disabled} value="${esc(val)}"
    placeholder="${placeholder}" spellcheck="false">`;
}

function renderForm() {
  const body = $("#tabBody");
  const groups = new Map();
  SCHEMA.forEach((spec) => {
    if (spec.kind === "object") return; // block nodes render as fieldsets/subheads
    const top = topKey(spec.pointer);
    if (!groups.has(top)) groups.set(top, []);
    groups.get(top).push(spec);
  });
  let html = "";
  let i = 0;
  for (const [top, specs] of groups) {
    const topSpec = SCHEMA.find((s) => s.pointer === "/" + top) || {};
    const scopeNote = topSpec.scope === "root-only"
      ? '<span class="scope"> · root-only</span>'
      : '<span class="scope"> · cascades per folder</span>';
    html += `<fieldset><legend>${esc(top)}${scopeNote}</legend>`;
    let prevMid = null;
    for (const spec of specs) {
      const mid = midPath(spec.pointer);
      if (mid !== prevMid && mid) {
        html += `<div class="subhead">${esc(mid)}</div>`;
      }
      prevMid = mid;
      const st = fieldState(spec);
      const id = "fld" + (i++);
      const hint = spec.description
        ? `<p class="hint" data-hint>${esc(spec.description)}</p>` : "";
      html += `<div class="field" title="${esc(spec.pointer)}">
        <div class="fl">
          <label class="fname" for="${id}">${esc(leafKey(spec.pointer))}</label>
          ${mid ? `<span class="fpath">${esc(mid)}</span>` : ""}
        </div>
        <div class="fc">${inputFor(spec, st, id)}
          ${spec.format === "regex" ? `
            <div class="regex-test">test:
              <input id="${id}-sample" placeholder="sample filename">
              <span id="${id}-key"></span></div>` : ""}
        </div>
        <div class="fb">${badgeFor(spec, st)}
          ${st.ownVal !== undefined && !(spec.scope === "root-only" && !FOLDER.is_root)
            ? `<button class="small" data-reset="${esc(spec.pointer)}"
               title="remove the override here — fall back to the inherited value">
               ✕ reset</button>` : ""}
        </div>
        ${hint}
      </div>`;
      queueMicrotask(((spec, id) => () => wireField(spec, id))(spec, id));
    }
    html += "</fieldset>";
  }
  const saveLabel = FOLDER.hash ? "Save this folder" : "Create override here";
  const saveNote = FOLDER.hash
    ? "schema-gated · comment-preserving · backed up to .wiki/backups/"
    : "creates this folder's .wiki/sync.yaml with ONLY the fields you set";
  html += `<div class="actions">
    <button class="primary" id="saveForm">${saveLabel}</button>
    <span id="dirtyCount"></span>
    <span class="note">${saveNote}</span></div>`;
  body.innerHTML = html;
  $("#saveForm").onclick = saveForm;
  body.querySelectorAll("[data-reset]").forEach((b) => b.onclick = () => {
    pendingFor(FOLDER.rel).set(b.dataset.reset, {op: "unset"});
    renderPanel("form");
    updateDirtyCount();
  });
  body.querySelectorAll("[data-hint]").forEach((h) => {
    if (h.scrollHeight > h.clientHeight + 2) {
      h.classList.add("expandable");
      h.title = "click to expand";
      h.onclick = () => h.classList.toggle("open");
    }
  });
  updateDirtyCount();
}

function updateDirtyCount() {
  const size = pendingFor(SEL).size;
  const el = $("#dirtyCount");
  if (el) el.textContent = size
    ? `${size} unsaved change${size > 1 ? "s" : ""}` : "";
  const save = $("#saveForm");
  if (save) save.disabled = !size;
  updateDots();
}

function wireField(spec, id) {
  const el = document.getElementById(id);
  if (!el) return;
  el.addEventListener("input", () => {
    const pending = pendingFor(FOLDER.rel);
    let value = el.value;
    if (value === "") {
      const own = FOLDER.own ? byPointer(FOLDER.own, spec.pointer) : undefined;
      if (own !== undefined) pending.set(spec.pointer, {op: "unset"});
      else pending.delete(spec.pointer);
      updateDirtyCount();
      return;
    }
    if (spec.kind === "boolean") value = value === "true";
    else if (spec.kind === "array")
      value = el.value.split("\n").map((s) => s.trim()).filter(Boolean);
    pending.set(spec.pointer, {op: "set", value});
    updateDirtyCount();
  });
  const sample = document.getElementById(id + "-sample");
  if (sample) sample.addEventListener("input", async () => {
    const st = fieldState(spec);
    const pattern = document.getElementById(id).value
      || (st.eff !== undefined && st.eff !== null ? String(st.eff) : "");
    const out = document.getElementById(id + "-key");
    if (!pattern || !sample.value) { out.textContent = ""; return; }
    const {body} = await api("/api/test-regex", {method: "POST", headers: JHDR,
      body: JSON.stringify({pattern, sample: sample.value})});
    out.textContent = body.ok
      ? (body.key ? `→ key "${body.key}"` : "→ no match")
      : `⚠ ${body.detail || "unsafe pattern"}`;
  });
}

// ---------- saving -----------------------------------------------------------
async function saveOne(rel) {
  const pending = pendingFor(rel);
  if (!pending.size) return {ok: true};
  const edits = [...pending.entries()].map(([pointer, e]) =>
    ({pointer, op: e.op, value: e.value}));
  const {status, body} = await api("/api/write", {method: "POST", headers: JHDR,
    body: JSON.stringify({rel, edits, expected_hash: BASEHASH.get(rel)})});
  if (status === 200) {
    PENDING.delete(rel);
    BASEHASH.set(rel, body.hash);
    return {ok: true, backup: body.backup};
  }
  return {ok: false, error: `${body.error || "save failed"}: ${body.detail || ""}`};
}

async function saveForm() {
  const result = await saveOne(FOLDER.rel);
  if (result.ok) {
    setStatus("saved ✓ (backup: " + (result.backup || "new file") + ")", true);
    select(SEL, document.querySelector("nav .item.active"));
    loadTree();
  } else setStatus(result.error, false);
}

async function saveAll() {
  const rels = dirtyFolders();
  const failed = [];
  for (const rel of rels) {
    const result = await saveOne(rel);
    if (!result.ok) failed.push(`${rel}: ${result.error}`);
  }
  if (failed.length) setStatus(`saved ${rels.length - failed.length}/${rels.length}; `
    + `FAILED — ${failed.join(" · ")}`, false);
  else setStatus(`saved all (${rels.length}) ✓`, true);
  select(SEL, document.querySelector("nav .item.active"));
  loadTree();
}
$("#saveAll").onclick = saveAll;

async function deleteConfig() {
  const target = FOLDER.rel === "." ? ".wiki/sync.yaml"
    : FOLDER.rel + "/.wiki/sync.yaml";
  if (!confirm(`Delete ${target}?\n\nThis folder falls back to the inherited `
      + "cascade. A backup is kept in .wiki/backups/ (wiki-config restore "
      + "undoes this).")) return;
  const {status, body} = await api("/api/delete-config", {method: "POST",
    headers: JHDR, body: JSON.stringify({rel: FOLDER.rel})});
  if (status === 200) {
    PENDING.delete(FOLDER.rel);
    setStatus("config deleted ✓ (backup: " + (body.backup || "—") + ")", true);
    select(SEL, document.querySelector("nav .item.active"));
    loadTree();
  } else setStatus(body.error || "delete failed", false);
}

// ---------- restore from backups -------------------------------------------------
function fmtBackup(entry) {
  // sync.yaml.20260711T123456.789012Z.bak → "2026-07-11 12:34:56 UTC"
  const m = entry.name.match(/\.(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})/);
  const when = m ? `${m[1]}-${m[2]}-${m[3]} ${m[4]}:${m[5]}:${m[6]} UTC`
                 : entry.mtime || entry.name;
  const kb = entry.size >= 1024 ? (entry.size / 1024).toFixed(1) + " KiB"
                                : entry.size + " B";
  return `${when} · ${kb}`;
}

async function renderRestore() {
  const row = $("#restoreRow");
  row.innerHTML = "";
  const {status, body} = await api(
    "/api/backups?rel=" + encodeURIComponent(FOLDER.rel), {headers: HDR});
  if (status !== 200) return;
  const backups = body.backups || [];
  if (!backups.length) return;
  const hasOwn = !!FOLDER.text;
  const lead = hasOwn
    ? `<span class="muted">↺ Restore from backup (${backups.length}):</span>`
    : `<span style="color:var(--warn);font-weight:600">↺ This folder HAD a
       config — ${backups.length} backup${backups.length > 1 ? "s" : ""}
       available:</span>`;
  row.innerHTML = `${lead}
    <select id="bakSel">${backups.map((b, i) =>
      `<option value="${esc(b.name)}">${esc(fmtBackup(b))}${
        i === 0 ? " (newest)" : ""}</option>`).join("")}</select>
    <button class="small" id="bakGo">restore</button>`;
  row.className = "confignote";
  $("#bakGo").onclick = async () => {
    const name = $("#bakSel").value;
    if (!confirm(`Restore ${FOLDER.rel === "." ? "" : FOLDER.rel + "/"}`
        + `.wiki/sync.yaml from\n${name}?\n\n`
        + (hasOwn ? "The CURRENT file is backed up first — restore is reversible."
                  : "The folder gets its config back, byte-exact.")))
      return;
    const {status: st, body: r} = await api("/api/restore", {method: "POST",
      headers: JHDR,
      body: JSON.stringify({rel: FOLDER.rel, name})});
    if (st === 200) {
      PENDING.delete(FOLDER.rel);
      setStatus("restored ✓" + (r.restored_file_valid === false
        ? " (note: the restored file no longer passes validation — run doctor)"
        : ""), true);
      select(SEL, document.querySelector("nav .item.active"));
      loadTree();
    } else setStatus(r.error || "restore failed", false);
  };
}

// ---------- yaml tab ----------------------------------------------------------
function renderYaml() {
  const body = $("#tabBody");
  body.innerHTML = `
    <textarea id="yamlText" spellcheck="false">${esc(FOLDER.text || "")}</textarea>
    <p id="yamlVerdict" class="muted">validation runs as you type</p>
    <div class="actions"><button class="primary" id="saveYaml">Save YAML</button>
    <span class="note">full hardened gate before write · backup taken</span></div>`;
  const area = $("#yamlText");
  let timer = null;
  area.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const {body: v} = await api("/api/validate", {method: "POST", headers: JHDR,
        body: JSON.stringify({text: area.value})});
      const verdict = $("#yamlVerdict");
      verdict.textContent = v.ok ? "✓ valid"
        : `✗ ${v.reason || ""}: ${v.detail || ""}`;
      verdict.className = v.ok ? "good" : "bad";
    }, 400);
  });
  $("#saveYaml").onclick = async () => {
    const {status, body: r} = await api("/api/write", {method: "POST",
      headers: JHDR,
      body: JSON.stringify({rel: FOLDER.rel, text: area.value,
                            expected_hash: BASEHASH.get(FOLDER.rel)})});
    if (status === 200) {
      PENDING.delete(FOLDER.rel);
      setStatus("saved ✓", true);
      select(SEL, document.querySelector("nav .item.active"));
      loadTree();
    } else setStatus(`${r.error || "save failed"}: ${r.detail || ""}`, false);
  };
}

// ---------- findings + fixes ----------------------------------------------------
function renderFindings() {
  const box = $("#findingsBox");
  const findings = FOLDER.findings || [];
  if (!findings.length) { box.innerHTML = ""; return; }
  const planById = new Map((FOLDER.fix_plans || []).map((p) => [p.id, p]));
  box.innerHTML = "<h3>Findings</h3>" +
    findings.map((f) => {
      const planId = `${f.code}:${f.file}:${f.pointer || ""}`;
      const plan = planById.get(planId);
      return `<div class="finding f-${esc(f.severity)}">
        <span class="code">${esc(f.code)}</span>
        ${f.pointer ? `<code>${esc(f.pointer)}</code>` : ""}
        <span>${esc(f.message)}</span>
        ${plan ? `<button class="small" data-fix="${esc(plan.id)}"
          title="${esc(plan.description)}">fix (${esc(plan.tier)})</button>` : ""}
      </div>`;
    }).join("");
  box.querySelectorAll("[data-fix]").forEach((b) => b.onclick = async () => {
    const {status} = await api("/api/fix", {method: "POST", headers: JHDR,
      body: JSON.stringify({id: b.dataset.fix})});
    setStatus(status === 200 ? "fixed ✓ (backup taken)" : "fix failed",
              status === 200);
    select(SEL, document.querySelector("nav .item.active"));
    loadTree();
  });
}

// ---------- templates ------------------------------------------------------------
async function renderTemplates() {
  const row = $("#tplRow");
  const hasOwn = !!FOLDER.text;
  const caption = hasOwn ? "Re-init from template:" : "Quick setup from template:";
  const goLabel = hasOwn ? "replace…" : "apply";
  row.innerHTML = `<span class="muted">${caption}</span>
    <select id="tplSel"><option value="">choose a template…</option></select>
    <button class="small" id="tplGo">${goLabel}</button>
    ${hasOwn ? '<span class="muted">replaces this file — a backup is kept</span>'
             : ""}`;
  const {body} = await api("/api/templates", {headers: HDR});
  const templates = body.templates || [];
  const sel = $("#tplSel");
  templates.forEach((t) => {
    const level = t.level === "root" ? " (root)" : "";
    const o = document.createElement("option");
    o.value = t.name; o.textContent = `${t.name} v${t.version}${level}`;
    o.title = t.purpose || "";
    sel.appendChild(o);
  });
  $("#tplGo").onclick = async () => {
    if (!sel.value) return;
    if (hasOwn && !confirm(
        `Replace this folder's sync.yaml with the '${sel.value}' template?\n\n`
        + "The current file goes to .wiki/backups/ first (wiki-config restore "
        + "undoes this). Hand-authored keys and comments are NOT merged — "
        + "use `wiki-config init --merge` from the CLI for an additive merge."))
      return;
    const tpl = templates.find((t) => t.name === sel.value);
    const vars = {};
    for (const v of (tpl && tpl.required_vars) || []) {
      const answer = prompt(
        `${v.name} (${v.kind}): ${v.description}` +
        (v.default ? ` [default: ${v.default}]` : ""));
      if (answer) vars[v.name] = answer;
    }
    const {status, body: r} = await api("/api/template", {method: "POST",
      headers: JHDR,
      body: JSON.stringify({rel: FOLDER.rel, template: sel.value, vars,
                            force: hasOwn})});
    setStatus(status === 200 ? `applied ${sel.value} ✓`
      : `${r.error || "failed"}`, status === 200);
    select(SEL, document.querySelector("nav .item.active"));
    loadTree();
  };
}

// ---------- boot ------------------------------------------------------------------
(async () => {
  if (!token) {
    $("#panel").innerHTML = "<div class='panelbody'><div class='alert'>" +
      "Missing token — open the exact URL printed by " +
      "<code>wiki-config serve</code> (it carries #t=…).</div></div>";
    return;
  }
  const {status, body} = await api("/api/schema", {headers: HDR});
  if (status !== 200) {
    $("#panel").innerHTML = "<div class='panelbody'><div class='alert'>" +
      "Unauthorized — the token in the URL fragment does not match the " +
      "running server.</div></div>";
    return;
  }
  SCHEMA = body.fields || [];
  await loadTree();
  const rootBtn = document.querySelector('nav .item[data-label="."]');
  if (rootBtn) rootBtn.click();
})();
</script></body></html>
"""
