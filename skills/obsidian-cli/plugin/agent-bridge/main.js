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
try {
  ({ Plugin, Notice } = require("obsidian"));
} catch (err) {
  Plugin = class {};
  Notice = class {
    constructor(message) {
      void message;
    }
  };
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

class AgentBridge extends Plugin {
  async onload() {
    this.addCommand({
      id: "export-selection",
      name: "Export selection",
      callback: () => {
        this.exportSelection();
      },
    });
    this.addCommand({
      id: "apply-edit",
      name: "Apply edit",
      callback: () => {
        this.applyEdit();
      },
    });
    this.addCommand({
      id: "copy-selection-ref",
      name: "Copy selection reference (for the shell agent)",
      callback: () => {
        this.copySelectionRef();
      },
    });
  }

  // Put `@<path>#L<from>-<to>\n<exact selected text>` on the clipboard: line 1 is the file:line
  // LOCATION, everything after the first newline is the EXACT selected text (a line ref alone is
  // line-granular and expands a sub-line selection to whole lines). Clipboard-only — no vault
  // I/O; runs solely from a human hotkey gesture; captured text is untrusted (H-6). Mirrors main.ts.
  async copySelectionRef() {
    const ed = this.app.workspace.activeEditor;
    if (!ed || !ed.editor || !ed.file) {
      new Notice("agent-bridge: no active editor");
      return;
    }
    const editor = ed.editor;
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
    const payload = `@${ed.file.path}#${loc}\n${selection}`;
    try {
      await navigator.clipboard.writeText(payload);
    } catch (err) {
      new Notice("agent-bridge: could not write to the clipboard");
      return;
    }
    new Notice(`Copied selection @${ed.file.path}#${loc} (+ exact text)`);
  }

  async readNonce(file) {
    try {
      const raw = await this.app.vault.adapter.read(file);
      const parsed = JSON.parse(raw);
      return parsed.nonce;
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
    const ed = this.app.workspace.activeEditor;
    if (!ed || !ed.editor || !ed.file) {
      await this.writeResult({ ok: false, reason: "no-editor", nonce });
      return;
    }
    const editor = ed.editor;
    const file = ed.file;
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
      // No readable edit payload at all -- nothing to act on. Mirror a refusal with an
      // empty nonce so a wrapper poll (which will never see ITS nonce) times out on its
      // own deadline rather than hanging.
      await this.writeResult({ ok: false, reason: "no-editor", nonce: "" });
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

    const ed = this.app.workspace.activeEditor;
    if (!ed || !ed.editor || !ed.file) {
      await this.writeResult({ ok: false, reason: "no-editor", nonce });
      return;
    }
    const editor = ed.editor;
    const file = ed.file;
    if (ed.getMode && ed.getMode() === "preview") {
      await this.writeResult({ ok: false, reason: "preview", nonce });
      return;
    }
    if (!editor.somethingSelected()) {
      await this.writeResult({ ok: false, reason: "empty-selection", nonce });
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

    editor.replaceRange(replacement, from, to);
    await ed.save();
    await this.writeResult({ ok: true, mode: "apply", newLen: replacement.length, nonce });
  }
}

module.exports = AgentBridge;
