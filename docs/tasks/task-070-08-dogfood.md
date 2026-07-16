# TASK 070-08 — [AC] LIVE DOGFOOD — the only gate that can actually fail

**Goal:** prove the regenerated plugin runs. H2 means **no suite covers the plugin**; `main.js` is a **new artifact**. Nothing in 070-01..07 proves it loads.

**Context:** the user's real Obsidian (1.12.7 / Electron 39.8.3). Install = copy `manifest.json` + `main.js` into `<vault>/.obsidian/plugins/agent-bridge/`, reload.

**Steps (from the INTEGRATED terminal — the scenario the feature exists for)**
1. `obsidian-selection read` with text selected → returns the selection (`source: active|recent-editor`).
2. `obsidian-selection apply …` → writes back; guards refuse a moved/edited selection.
3. **`read` inside a POPOUT window** → closes **OQ-070-4** (`instanceof` across window realms is UNVERIFIED — Obsidian ships `Node.instanceOf<T>()` precisely because plain `instanceof` fails across realms). **Do not close this by argument.**
4. Popout shows the **persisted highlight** (R-070-6).
5. **`copy-selection-ref`** still behaves — the third consumer; R-070-5 changes it (it had no preview guard and copied stale source-mode text under a confident label).
6. Optional, cheap — **OQ-070-3**: `minAppVersion: "99.0.0"` → reload → confirm Obsidian **refuses to load**. Until run, R-070-2's runtime half is documentation-grade.

**Verification** — all six observed by the user. Any failure ⇒ the plugin does not ship; regenerating `main.js` changed the executed artifact and only this step can see it.
