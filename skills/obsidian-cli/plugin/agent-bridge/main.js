"use strict";
var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __export = (target, all) => {
  for (var name in all)
    __defProp(target, name, { get: all[name], enumerable: true });
};
var __copyProps = (to, from, except, desc) => {
  if (from && typeof from === "object" || typeof from === "function") {
    for (let key of __getOwnPropNames(from))
      if (!__hasOwnProp.call(to, key) && key !== except)
        __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
  }
  return to;
};
var __toCommonJS = (mod) => __copyProps(__defProp({}, "__esModule", { value: true }), mod);

// main.ts
var main_exports = {};
__export(main_exports, {
  default: () => AgentBridge
});
module.exports = __toCommonJS(main_exports);
var import_obsidian = require("obsidian");
var import_view = require("@codemirror/view");
var AGENT_DIR = ".obsidian";
var REQUEST_FILE = `${AGENT_DIR}/agent-request.json`;
var EDIT_FILE = `${AGENT_DIR}/agent-edit.json`;
var SELECTION_FILE = `${AGENT_DIR}/agent-selection.json`;
var CONTEXT_FILE = `${AGENT_DIR}/agent-context.json`;
var RESULT_FILE = `${AGENT_DIR}/agent-result.json`;
function decodeB64Utf8(b64) {
  const binary = atob(b64);
  const bytes = Uint8Array.from(binary, (c) => c.charCodeAt(0));
  return new TextDecoder("utf-8").decode(bytes);
}
var PERSIST_SELECTION_CLASS = "agent-persist-selection";
var persistSelectionMark = import_view.Decoration.mark({ class: PERSIST_SELECTION_CLASS });
var persistSelectionTheme = import_view.EditorView.baseTheme({
  [`.${PERSIST_SELECTION_CLASS}`]: { backgroundColor: "var(--text-selection)" }
});
var persistSelectionExtension = import_view.ViewPlugin.fromClass(
  class {
    constructor(view) {
      this.decorations = this.build(view);
    }
    update(u) {
      if (u.selectionSet || u.focusChanged || u.docChanged || u.viewportChanged) {
        this.decorations = this.build(u.view);
      }
    }
    build(view) {
      if (view.hasFocus) return import_view.Decoration.none;
      const marks = [];
      for (const r of view.state.selection.ranges) {
        if (!r.empty) marks.push(persistSelectionMark.range(r.from, r.to));
      }
      return import_view.Decoration.set(marks);
    }
  },
  { decorations: (v) => v.decorations }
);
var AgentBridge = class extends import_obsidian.Plugin {
  constructor() {
    super(...arguments);
    /**
     * The most-recently-ACTIVE markdown view. Load-bearing, not a nicety: when the agent types
     * in Obsidian's own INTEGRATED TERMINAL — the very scenario this plugin exists for — that
     * terminal is the active leaf, so `app.workspace.activeEditor` is **null** (live-verified:
     * `activeLeafType: "terminal:terminal"`, `activeEditor: null`, while the note's editor still
     * holds the selection). We therefore remember the last markdown editor and fall back to it,
     * mirroring the `recent-open` fallback in `obsidian_active_note.py` (TASK 041 / ADR-008),
     * which exists for exactly this reason.
     */
    this.lastEditor = null;
  }
  /** Last-resort net for a command that threw outside its own typed-result handling. */
  reportCrash(command, err) {
    new import_obsidian.Notice(`agent-bridge: ${command} failed \u2014 see the console`);
    console.error(`agent-bridge: ${command} threw`, err);
  }
  /**
   * Remember the active markdown view. ONLY a `MarkdownView` is worth remembering: `isAttached`
   * proves liveness by identity against the markdown leaf list, whose `view` IS the
   * `MarkdownView` (`WorkspaceLeaf.view: View`), so any other `MarkdownFileInfo` could never
   * pass it — it would be dead state that ALSO evicts a usable memory in `resolveEditor`.
   */
  rememberEditor() {
    const ae = this.app.workspace.activeEditor;
    if (ae instanceof import_obsidian.MarkdownView && ae.editor && ae.file) this.lastEditor = ae;
  }
  /**
   * The view to act on, or a typed reason why not: the ACTIVE markdown view, else the remembered
   * one (when the active leaf is the integrated terminal / a Bases view / settings). `source`
   * records which — the caller surfaces it so a fallback resolve is visible, never silent.
   *
   * Resolution and the mode gate live together because "an editor we may safely act on" is ONE
   * question: mode is knowable only on a `MarkdownView` (`getMode()` is a `MarkdownView` member,
   * NOT a `MarkdownFileInfo` one), so a resolver handing back a bare `MarkdownFileInfo` forces
   * every caller into the `getMode?.()` fail-open this bead exists to delete.
   */
  /**
   * The view to act on, or a typed reason why not — WITHOUT the preview mode-gate. This is the
   * shared core of `resolveEditor`: the active markdown view, else the remembered one. Callers
   * that must reject preview (the apply write-path) go through `resolveEditor`; callers that
   * tolerate it (read-only `export-context`) use this directly and branch on `getMode()`.
   */
  resolveView() {
    let view;
    let source;
    const active = this.app.workspace.activeEditor;
    if (active) {
      if (!(active instanceof import_obsidian.MarkdownView)) return { ok: false, reason: "unsupported-view" };
      view = active;
      source = "active";
    } else {
      const last = this.lastEditor;
      if (!last || !last.editor || !last.file || !this.isAttached(last)) {
        if (last && !this.isAttached(last)) this.lastEditor = null;
        return { ok: false, reason: "no-editor" };
      }
      view = last;
      source = "recent-editor";
    }
    const editor = view.editor;
    const file = view.file;
    if (!editor || !file) return { ok: false, reason: "no-editor" };
    return { ok: true, view, editor, file, source };
  }
  resolveEditor() {
    const resolved = this.resolveView();
    if (!resolved.ok) return resolved;
    if (resolved.view.getMode() === "preview") return { ok: false, reason: "preview" };
    return resolved;
  }
  /**
   * Is the remembered view still attached to a live markdown leaf? Load-bearing: closing the
   * note leaves a DETACHED view that still answers `.editor` and `.file` and still holds its old
   * selection — so both apply guards would pass and we could write into a note the human closed
   * (or mirror `ok:true` for a save that silently no-ops, defeating the wrapper's
   * success-is-shape contract). Identity against the live leaf list is the only honest check.
   */
  isAttached(view) {
    return this.app.workspace.getLeavesOfType("markdown").some((leaf) => leaf.view === view);
  }
  async onload() {
    this.addCommand({
      id: "export-selection",
      name: "Export selection",
      callback: () => {
        this.exportSelection().catch((e) => this.reportCrash("export-selection", e));
      }
    });
    this.addCommand({
      id: "apply-edit",
      name: "Apply edit",
      callback: () => {
        this.applyEdit().catch((e) => this.reportCrash("apply-edit", e));
      }
    });
    this.addCommand({
      id: "copy-selection-ref",
      name: "Copy selection reference (for the shell agent)",
      callback: () => {
        this.copySelectionRef().catch((e) => this.reportCrash("copy-selection-ref", e));
      }
    });
    this.addCommand({
      id: "export-context",
      name: "Export note context",
      callback: () => {
        this.exportContext().catch((e) => this.reportCrash("export-context", e));
      }
    });
    this.registerEvent(this.app.workspace.on("active-leaf-change", () => this.rememberEditor()));
    this.app.workspace.onLayoutReady(() => this.rememberEditor());
    this.registerEditorExtension([persistSelectionExtension, persistSelectionTheme]);
  }
  /**
   * Put a selection capture on the clipboard for the human to paste into an agent's shell:
   *
   *     @<vault-relative-path>#L<from>-<to>
   *     <the exact selected text, verbatim>
   *
   * Line 1 is a `@file#L…` LOCATION (which file, and the 1-based inclusive line range — for
   * context and as the file to edit). Everything after the first newline is the EXACT selected
   * text. Both are needed because a line reference alone is line-GRANULAR: a sub-line selection
   * (a substring within a line) would expand to the whole line when the agent reads by line, so
   * the verbatim selection is what pins the precise target (and the agent's edit `old_string`).
   *
   * Clipboard-only — no vault I/O, no `.obsidian/` files, nothing an agent can trigger; the only
   * side effect is overwriting the clipboard, and it runs solely from a human hotkey gesture. The
   * captured text is untrusted content (H-6) for the consuming agent. Never throws to the
   * dispatcher; gives feedback via a Notice.
   */
  async copySelectionRef() {
    const resolved = this.resolveEditor();
    if (!resolved.ok) {
      new import_obsidian.Notice(`agent-bridge: cannot capture the selection (${resolved.reason})`);
      return;
    }
    const { editor, file } = resolved;
    if (!editor.somethingSelected()) {
      new import_obsidian.Notice("agent-bridge: nothing selected");
      return;
    }
    const from = editor.getCursor("from");
    const to = editor.getCursor("to");
    const fromLine = from.line + 1;
    const toLine = to.ch === 0 && to.line > from.line ? to.line : to.line + 1;
    const loc = fromLine === toLine ? `L${fromLine}` : `L${fromLine}-${toLine}`;
    const selection = editor.getRange(from, to);
    const payload = `@${file.path}#${loc}
${selection}`;
    try {
      await navigator.clipboard.writeText(payload);
    } catch (_err) {
      new import_obsidian.Notice("agent-bridge: could not write to the clipboard");
      return;
    }
    new import_obsidian.Notice(`Copied selection @${file.path}#${loc} (+ exact text)`);
  }
  async readNonce(file) {
    try {
      const raw = await this.app.vault.adapter.read(file);
      const parsed = JSON.parse(raw);
      return typeof parsed.nonce === "string" ? parsed.nonce : "";
    } catch (_err) {
      return "";
    }
  }
  /** Written LAST on every branch so the wrapper's nonce read-back poll never observes
   * a half-written outcome. */
  async writeResult(payload) {
    await this.app.vault.adapter.write(RESULT_FILE, JSON.stringify(payload));
  }
  async exportSelection() {
    const nonce = await this.readNonce(REQUEST_FILE);
    const resolved = this.resolveEditor();
    if (!resolved.ok) {
      await this.writeResult({ ok: false, reason: resolved.reason, nonce });
      return;
    }
    const { editor, file, source } = resolved;
    if (!editor.somethingSelected()) {
      await this.writeResult({ ok: false, reason: "empty-selection", nonce });
      return;
    }
    const from = editor.getCursor("from");
    const to = editor.getCursor("to");
    const selection = {
      vault: this.app.vault.getName(),
      path: file.path,
      from,
      to,
      fromOffset: editor.posToOffset(from),
      toOffset: editor.posToOffset(to),
      text: editor.getRange(from, to),
      mtime: file.stat.mtime,
      exportedAt: Date.now(),
      // "active" = the focused editor; "recent-editor" = resolved via the fallback because the
      // active leaf was not a markdown editor (typically the agent's integrated terminal). The
      // wrapper surfaces this so a fallback resolve is visible to the caller, never silent.
      source,
      nonce
    };
    await this.app.vault.adapter.write(SELECTION_FILE, JSON.stringify(selection));
    await this.writeResult({ ok: true, mode: "read", nonce });
  }
  async applyEdit() {
    let editPayload;
    try {
      const raw = await this.app.vault.adapter.read(EDIT_FILE);
      editPayload = JSON.parse(raw);
    } catch (_err) {
      await this.writeResult({ ok: false, reason: "bad-payload", nonce: "" });
      return;
    }
    const nonce = editPayload.nonce;
    let expect;
    let replacement;
    try {
      expect = decodeB64Utf8(editPayload.expectB64);
      replacement = decodeB64Utf8(editPayload.replacementB64);
    } catch (_err) {
      await this.writeResult({ ok: false, reason: "bad-payload", nonce });
      return;
    }
    const resolved = this.resolveEditor();
    if (!resolved.ok) {
      await this.writeResult({ ok: false, reason: resolved.reason, nonce });
      return;
    }
    const { view, editor, file } = resolved;
    if (!editor.somethingSelected()) {
      await this.writeResult({ ok: false, reason: "empty-selection", nonce });
      return;
    }
    const from = editor.getCursor("from");
    const to = editor.getCursor("to");
    if (editPayload.path !== file.path) {
      await this.writeResult({ ok: false, reason: "path-mismatch", nonce });
      return;
    }
    if (editor.posToOffset(from) !== editPayload.fromOffset || editor.posToOffset(to) !== editPayload.toOffset) {
      await this.writeResult({ ok: false, reason: "position-mismatch", nonce });
      return;
    }
    if (editor.getRange(from, to) !== expect) {
      await this.writeResult({ ok: false, reason: "stale-range", nonce });
      return;
    }
    try {
      editor.replaceRange(replacement, from, to);
      await view.save();
    } catch (_err) {
      await this.writeResult({ ok: false, reason: "save-failed", nonce });
      return;
    }
    await this.writeResult({ ok: true, mode: "apply", newLen: replacement.length, nonce });
  }
  async exportContext() {
    var _a, _b;
    const req = await this.readRequest(REQUEST_FILE);
    const nonce = typeof req.nonce === "string" ? req.nonce : "";
    const includeOutline = !!req.includeOutline;
    const includeFrontmatter = !!req.includeFrontmatter;
    const includeSelection = !!req.includeSelection;
    const resolved = this.resolveView();
    if (!resolved.ok) {
      await this.writeResult({ ok: false, reason: resolved.reason, nonce });
      return;
    }
    const { view, editor, file, source } = resolved;
    const fileCache = this.app.metadataCache.getFileCache(file);
    const isSource = view.getMode() === "source";
    const parentPath = (_b = (_a = file.parent) == null ? void 0 : _a.path) != null ? _b : "";
    const folder = parentPath === "/" ? "" : parentPath;
    const context = {
      vault: this.app.vault.getName(),
      path: file.path,
      folder,
      mtime: file.stat.mtime,
      exportedAt: Date.now(),
      // The editor's view mode. Named `editorMode`, NOT `mode`, to avoid colliding with the
      // wrapper envelope's operation `mode` ("context") when the wrapper carries these fields
      // through. "source" = an editable editor; "preview" = the note is being READ (cursor/
      // selection absent).
      editorMode: isSource ? "source" : "preview",
      // "active" = the focused editor; "recent-editor" = the fallback (the active leaf was not a
      // markdown editor — typically the agent's integrated terminal). Surfaced so a fallback
      // resolve is visible, never silent.
      source,
      nonce
    };
    if (isSource) {
      const cursor = editor.getCursor();
      context.cursor = { line: cursor.line, ch: cursor.ch };
      context.cursorOffset = editor.posToOffset(cursor);
      let currentHeading = "";
      let currentLevel = 0;
      if (fileCache == null ? void 0 : fileCache.headings) {
        for (const h of fileCache.headings) {
          if (h.position.start.line <= cursor.line) {
            currentHeading = h.heading;
            currentLevel = h.level;
          } else {
            break;
          }
        }
      }
      context.heading = currentHeading;
      context.headingLevel = currentLevel;
      if (includeSelection && editor.somethingSelected()) {
        const from = editor.getCursor("from");
        const to = editor.getCursor("to");
        context.selection = {
          from,
          to,
          fromOffset: editor.posToOffset(from),
          toOffset: editor.posToOffset(to),
          text: editor.getRange(from, to)
        };
      }
    }
    if (includeOutline && (fileCache == null ? void 0 : fileCache.headings)) {
      context.outline = fileCache.headings.map((h) => ({
        level: h.level,
        heading: h.heading,
        line: h.position.start.line
      }));
    }
    if (fileCache) {
      const allTags = (0, import_obsidian.getAllTags)(fileCache);
      if (allTags && allTags.length) {
        context.tags = allTags.map((t) => t.startsWith("#") ? t.slice(1) : t);
      }
    }
    if (includeFrontmatter && (fileCache == null ? void 0 : fileCache.frontmatter)) {
      context.frontmatter = fileCache.frontmatter;
    }
    await this.app.vault.adapter.write(CONTEXT_FILE, JSON.stringify(context));
    await this.writeResult({ ok: true, mode: "context", nonce });
  }
  async readRequest(file) {
    try {
      const raw = await this.app.vault.adapter.read(file);
      return JSON.parse(raw);
    } catch (_err) {
      return { nonce: "" };
    }
  }
};
