"""TASK 058 — the `wiki-config serve` inline web app (ONE self-contained page).

Vanilla JS, zero deps, no build step (explicit user decision over React/shadcn).
The FORM is rendered generically from `GET /api/schema` (the UI-model projection
of the sync-config schema): enum → <select>, boolean → tri-state select
(inherit/true/false), string → input (regex fields get a live tester), array →
one-item-per-line textarea. Field hints come from the schema `description`;
inherited values render as placeholders with the origin badge and an
"override here / reset" toggle; root-only fields are disabled outside the vault
root. A new schema field appears here with ZERO edits to this file (R-058-10).

Kept as a Python module holding one string so mypy/pytest cover its wiring;
the page itself is served by `_server.py` under a strict CSP.
"""

from __future__ import annotations

APP_HTML = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>wiki-config</title>
<style>
:root{--bg:#fff;--fg:#0a0a0a;--muted:#6b7280;--card:#f8f9fb;--line:#e5e7eb;
--accent:#2563eb;--ok:#16a34a;--warn:#d97706;--err:#dc2626;--here:#16a34a;
--inh:#0d9488;--rootb:#2563eb;--def:#6b7280;
font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}
@media (prefers-color-scheme:dark){:root{--bg:#0b0e14;--fg:#e6e8ee;
--muted:#9aa4b2;--card:#131722;--line:#232a38}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg)}
header{position:sticky;top:0;background:var(--bg);z-index:3;
border-bottom:1px solid var(--line);padding:.7rem 1.2rem;display:flex;
gap:1rem;align-items:center}h1{font-size:1rem;margin:0}
.muted{color:var(--muted);font-size:.8rem}
main{display:grid;grid-template-columns:minmax(13rem,19rem) 1fr;gap:1rem;
padding:1rem 1.2rem;max-width:88rem;margin:0 auto}
nav{position:sticky;top:3.4rem;align-self:start;max-height:calc(100vh - 5rem);
overflow:auto;border:1px solid var(--line);border-radius:.7rem;padding:.4rem}
nav button{display:flex;width:100%;justify-content:space-between;text-align:left;
background:none;border:0;color:var(--fg);padding:.35rem .6rem;font-size:.85rem;
border-radius:.4rem;cursor:pointer}
nav button:hover{background:var(--card)}nav button.active{background:var(--card);
outline:1px solid var(--accent)}
#panel{border:1px solid var(--line);border-radius:.7rem;background:var(--card);
padding:1rem;min-height:20rem}
.tabs{display:flex;gap:.4rem;margin:.6rem 0 1rem}
.tabs button{background:var(--bg);border:1px solid var(--line);color:var(--fg);
border-radius:.5rem;padding:.3rem .9rem;cursor:pointer}
.tabs button.active{border-color:var(--accent);color:var(--accent);font-weight:600}
fieldset{border:1px solid var(--line);border-radius:.6rem;margin:0 0 1rem;
padding:.6rem 1rem;background:var(--bg)}
legend{font-weight:600;padding:0 .4rem}
.field{display:grid;grid-template-columns:minmax(9rem,14rem) minmax(10rem,1fr) auto;
gap:.6rem;align-items:start;padding:.45rem 0;border-bottom:1px dashed var(--line)}
.field:last-child{border-bottom:0}
.field label{font-size:.85rem;padding-top:.3rem}
.field .hint{grid-column:1/-1;font-size:.75rem;color:var(--muted);margin:0}
input,select,textarea{background:var(--bg);color:var(--fg);
border:1px solid var(--line);border-radius:.45rem;padding:.3rem .5rem;
font-size:.85rem;width:100%}
textarea{font-family:ui-monospace,Menlo,monospace;min-height:3.2rem}
#yamlText{min-height:22rem;white-space:pre;font-size:.82rem}
.badge{display:inline-block;border-radius:.6rem;padding:.05rem .5rem;
font-size:.7rem;font-weight:600;color:#fff;white-space:nowrap}
.b-default{background:var(--def)}.b-root{background:var(--rootb)}
.b-here{background:var(--here)}.b-inherited{background:var(--inh)}
.b-disabled{background:var(--err)}
button.small{background:var(--bg);border:1px solid var(--line);color:var(--fg);
border-radius:.4rem;padding:.15rem .5rem;font-size:.72rem;cursor:pointer}
button.primary{background:var(--accent);border:0;color:#fff;border-radius:.5rem;
padding:.45rem 1.1rem;font-weight:600;cursor:pointer}
#status{font-size:.85rem;margin-left:.8rem}
#status.ok{color:var(--ok)}#status.err{color:var(--err)}
ul#findings{padding-left:1.1rem;font-size:.83rem}
ul#findings li{margin:.25rem 0}
.f-error{color:var(--err)}.f-warning{color:var(--warn)}.f-info{color:var(--muted)}
.regex-test{grid-column:2/3;display:flex;gap:.4rem;align-items:center;
font-size:.75rem}.regex-test input{max-width:14rem}
#tplRow{display:flex;gap:.5rem;align-items:center;margin-top:.6rem;flex-wrap:wrap}
</style></head>
<body>
<header><h1>wiki-config</h1><span id="vault" class="muted"></span>
<span id="status"></span></header>
<main>
<nav id="tree"></nav>
<div id="panel"><p class="muted">Loading…</p></div>
</main>
<script>
"use strict";
const token = new URLSearchParams(location.hash.slice(1)).get("t") || "";
const HDR = {"X-Wiki-Config-Token": token};
const JHDR = {...HDR, "Content-Type": "application/json"};
let SCHEMA = [];          // [{pointer,kind,scope,enum,default,description,format}]
let FOLDER = null;        // /api/folder payload for the selected folder
let DIRTY = new Map();    // pointer -> {op,value}
let SEL = ".";

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
  if (text) setTimeout(() => { el.textContent = ""; el.className = ""; }, 4000);
};

// ---------- data helpers ---------------------------------------------------
const byPointer = (obj, pointer) => pointer.split("/").filter(Boolean)
  .reduce((acc, part) => (acc && typeof acc === "object") ? acc[part] : undefined, obj);
const topKey = (pointer) => pointer.split("/").filter(Boolean)[0];
const leaves = SCHEMA; // filled after load

// ---------- tree ------------------------------------------------------------
async function loadTree() {
  const {body} = await api("/api/tree", {headers: HDR});
  $("#vault").textContent = body.vault_root || "";
  const labels = new Set([".", ...(body.nodes || []).map((n) => n.folder)]);
  const tree = $("#tree");
  tree.innerHTML = "";
  [...labels].sort((a, b) => a.localeCompare(b)).forEach((label) => {
    const node = (body.nodes || []).find((n) => n.folder === label);
    const marks = node && node.ignored && node.ignored.length ? " ⛔"
      : (node && node.error ? " ⚠" : "");
    const b = document.createElement("button");
    b.innerHTML = `<span>${esc(label)}</span><span>${marks}</span>`;
    b.onclick = () => select(label, b);
    b.dataset.label = label;
    if (label === SEL) b.classList.add("active");
    tree.appendChild(b);
  });
  const other = document.createElement("button");
  other.innerHTML = "<span>+ other folder…</span>";
  other.onclick = () => {
    const rel = prompt("Vault-relative folder path:");
    if (rel) select(rel, other);
  };
  tree.appendChild(other);
}

async function select(label, btn) {
  SEL = label;
  document.querySelectorAll("nav button").forEach((x) =>
    x.classList.toggle("active", x === btn));
  const {status, body} = await api(
    "/api/folder?rel=" + encodeURIComponent(label), {headers: HDR});
  if (status !== 200) { setStatus(body.error || "load failed", false); return; }
  FOLDER = body; DIRTY = new Map();
  renderPanel("form");
}

// ---------- panel -----------------------------------------------------------
function renderPanel(tab) {
  const panel = $("#panel");
  const broken = FOLDER.broken
    ? `<p class="f-error">A config on this path fails its gate `
      + `(${esc(FOLDER.broken.reason || "")} at ${esc(FOLDER.broken.level || "?")}): `
      + `${esc(FOLDER.broken.detail || "")}. The form needs a valid cascade — `
      + `use the YAML tab / doctor first.</p>`
    : "";
  panel.innerHTML = `
    <h2 style="margin:.2rem 0">${esc(FOLDER.rel)}</h2>
    <div class="tabs">
      <button id="tabForm" class="${tab === "form" ? "active" : ""}">Form</button>
      <button id="tabYaml" class="${tab === "yaml" ? "active" : ""}">YAML</button>
    </div>
    ${broken}
    <div id="tabBody"></div>
    <div id="findingsBox"></div>
    <div id="tplRow"></div>`;
  $("#tabForm").onclick = () => renderPanel("form");
  $("#tabYaml").onclick = () => renderPanel("yaml");
  if (tab === "form" && !FOLDER.broken) renderForm();
  else if (tab === "yaml") renderYaml();
  renderFindings();
  renderTemplates();
}

// ---------- schema-driven form ----------------------------------------------
function fieldState(spec) {
  const ownVal = FOLDER.own ? byPointer(FOLDER.own, spec.pointer) : undefined;
  const eff = byPointer(FOLDER.effective || {}, spec.pointer);
  const prov = (FOLDER.provenance || {})[spec.pointer] || {};
  const dirty = DIRTY.get(spec.pointer);
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
  return `<span class="badge b-inherited">↑ ${esc(origin)}</span>`;
}

function inputFor(spec, st, id) {
  const disabled = (spec.scope === "root-only" && !FOLDER.is_root) ? "disabled" : "";
  const current = st.dirty && st.dirty.op === "set" ? st.dirty.value
    : (st.ownVal !== undefined ? st.ownVal : undefined);
  const placeholder = current === undefined
    ? `inherited: ${esc(JSON.stringify(st.eff === undefined ? spec.default : st.eff))}`
    : "";
  if (spec.enum) {
    const opts = ['<option value="">(inherit)</option>']
      .concat(spec.enum.map((v) =>
        `<option value="${esc(v)}" ${current === v ? "selected" : ""}>${esc(v)}</option>`));
    return `<select id="${id}" ${disabled}>${opts.join("")}</select>`;
  }
  if (spec.kind === "boolean") {
    const sel = (v) => current === v ? "selected" : "";
    return `<select id="${id}" ${disabled}>
      <option value="">(inherit)</option>
      <option value="true" ${sel(true)}>true</option>
      <option value="false" ${sel(false)}>false</option></select>`;
  }
  if (spec.kind === "array") {
    const val = Array.isArray(current) ? current.join("\n") : "";
    return `<textarea id="${id}" ${disabled} placeholder="${placeholder}"
      spellcheck="false">${esc(val)}</textarea>`;
  }
  const val = current === undefined ? "" : String(current);
  return `<input id="${id}" ${disabled} value="${esc(val)}"
    placeholder="${placeholder}" spellcheck="false">`;
}

function renderForm() {
  const body = $("#tabBody");
  const groups = new Map();
  SCHEMA.forEach((spec) => {
    if (spec.kind === "object") return; // fieldset headers, not inputs
    const top = topKey(spec.pointer);
    if (!groups.has(top)) groups.set(top, []);
    groups.get(top).push(spec);
  });
  let html = "";
  let i = 0;
  for (const [top, specs] of groups) {
    const topSpec = SCHEMA.find((s) => s.pointer === "/" + top) || {};
    const scopeNote = topSpec.scope === "root-only"
      ? ' <span class="muted">(root-only)</span>'
      : ' <span class="muted">(cascades per folder)</span>';
    html += `<fieldset><legend>${esc(top)}${scopeNote}</legend>`;
    for (const spec of specs) {
      const st = fieldState(spec);
      const id = "fld" + (i++);
      html += `<div class="field">
        <label for="${id}"><code>${esc(spec.pointer)}</code></label>
        <div>${inputFor(spec, st, id)}
          ${spec.format === "regex" ? `
            <div class="regex-test">test:
              <input id="${id}-sample" placeholder="sample filename">
              <span id="${id}-key" class="muted"></span></div>` : ""}
        </div>
        <div>${badgeFor(spec, st)}
          ${st.ownVal !== undefined && !(spec.scope === "root-only" && !FOLDER.is_root)
            ? `<button class="small" data-reset="${esc(spec.pointer)}"
               title="remove the override here — fall back to the inherited value">
               ✕ reset</button>` : ""}
        </div>
        ${spec.description ? `<p class="hint">${esc(spec.description)}</p>` : ""}
      </div>`;
      queueMicrotask(((spec, id) => () => wireField(spec, id))(spec, id));
    }
    html += "</fieldset>";
  }
  html += `<button class="primary" id="saveForm">Save changes</button>
    <span class="muted">every save is schema-gated, comment-preserving, and
    backed up to .wiki/backups/</span>`;
  body.innerHTML = html;
  $("#saveForm").onclick = saveForm;
  body.querySelectorAll("[data-reset]").forEach((b) => b.onclick = () => {
    DIRTY.set(b.dataset.reset, {op: "unset"});
    renderPanel("form");
  });
}

function wireField(spec, id) {
  const el = document.getElementById(id);
  if (!el) return;
  el.addEventListener("input", () => {
    let value = el.value;
    if (value === "") {
      const st = fieldState(spec);
      if (st.ownVal !== undefined) DIRTY.set(spec.pointer, {op: "unset"});
      else DIRTY.delete(spec.pointer);
      return;
    }
    if (spec.kind === "boolean") value = value === "true";
    else if (spec.kind === "array")
      value = el.value.split("\n").map((s) => s.trim()).filter(Boolean);
    DIRTY.set(spec.pointer, {op: "set", value});
  });
  const sample = document.getElementById(id + "-sample");
  if (sample) sample.addEventListener("input", async () => {
    const pattern = document.getElementById(id).value
      || (fieldState(spec).eff ?? "");
    if (!pattern || !sample.value) return;
    const {body} = await api("/api/test-regex", {method: "POST", headers: JHDR,
      body: JSON.stringify({pattern, sample: sample.value})});
    document.getElementById(id + "-key").textContent =
      body.ok ? (body.key ? `→ key "${body.key}"` : "→ no match")
              : `⚠ ${body.detail || "unsafe pattern"}`;
  });
}

async function saveForm() {
  if (!DIRTY.size) { setStatus("nothing to save", true); return; }
  const edits = [...DIRTY.entries()].map(([pointer, e]) =>
    ({pointer, op: e.op, value: e.value}));
  const {status, body} = await api("/api/write", {method: "POST", headers: JHDR,
    body: JSON.stringify({rel: FOLDER.rel, edits,
                          expected_hash: FOLDER.hash})});
  if (status === 200) {
    setStatus("saved ✓ (backup: " + (body.backup || "new file") + ")", true);
    select(SEL, document.querySelector("nav button.active"));
    loadTree();
  } else {
    setStatus(`${body.error || "save failed"}: ${body.detail || ""}`, false);
  }
}

// ---------- yaml tab ----------------------------------------------------------
function renderYaml() {
  const body = $("#tabBody");
  body.innerHTML = `
    <textarea id="yamlText" spellcheck="false">${esc(FOLDER.text || "")}</textarea>
    <p id="yamlVerdict" class="muted">validation runs as you type</p>
    <button class="primary" id="saveYaml">Save YAML</button>`;
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
      verdict.className = v.ok ? "f-info" : "f-error";
    }, 400);
  });
  $("#saveYaml").onclick = async () => {
    const {status, body: r} = await api("/api/write", {method: "POST",
      headers: JHDR,
      body: JSON.stringify({rel: FOLDER.rel, text: area.value,
                            expected_hash: FOLDER.hash})});
    if (status === 200) {
      setStatus("saved ✓", true);
      select(SEL, document.querySelector("nav button.active"));
    } else setStatus(`${r.error || "save failed"}: ${r.detail || ""}`, false);
  };
}

