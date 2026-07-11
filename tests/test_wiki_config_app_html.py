"""TASK 058 vdd-multi cycle — regression coverage for the vanilla-JS `serve`
frontend (`_app_html.py`). The repo has no JS test harness (deliberately
dependency-free single-file app); these tests extract the REAL source text
(never a hand-copied reimplementation) and drive it under `node` with a
minimal stub of the browser globals it touches, so a regression in the
extracted functions fails here — not just in a browser.

Skipped whole-file when `node` is not on PATH (CI/dev-machine variance)."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.wiki_skills.wiki_config._app_html import APP_HTML

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="node not on PATH")


def _extract(start_marker: str, end_marker: str) -> str:
    start = APP_HTML.index(start_marker)
    end = APP_HTML.index(end_marker, start)
    return APP_HTML[start:end]


def _run_node(tmp_path: Path, script: str) -> None:
    path = tmp_path / "harness.js"
    path.write_text(script, encoding="utf-8")
    result = subprocess.run(["node", str(path)], capture_output=True, text=True,
                            timeout=30)
    assert result.returncode == 0, (
        f"node harness failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}")


def test_app_html_script_is_syntactically_valid() -> None:
    """Baseline: `node --check` on the WHOLE embedded script (syntax_only
    backstop for the two behavioral tests below, which only exercise
    fragments)."""
    m = re.search(r'<script>\n"use strict";\n(.*?)</script>', APP_HTML, re.S)
    assert m is not None
    script = m.group(1)
    result = subprocess.run(["node", "--check", "-"], input=script,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


def test_tree_set_helpers_match_bruteforce_reference(tmp_path: Path) -> None:
    """Finding 8b: `hasKidsSetFor`/`hiddenSetFor` (the O(n) precompute) must
    stay behaviorally IDENTICAL to the O(n^2) definitions they replaced
    (`rels.some(r => isUnder(r, rel))` / `[...COLLAPSED].some(c => isUnder(rel,
    c))`) across randomized folder trees + collapsed sets."""
    helpers = _extract(
        "// One O(n) pass (over each rel's OWN",
        "function renderTree() {")
    harness = f"""
"use strict";
let COLLAPSED = new Set();

{helpers}

function isUnderRef(rel, ancestor) {{
  return ancestor === "." ? rel !== "." : rel !== ancestor && rel.startsWith(ancestor + "/");
}}
function bruteHasKids(rels) {{
  const set = new Set();
  for (const rel of rels) if (rels.some((r) => isUnderRef(r, rel))) set.add(rel);
  return set;
}}
function bruteHidden(rels) {{
  const set = new Set();
  for (const rel of rels) if ([...COLLAPSED].some((c) => isUnderRef(rel, c))) set.add(rel);
  return set;
}}

function eqSet(a, b) {{
  if (a.size !== b.size) return false;
  for (const x of a) if (!b.has(x)) return false;
  return true;
}}

// Deterministic PRNG (no external deps) for reproducible trials.
let seed = 12345;
function rnd() {{ seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed / 0x7fffffff; }}

function randomTree(n) {{
  const rels = ["."];
  const pool = ["."];
  for (let i = 0; i < n; i++) {{
    const parent = pool[Math.floor(rnd() * pool.length)];
    const name = "d" + i;
    const rel = parent === "." ? name : parent + "/" + name;
    rels.push(rel);
    pool.push(rel);
  }}
  return rels;
}}

let failures = 0;
for (let trial = 0; trial < 300; trial++) {{
  const rels = randomTree(1 + Math.floor(rnd() * 40));
  // shuffle so callers can't rely on parent-before-child ordering
  for (let i = rels.length - 1; i > 0; i--) {{
    const j = Math.floor(rnd() * (i + 1));
    [rels[i], rels[j]] = [rels[j], rels[i]];
  }}
  COLLAPSED = new Set();
  const nCollapsed = Math.floor(rnd() * 5);
  for (let i = 0; i < nCollapsed; i++) {{
    COLLAPSED.add(rels[Math.floor(rnd() * rels.length)]);
  }}

  const gotKids = hasKidsSetFor(rels);
  const wantKids = bruteHasKids(rels);
  if (!eqSet(gotKids, wantKids)) {{
    console.error("hasKids mismatch", JSON.stringify(rels), JSON.stringify([...COLLAPSED]));
    failures++;
  }}
  const gotHidden = hiddenSetFor(rels);
  const wantHidden = bruteHidden(rels);
  if (!eqSet(gotHidden, wantHidden)) {{
    console.error("hidden mismatch", JSON.stringify(rels), JSON.stringify([...COLLAPSED]));
    failures++;
  }}
}}
if (failures) {{ console.error(failures + " mismatches"); process.exit(1); }}
console.log("ok");
"""
    _run_node(tmp_path, harness)


def test_select_drops_stale_response_after_newer_selection(tmp_path: Path) -> None:
    """Finding 8a: `select()` must ignore a slow response for a folder that is
    no longer the current selection — a fast SECOND click landing before a
    slow FIRST click's response must not have its state clobbered by the
    stale reply."""
    select_src = _extract("async function select(label, btn) {", "// ---------- panel")
    harness = f"""
"use strict";
let SEL = ".";
let FOLDER = null;
const BASEHASH = new Map();
const HDR = {{}};
const renderPanelCalls = [];
function renderPanel(tab) {{ renderPanelCalls.push(FOLDER.rel); }}
function setStatus() {{}}
const document = {{querySelectorAll: () => ({{forEach: () => {{}}}})}};

// api() resolves folder "slow" AFTER folder "fast" — simulating a slow first
// click whose response arrives after a fast second click has already landed.
function api(path) {{
  const label = decodeURIComponent(path.split("rel=")[1]);
  const delay = label === "slow" ? 30 : 5;
  return new Promise((resolve) => setTimeout(
    () => resolve({{status: 200, body: {{rel: label, hash: "h-" + label}}}}), delay));
}}

{select_src}

(async () => {{
  const p1 = select("slow", null);   // fired first, resolves LAST
  const p2 = select("fast", null);   // fired second, resolves FIRST
  await Promise.all([p1, p2]);
  if (SEL !== "fast") {{ console.error("SEL clobbered:", SEL); process.exit(1); }}
  if (FOLDER.rel !== "fast") {{ console.error("FOLDER clobbered:", FOLDER.rel); process.exit(1); }}
  if (renderPanelCalls.includes("slow")) {{
    console.error("stale response was rendered:", renderPanelCalls); process.exit(1);
  }}
  console.log("ok");
}})();
"""
    _run_node(tmp_path, harness)
