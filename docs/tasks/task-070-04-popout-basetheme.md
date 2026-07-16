# TASK 070-04 — [R-070-6] Popout highlight via EditorView.baseTheme

**Goal:** the highlight persists in every open document. One line, not thirty.

**Context:** `skills/obsidian-cli/plugin/agent-bridge/main.ts:197-201`. Design: `design-popout-fix.md`.

**Steps**
1. Add `const persistSelectionTheme = EditorView.baseTheme({ [".${PERSIST_SELECTION_CLASS}"]: { backgroundColor: "var(--text-selection)" } });` (`EditorView` is already imported).
2. `this.registerEditorExtension([persistSelectionExtension, persistSelectionTheme]);`
3. **Delete** the `document.createElement("style")` block **and** `this.register(() => style.remove())` — CM6 mounts per view root; cleanup is `registerEditorExtension`'s job; dedup is structural (`style-mod.js:82`).
4. **`window-open`/`iterateAllLeaves` is REJECTED** — ~30 lines and four failure modes for a one-line fix that has none.

**Verification — read the parametrisation BEFORE you panic.** The design's test file is
`@parametrize("src_path", [_MAIN_JS, _MAIN_TS])`, so each test runs **twice**. This bead patches
`main.ts` only — `main.js` is still the hand-authored mirror until 070-05 regenerates it. So the
**correct state here is `[main.ts]` GREEN, `[main.js]` RED.** That RED is expected; the suite is red
across beads 02→05 by design (PLAN §0) and nothing depends on a green suite in that window.

> 🛑 **DO NOT hand-patch `main.js` to clear it.** `design-popout-fix.md` §"Exact code" offers a
> ready-made `main.js` patch. Taking it is the hand-mirror discipline that 070-02 makes a **gate
> violation** and 070-07 deletes from the README. If the RED is intolerable, land the test file in
> 070-05 instead — never hand-edit the build product.

Tests: **2 surviving** — `test_highlight_css_is_a_cm6_base_theme`,
`test_highlight_css_never_injected_into_one_document`. **Do NOT copy the other two**: the destructure test is moot post-070-05 (esbuild always emits the require), and `test_main_js_loads_under_plain_require` goes RED (obsidian pkg `"main": ""` — types-only).