// ---------- findings + fixes ----------------------------------------------------
function renderFindings() {
  const box = $("#findingsBox");
  const findings = FOLDER.findings || [];
  if (!findings.length) { box.innerHTML = ""; return; }
  const planById = new Map((FOLDER.fix_plans || []).map((p) => [p.id, p]));
  box.innerHTML = "<h3>Findings</h3><ul id='findings'>" +
    findings.map((f) => {
      const planId = `${f.code}:${f.file}:${f.pointer || ""}`;
      const plan = planById.get(planId);
      return `<li class="f-${esc(f.severity)}"><strong>${esc(f.code)}</strong>
        ${f.pointer ? `<code>${esc(f.pointer)}</code>` : ""} — ${esc(f.message)}
        ${plan ? `<button class="small" data-fix="${esc(plan.id)}"
          title="${esc(plan.description)}">fix (${esc(plan.tier)})</button>` : ""}
      </li>`;
    }).join("") + "</ul>";
  box.querySelectorAll("[data-fix]").forEach((b) => b.onclick = async () => {
    const {status, body} = await api("/api/fix", {method: "POST", headers: JHDR,
      body: JSON.stringify({id: b.dataset.fix})});
    setStatus(status === 200 ? "fixed ✓ (backup taken)" : "fix failed",
              status === 200);
    select(SEL, document.querySelector("nav button.active"));
    loadTree();
  });
}

