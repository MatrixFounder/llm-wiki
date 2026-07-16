"use strict";

// agent-bridge — hand-authored CommonJS mirror of main.ts (TASK 068 / R-068-1/R-068-2).
// Obsidian plugins are plain CommonJS — no bundler required. Keep this file in lockstep
// with main.ts by hand; see README.md's "rebuild before commit" discipline.
//
// NOTE (intentional divergence from main.ts, documented here so it isn't mistaken for
// drift): main.ts resolves "obsidian" as a compile-time-only ambient module (our vendored
// obsidian.d.ts) — it never actually requires anything at runtime beyond what Obsidian
// itself provides. This main.js DOES run under plain `require`, including in the TC-03
// smoke test (`node -e "require('./main.js')"`) which executes outside the real Obsidian
// process, where the "obsidian" module does not resolve. The try/catch below falls back to
// an inert stand-in ONLY for that offline-load case; inside the real Obsidian app the
// require always succeeds and this behaves exactly like a plain `const { Plugin } =
// require("obsidian")`.
let Plugin;
let Notice;
let MarkdownView;
try {
  ({ Plugin, Notice, MarkdownView } = require("obsidian"));
} catch (err) {
  Plugin = class {};
  MarkdownView = class {};
  Notice = class {
    constructor(message) {
      void message;
    }
  };
}

// CodeMirror 6 (for the persist-selection ViewPlugin). Obsidian provides these at runtime;
// the try/catch fallback is ONLY for the offline `node -e require('./main.js')` smoke test
// (they don't resolve outside Obsidian). Inert stand-ins keep module load from crashing there.
let Decoration, ViewPlugin;
try {
  ({ Decoration, ViewPlugin } = require("@codemirror/view"));
} catch (err) {
  Decoration = { mark: () => ({ range: () => ({}) }), set: () => ({}), none: {} };
  ViewPlugin = { fromClass: () => ({}) };
}

const AGENT_DIR = ".obsidian";
const REQUEST_FILE = `${AGENT_DIR}/agent-request.json`;
const EDIT_FILE = `${AGENT_DIR}/agent-edit.json`;
const SELECTION_FILE = `${AGENT_DIR}/agent-selection.json`;
const RESULT_FILE = `${AGENT_DIR}/agent-result.json`;

// Decode a base64 string to UTF-8 text -- NEVER bare `atob` (ground-truth fact #6: `atob`
// alone recovers only the raw BYTES as a Latin-1-per-char binary string, which mangles
// anything outside Latin-1, e.g. Cyrillic). Uint8Array + TextDecoder correctly
// reinterpret those bytes as UTF-8.
function decodeB64Utf8(b64) {
  const binary = atob(b64);
  const bytes = Uint8Array.from(binary, (c) => c.charCodeAt(0));
  return new TextDecoder("utf-8").decode(bytes);
}

// Persist the selection highlight when the editor is unfocused (CM6 removes its own selection
// layer on blur, so pure CSS can't do it). Re-draws the selection as a mark decoration when
// the editor is NOT focused; yields to CM's native selection when it IS. Mirrors main.ts.
const PERSIST_SELECTION_CLASS = "agent-persist-selection";
const persistSelectionMark = Decoration.mark({ class: PERSIST_SELECTION_CLASS });
const persistSelectionExtension = ViewPlugin.fromClass(
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
      if (view.hasFocus) return Decoration.none;
      const marks = [];
      for (const r of view.state.selection.ranges) {
        if (!r.empty) marks.push(persistSelectionMark.range(r.from, r.to));
      }
      return Decoration.set(marks);
    }
  },
  { decorations: (v) => v.decorations }
);

class AgentBridge extends Plugin {
  // The most-recently-ACTIVE markdown editor. Load-bearing: when the agent types in Obsidian's
  // own INTEGRATED TERMINAL (the scenario this plugin exists for), that terminal is the active
  // leaf and `app.workspace.activeEditor` is NULL — live-verified — while the note's editor
  // still holds the selection. Mirrors obsidian_active_note.py's `recent-open` fallback.
  lastEditor = null;

  // Last-resort net for a command that threw outside its own typed-result handling.
  reportCrash(command, err) {
    new Notice(`agent-bridge: ${command} failed — see the console`);
    console.error(`agent-bridge: ${command} threw`, err);
  }

  // Remember the active markdown editor; never overwrite it with a non-editor leaf.
  rememberEditor() {
    const ae = this.app.workspace.activeEditor;
    if (ae && ae.editor && ae.file) this.lastEditor = ae;
  }

