# TASK 070-08 — [AC] LIVE DOGFOOD — the only gate that can actually fail

**Goal:** prove the regenerated plugin runs. H2 means **no suite covers the plugin**; `main.js` is a **new artifact**. Nothing in 070-01..07 proves it loads.

**Context:** the user's real Obsidian (1.12.7 / Electron 39.8.3). Install = copy `manifest.json` + `main.js` into `<vault>/.obsidian/plugins/agent-bridge/`, reload.

**Steps (from the INTEGRATED terminal — the scenario the feature exists for)**
1. `obsidian-selection read` with text selected → returns the selection (`source: active|recent-editor`).
2. `obsidian-selection apply …` → writes back; guards refuse a moved/edited selection.
3. **`read` inside a POPOUT window** → closes **OQ-070-4** (`instanceof` across window realms is UNVERIFIED — Obsidian ships `instanceOf<T>()` precisely because plain `instanceof` fails across realms). **Do not close this by argument.**

   > **⚠️ The stake ROSE in 070-03, and this step is now a REGRESSION gate, not just a new check.**
   > Before 070, `instanceof MarkdownView` existed only on the `apply` path. `resolveEditor` now runs it
   > for **all three** commands, so if it failed across realms, `read` in a popout would newly return
   > `unsupported-view` — a capability that works today.
   >
   > **Evidence that lowers the prior (NOT closure):** the real typings declare `instanceOf<T>()` on
   > **`Node`** — `node_modules/obsidian/obsidian.d.ts:62` — documented as *"a drop-in replacement for
   > instanceof checks on **DOM Nodes**"*. The per-realm hazard is a property of **DOM** classes; a
   > popout gets its own `document`, hence its own `HTMLElement`. `MarkdownView` is one of Obsidian's own
   > classes from a single app bundle, and the view objects in a popout are constructed by that same
   > bundle — so the class identity should hold. **This is still an inference from a `.d.ts` about
   > runtime behaviour, which is precisely the reasoning TASK 070 exists to distrust.** Run the step.
4. Popout shows the **persisted highlight** (R-070-6).
5. **`copy-selection-ref`** still behaves — the third consumer; R-070-5 changes it (it had no preview guard and copied stale source-mode text under a confident label).
6. Optional, cheap — **OQ-070-3**: `minAppVersion: "99.0.0"` → reload → confirm Obsidian **refuses to load**. Until run, R-070-2's runtime half is documentation-grade.

**Verification** — all six observed by the user. Any failure ⇒ the plugin does not ship; regenerating `main.js` changed the executed artifact and only this step can see it.

---

## RESULTS (2026-07-16)

Installed at `/Users/sergey/Downloads/TestVault/ObsidianNotes-Test/.obsidian/plugins/agent-bridge/`.
`main.js` = `4cd48e5d…`, **12,668 B — byte-identical to the repo's build**, `minAppVersion: 1.12.3`.
The drift gate is what makes that statement checkable rather than assumed.

| # | Step | Result |
|---|---|---|
| 1 | `read` from the **integrated terminal**, main window | ✅ returned the selection (user-run) |
| 3 | **`read` in a POPOUT** | ✅ **`ok:true`, `source:"active"`** — see below |
| 2 | `apply` write-back | ⬜ not run |
| 4 | popout persists the **highlight** (R-070-6) | ⬜ not run — visual, human-only |
| 5 | `copy-selection-ref` | ⬜ not run |
| 6 | OQ-070-3 `minAppVersion` refusal | ⬜ not run (but 1.12.3 demonstrably did **not** block load on the 1.12.7 app) |

### ★ OQ-070-4 — **CLOSED by observation**

Popout read returned `{"ok": true, …, "source": "active", "from": {"line": 28, "ch": 100}}`.

`source: "active"` is the load-bearing evidence: `activeEditor` was **not null**, so resolution took the
`if (active)` branch and evaluated `!(active instanceof MarkdownView)` against a view whose DOM lives in
a **popout window's realm** — and it passed. **Plain `instanceof MarkdownView` holds across window
realms.** The prior reasoning (Obsidian declares `instanceOf<T>()` on `Node`, i.e. for *DOM* classes,
while `MarkdownView` comes from the single app bundle) was correct — but it is now *observed*, which is
the only currency this task accepts. This also retires the regression R-070-5 introduced: `resolveEditor`
runs `instanceof` for all three commands where pre-070 only `apply` did.

Run from an **external** shell (VS Code), which is why `source` is `active` rather than `recent-editor` —
the note stays Obsidian's active leaf. That is the same asymmetry TASK 068's OQ1 hit.

### ★ The diagonal — **CLOSED by observation**, and self-evidencing

**Integrated terminal + popout** — the scenario the plugin exists for, and the one neither earlier run
touched (run 1 = `recent-editor` in the **main window**; run 3 = `active` in a **popout**). Two halves
do not compose into it: it is the only path where `activeEditor` is null **and** the remembered view
lives in another window, so `isAttached()` must ask whether `getLeavesOfType("markdown")` **includes
popout leaves**. If it does not, the view reads as detached, `lastEditor` is nulled, and the read
returns `no-editor`.

**Method — the test carries its own proof, so no testimony about window state is needed.** A probe note
`_popout-probe.md` containing the unique sentinel `POPOUT-PROBE-7f3a91c2` was created and then moved to
a popout via *Move to new window*, so the note existed **only** in that popout. Result, from the
integrated terminal:

```
source = recent-editor | line 0 | POPOUT-PROBE-7f3a91c2 — эта строка живёт
```

Three independent facts in one line: `recent-editor` ⇒ `activeEditor` was null (the `else` branch ran);
the sentinel ⇒ the resolved leaf **was** the popout's, because the string exists nowhere else; therefore
`isAttached()` returned true ⇒ **`getLeavesOfType("markdown")` includes popout leaves**. It also proves
`rememberEditor` retained the popout view in the first place (its `ae instanceof MarkdownView` passed) —
the second necessary link.

**Why it was designed this way.** The preceding attempt returned `source: "recent-editor"` with correct
text and *looked* like a pass — but nothing in the envelope distinguished "resolved the popout's view"
from "resolved a main-window view", so it rested on the operator's recollection of which window held the
note. A sentinel that can only come from one place removes the human from the evidence chain. The
`probe = False` branch would have caught the `lastEditor`-points-at-the-wrong-window case — the silent
wrong-target that R-070-5 was written against, and which every prior run was blind to.

*(The probe note was deleted after the run.)*