// ---------- templates ------------------------------------------------------------
async function renderTemplates() {
  const row = $("#tplRow");
  if (FOLDER.text) { row.innerHTML = ""; return; }  // only offered for empty folders
  row.innerHTML = `<span class="muted">Quick setup:</span>
    <select id="tplSel"><option value="">choose a template…</option></select>
    <button class="small" id="tplGo">apply</button>`;
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
      body: JSON.stringify({rel: FOLDER.rel, template: sel.value, vars})});
    setStatus(status === 200 ? `applied ${sel.value} ✓`
      : `${r.error || "failed"}`, status === 200);
    select(SEL, document.querySelector("nav button.active"));
    loadTree();
  };
}

// ---------- boot ------------------------------------------------------------------
(async () => {
  if (!token) {
    $("#panel").innerHTML = "<p class='f-error'>Missing token — open the exact " +
      "URL printed by <code>wiki-config serve</code> (it carries #t=…).</p>";
    return;
  }
  const {status, body} = await api("/api/schema", {headers: HDR});
  if (status !== 200) {
    $("#panel").innerHTML = "<p class='f-error'>Unauthorized — the token in " +
      "the URL fragment does not match the running server.</p>";
    return;
  }
  SCHEMA = body.fields || [];
  await loadTree();
  const rootBtn = document.querySelector('nav button[data-label="."]');
  if (rootBtn) rootBtn.click();
})();
</script></body></html>
"""