  // Is the remembered editor still attached to a live markdown leaf? A CLOSED note leaves a
  // detached view that still answers .editor/.file and holds its old selection — both apply
  // guards would pass and we could write into a note the human closed. Mirrors main.ts.
  isAttached(info) {
    return this.app.workspace.getLeavesOfType("markdown").some((leaf) => leaf.view === info);
  }

  // Active markdown editor, else the remembered one (active leaf = terminal / Bases / settings).
  // `source` records which, so a fallback resolve is visible to the caller, never silent.
  resolveEditor() {
    const active = this.app.workspace.activeEditor;
    if (active && active.editor && active.file) {
      return { ed: active, editor: active.editor, file: active.file, source: "active" };
    }
    const last = this.lastEditor;
    if (last && last.editor && last.file && this.isAttached(last)) {
      return { ed: last, editor: last.editor, file: last.file, source: "recent-editor" };
    }
    if (last && !this.isAttached(last)) this.lastEditor = null; // drop a dangling reference
    return null;
  }

  async onload() {
    // `.catch()` on every dispatch: a command callback is fire-and-forget, so an unhandled
    // rejection would vanish into the console and leave the wrapper polling to its deadline.
    // Each handler mirrors its own typed result; this is the last-resort net. Mirrors main.ts.
    this.addCommand({
      id: "export-selection",
      name: "Export selection",
      callback: () => {
        this.exportSelection().catch((e) => this.reportCrash("export-selection", e));
      },
    });
    this.addCommand({
      id: "apply-edit",
      name: "Apply edit",
      callback: () => {
        this.applyEdit().catch((e) => this.reportCrash("apply-edit", e));
      },
    });
    this.addCommand({
      id: "copy-selection-ref",
      name: "Copy selection reference (for the shell agent)",
      callback: () => {
        this.copySelectionRef().catch((e) => this.reportCrash("copy-selection-ref", e));
      },
    });

    // Track the last active markdown editor so the commands still work when the agent's
    // integrated terminal is the active leaf (activeEditor === null there). Mirrors main.ts.
    this.registerEvent(this.app.workspace.on("active-leaf-change", () => this.rememberEditor()));
    this.app.workspace.onLayoutReady(() => this.rememberEditor());

    // Keep the selection visible when the editor is unfocused (mirrors main.ts).
    this.registerEditorExtension(persistSelectionExtension);
    const style = document.createElement("style");
    style.textContent = `.${PERSIST_SELECTION_CLASS} { background-color: var(--text-selection); }`;
    document.head.appendChild(style);
    this.register(() => style.remove());
  }

  // Put `@<path>#L<from>-<to>\n<exact selected text>` on the clipboard: line 1 is the file:line
  // LOCATION, everything after the first newline is the EXACT selected text (a line ref alone is
  // line-granular and expands a sub-line selection to whole lines). Clipboard-only — no vault
  // I/O; runs solely from a human hotkey gesture; captured text is untrusted (H-6). Mirrors main.ts.
  async copySelectionRef() {
    const resolved = this.resolveEditor();
    if (!resolved) {
      new Notice("agent-bridge: no active editor");
      return;
    }
    const { editor, file } = resolved;
    if (!editor.somethingSelected()) {
      new Notice("agent-bridge: nothing selected");
      return;
    }
    const from = editor.getCursor("from");
    const to = editor.getCursor("to");
    const fromLine = from.line + 1;
    const toLine = to.ch === 0 && to.line > from.line ? to.line : to.line + 1;
    const loc = fromLine === toLine ? `L${fromLine}` : `L${fromLine}-${toLine}`;
    const selection = editor.getRange(from, to);
    const payload = `@${file.path}#${loc}\n${selection}`;
    try {
      await navigator.clipboard.writeText(payload);
    } catch (err) {
      new Notice("agent-bridge: could not write to the clipboard");
      return;
    }
    new Notice(`Copied selection @${file.path}#${loc} (+ exact text)`);
  }

  async readNonce(file) {
    try {
      const raw = await this.app.vault.adapter.read(file);
      const parsed = JSON.parse(raw);
      // Normalize: the file is unsigned, so `nonce` may be absent, null, or a number. Anything
      // non-string becomes "" (fail-closed — never matches the wrapper's uuid4). Mirrors main.ts.
      return typeof parsed.nonce === "string" ? parsed.nonce : "";
    } catch (err) {
      return "";
    }
  }

  // Written LAST on every branch so the wrapper's nonce read-back poll never observes a
  // half-written outcome.
  async writeResult(payload) {
    await this.app.vault.adapter.write(RESULT_FILE, JSON.stringify(payload));
  }

  async exportSelection() {
    const nonce = await this.readNonce(REQUEST_FILE);
    const resolved = this.resolveEditor();
    if (!resolved) {
      await this.writeResult({ ok: false, reason: "no-editor", nonce });
      return;
    }
    const { ed, editor, file, source } = resolved;
    if (ed.getMode && ed.getMode() === "preview") {
      await this.writeResult({ ok: false, reason: "preview", nonce });
      return;
    }
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
      // "active" = focused editor; "recent-editor" = resolved via the fallback (active leaf was
      // not a markdown editor — typically the agent's integrated terminal). Mirrors main.ts.
      source,
      nonce,
    };
    await this.app.vault.adapter.write(SELECTION_FILE, JSON.stringify(selection));
    await this.writeResult({ ok: true, mode: "read", nonce });
  }

  async applyEdit() {
    let editPayload;
    try {
      const raw = await this.app.vault.adapter.read(EDIT_FILE);
      editPayload = JSON.parse(raw);
    } catch (err) {
      // The reason is `bad-payload`, NOT `no-editor` — there may well be an editor; it is the
      // PAYLOAD that was unreadable. We cannot echo a nonce we could not read, so the wrapper
      // times out on its own deadline (exit 4), but the reason on disk stays honest.
      await this.writeResult({ ok: false, reason: "bad-payload", nonce: "" });
      return;
    }
    const nonce = editPayload.nonce;
    // Decode INSIDE a try/catch so a malformed/missing base64 payload writes a typed
    // refusal instead of throwing to the dispatcher (mirrors main.ts — preserves the
    // "never throws, always mirrors a typed result" invariant; agent-edit.json is unsigned).
    let expect;
    let replacement;
    try {
      expect = decodeB64Utf8(editPayload.expectB64);
      replacement = decodeB64Utf8(editPayload.replacementB64);
    } catch (err) {
      await this.writeResult({ ok: false, reason: "bad-payload", nonce });
      return;
    }

    const resolved = this.resolveEditor();
    if (!resolved) {
      await this.writeResult({ ok: false, reason: "no-editor", nonce });
      return;
    }
    const { ed, editor, file } = resolved;
    if (ed.getMode && ed.getMode() === "preview") {
      await this.writeResult({ ok: false, reason: "preview", nonce });
      return;
    }
    if (!editor.somethingSelected()) {
      await this.writeResult({ ok: false, reason: "empty-selection", nonce });
      return;
    }
    // save() is NOT on MarkdownFileInfo — it comes from TextFileView via MarkdownView (verified
    // against the real obsidian typings; MarkdownEditView implements MarkdownFileInfo WITHOUT
    // save). Narrow BEFORE mutating: an unsaveable editor must be a typed refusal, never a
    // TypeError raised after replaceRange already changed the buffer. Mirrors main.ts.
    if (!(ed instanceof MarkdownView)) {
      await this.writeResult({ ok: false, reason: "no-saveable-view", nonce });
      return;
    }

    // Derive the coordinates from the LIVE selection at apply time (load-bearing --
    // never source from/to from the payload; the payload carries no from/to at all, by
    // design, so GUARD 2 below is never tautological).
    const from = editor.getCursor("from");
    const to = editor.getCursor("to");

    // GUARD 1
    if (editPayload.path !== file.path) {
      await this.writeResult({ ok: false, reason: "path-mismatch", nonce });
      return;
    }
    // GUARD 2
    if (editor.getRange(from, to) !== expect) {
      await this.writeResult({ ok: false, reason: "stale-range", nonce });
      return;
    }

    // The mutate → save → mirror tail must never leave the buffer edited with NO result
    // mirrored (the wrapper would poll to its deadline and report exit 4 for an edit that
    // actually LANDED; a retry would then report `stale-range` — two contradictory failures for
    // one successful write). A rejected save gets its own typed reason. Mirrors main.ts.
    try {
      editor.replaceRange(replacement, from, to);
      await ed.save();
    } catch (err) {
      await this.writeResult({ ok: false, reason: "save-failed", nonce });
      return;
    }
    await this.writeResult({ ok: true, mode: "apply", newLen: replacement.length, nonce });
  }
}

module.exports = AgentBridge;
