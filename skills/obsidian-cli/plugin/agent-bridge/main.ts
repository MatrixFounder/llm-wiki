import { Editor, MarkdownFileInfo, MarkdownView, Notice, Plugin, TFile } from "obsidian";
import { Decoration, DecorationSet, EditorView, PluginValue, ViewPlugin, ViewUpdate } from "@codemirror/view";

/**
 * agent-bridge — read/replace the live editor selection for an agent running in the
 * integrated terminal (TASK 068). Three plain-`callback` commands (NOT `editorCallback`):
 * `export-selection`, `apply-edit`, and `copy-selection-ref` — all resolve the editor INSIDE
 * the callback body via `resolveEditor()`, which is strictly more robust than gating on an
 * editor-focused callback signature. `resolveEditor()` has TWO sources — the active editor,
 * else the remembered last markdown editor (`lastEditor`) — because `activeEditor` is **null**
 * exactly when the agent types in Obsidian's integrated terminal (that terminal is the active
 * leaf). That fallback is load-bearing; see `resolveEditor` / `lastEditor` below.
 *
 * It also registers a CM6 editor extension (`persistSelectionExtension`) that keeps the
 * text selection VISIBLY highlighted when the editor loses focus — e.g. when the human
 * switches to the integrated terminal to talk to the agent. CodeMirror 6 removes its own
 * selection layer on blur (verified: 0 `.cm-selectionBackground` elements when unfocused),
 * so pure CSS cannot restore it; this re-draws the selection as a mark decoration whenever
 * the editor is not focused. Purely visual — it never changes the document.
 *
 * `copy-selection-ref` (bind it to a hotkey) is the HUMAN-triggered capture path: it puts a
 * `@<vault-relative-path>#L<from>-<to>` reference for the current selection on the system
 * clipboard, so the human pastes a stable file:line reference into the agent's shell prompt
 * and the agent reads those exact lines from disk — deterministic, no `activeEditor`
 * timing/state dependency (the failure mode the read/apply channel can hit). It is the
 * MORE ROBUST capture for "give the agent a task about THIS selection"; the read/apply
 * commands remain for autonomous read and guarded in-editor write-back.
 *
 * All file I/O is scoped under `.obsidian/` via `this.app.vault.adapter.{read,write,exists}`
 * — no absolute paths, no `require('fs')`, no `child_process`, no network. This least-
 * privilege surface is the whole reason this plugin exists instead of routing everything
 * through the T3 `obsidian eval` channel (full Node RCE) — see
 * `docs/tasks/task-068-04-plugin-logic.md` for the guard contract this plugin enforces.
 *
 * Every outcome (success or refusal) is mirrored to `.obsidian/agent-result.json` LAST,
 * with the caller-supplied `nonce` echoed back — this is what lets the wrapper tell THIS
 * dispatch's result apart from a stale one left over from a prior invocation (PLAN
 * decision 2). Nothing here ever throws to the command dispatcher; every branch writes a
 * typed `{ok, reason}` result instead.
 */

const AGENT_DIR = ".obsidian";
const REQUEST_FILE = `${AGENT_DIR}/agent-request.json`;
const EDIT_FILE = `${AGENT_DIR}/agent-edit.json`;
const SELECTION_FILE = `${AGENT_DIR}/agent-selection.json`;
const RESULT_FILE = `${AGENT_DIR}/agent-result.json`;

interface AgentRequest {
  nonce: string;
}

interface AgentEdit {
  path: string;
  expectB64: string;
  replacementB64: string;
  nonce: string;
}

/**
 * Decode a base64 string to UTF-8 text — NEVER bare `atob` (ground-truth fact #6:
 * `atob` alone recovers only the raw BYTES as a Latin-1-per-char binary string, which
 * mangles anything outside Latin-1, e.g. Cyrillic). `Uint8Array.from` + `TextDecoder`
 * correctly reinterpret those bytes as UTF-8.
 */
function decodeB64Utf8(b64: string): string {
  const binary = atob(b64);
  const bytes = Uint8Array.from(binary, (c) => c.charCodeAt(0));
  return new TextDecoder("utf-8").decode(bytes);
}

// ── persist the selection highlight when the editor is unfocused ──────────────────
const PERSIST_SELECTION_CLASS = "agent-persist-selection";
const persistSelectionMark = Decoration.mark({ class: PERSIST_SELECTION_CLASS });

/**
 * A CM6 ViewPlugin that re-draws the current selection as a mark decoration whenever the
 * editor is NOT focused, and yields to CM's native selection layer when it IS. This is why
 * the selection stays visible after you switch to the integrated terminal (CM removes its
 * own selection layer on blur). The decoration is a non-destructive overlay — it does not
 * modify the document.
 */
const persistSelectionExtension = ViewPlugin.fromClass(
  class implements PluginValue {
    decorations: DecorationSet;
    constructor(view: EditorView) {
      this.decorations = this.build(view);
    }
    update(u: ViewUpdate): void {
      if (u.selectionSet || u.focusChanged || u.docChanged || u.viewportChanged) {
        this.decorations = this.build(u.view);
      }
    }
    build(view: EditorView): DecorationSet {
      if (view.hasFocus) return Decoration.none; // focused → CM draws the real selection
      const marks: ReturnType<typeof persistSelectionMark.range>[] = [];
      for (const r of view.state.selection.ranges) {
        if (!r.empty) marks.push(persistSelectionMark.range(r.from, r.to));
      }
      return Decoration.set(marks);
    }
  },
  { decorations: (v) => v.decorations }
);

export default class AgentBridge extends Plugin {
  /**
   * The most-recently-ACTIVE markdown editor. Load-bearing, not a nicety: when the agent types
   * in Obsidian's own INTEGRATED TERMINAL — the very scenario this plugin exists for — that
   * terminal is the active leaf, so `app.workspace.activeEditor` is **null** (live-verified:
   * `activeLeafType: "terminal:terminal"`, `activeEditor: null`, while the note's editor still
   * holds the selection). We therefore remember the last markdown editor and fall back to it,
   * mirroring the `recent-open` fallback in `obsidian_active_note.py` (TASK 041 / ADR-008),
   * which exists for exactly this reason.
   */
  private lastEditor: MarkdownFileInfo | null = null;

  /** Last-resort net for a command that threw outside its own typed-result handling. */
  private reportCrash(command: string, err: unknown): void {
    new Notice(`agent-bridge: ${command} failed — see the console`);
    console.error(`agent-bridge: ${command} threw`, err);
  }

  /** Remember the active markdown editor; never overwrite it with a non-editor leaf. */
  private rememberEditor(): void {
    const ae = this.app.workspace.activeEditor;
    if (ae && ae.editor && ae.file) this.lastEditor = ae;
  }

  /**
   * The editor to act on: the ACTIVE markdown editor, else the remembered one (when the active
   * leaf is the integrated terminal / a Bases view / settings). `source` records which — the
   * caller surfaces it so a fallback resolve is visible, never silent (MEDIUM confidence, same
   * discipline as the resolver's `recent-open`).
   */
  private resolveEditor(): { ed: MarkdownFileInfo; editor: Editor; file: TFile; source: string } | null {
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

  /**
   * Is the remembered editor still attached to a live markdown leaf? Load-bearing: closing the
   * note leaves a DETACHED view that still answers `.editor` and `.file` and still holds its old
   * selection — so both apply guards would pass and we could write into a note the human closed
   * (or mirror `ok:true` for a save that silently no-ops, defeating the wrapper's
   * success-is-shape contract). Identity against the live leaf list is the only honest check.
   */
  private isAttached(info: MarkdownFileInfo): boolean {
    return this.app.workspace.getLeavesOfType("markdown").some((leaf) => leaf.view === info);
  }

  async onload(): Promise<void> {
    // `.catch()` on every dispatch: a command callback is fire-and-forget, so an unhandled
    // rejection would vanish into the devtools console and leave the wrapper polling to its
    // deadline. Each handler already mirrors its own typed result; this is the last-resort net
    // so nothing floats unobserved.
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
    // integrated terminal is the active leaf (activeEditor === null there).
    this.registerEvent(this.app.workspace.on("active-leaf-change", () => this.rememberEditor()));
    this.app.workspace.onLayoutReady(() => this.rememberEditor()); // a note may already be active

    // Keep the selection visible when the editor is unfocused (see the header comment).
    this.registerEditorExtension(persistSelectionExtension);
    const style = document.createElement("style");
    style.textContent = `.${PERSIST_SELECTION_CLASS} { background-color: var(--text-selection); }`;
    document.head.appendChild(style);
    this.register(() => style.remove());
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
  private async copySelectionRef(): Promise<void> {
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
    const fromLine = from.line + 1; // CM6 line indices are 0-based; file refs are 1-based
    // If the selection ends exactly at column 0 of a later line, that line contains no
    // selected character — the last selected line is the one above it.
    const toLine = to.ch === 0 && to.line > from.line ? to.line : to.line + 1;
    const loc = fromLine === toLine ? `L${fromLine}` : `L${fromLine}-${toLine}`;
    const selection = editor.getRange(from, to); // the EXACT selected text (may be sub-line)
    const payload = `@${file.path}#${loc}\n${selection}`;
    try {
      await navigator.clipboard.writeText(payload);
    } catch (_err) {
      new Notice("agent-bridge: could not write to the clipboard");
      return;
    }
    new Notice(`Copied selection @${file.path}#${loc} (+ exact text)`);
  }

  private async readNonce(file: string): Promise<string> {
    try {
      const raw = await this.app.vault.adapter.read(file);
      const parsed = JSON.parse(raw) as AgentRequest;
      // Normalize: the file is unsigned, so `nonce` may be absent, null, or a number. Anything
      // that is not a string becomes "" — which simply never matches the wrapper's uuid4 hex
      // (fail-closed) instead of leaking `undefined`/a number into the result contract.
      return typeof parsed.nonce === "string" ? parsed.nonce : "";
    } catch (_err) {
      return "";
    }
  }

  /** Written LAST on every branch so the wrapper's nonce read-back poll never observes
   * a half-written outcome. */
  private async writeResult(payload: Record<string, unknown>): Promise<void> {
    await this.app.vault.adapter.write(RESULT_FILE, JSON.stringify(payload));
  }

  private async exportSelection(): Promise<void> {
    const nonce = await this.readNonce(REQUEST_FILE);
    const resolved = this.resolveEditor();
    if (!resolved) {
      await this.writeResult({ ok: false, reason: "no-editor", nonce });
      return;
    }
    const { ed, editor, file, source } = resolved;
    if (ed.getMode?.() === "preview") {
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
      // "active" = the focused editor; "recent-editor" = resolved via the fallback because the
      // active leaf was not a markdown editor (typically the agent's integrated terminal). The
      // wrapper surfaces this so a fallback resolve is visible to the caller, never silent.
      source,
      nonce,
    };
    await this.app.vault.adapter.write(SELECTION_FILE, JSON.stringify(selection));
    await this.writeResult({ ok: true, mode: "read", nonce });
  }

  private async applyEdit(): Promise<void> {
    let editPayload: AgentEdit;
    try {
      const raw = await this.app.vault.adapter.read(EDIT_FILE);
      editPayload = JSON.parse(raw) as AgentEdit;
    } catch (_err) {
      // No readable edit payload at all. The reason is `bad-payload`, NOT `no-editor` — there
      // may well be an editor; it is the PAYLOAD that was unreadable, and mislabelling it sends
      // whoever debugs this to inspect the wrong thing. We cannot echo a nonce we could not
      // read, so this result is unmatchable by construction and the wrapper times out on its
      // own deadline (exit 4) — that is accepted, but the reason on disk stays honest.
      await this.writeResult({ ok: false, reason: "bad-payload", nonce: "" });
      return;
    }
    const nonce = editPayload.nonce;
    // Decode INSIDE a try/catch so a malformed/missing base64 payload (a hand-crafted or
    // truncated agent-edit.json) writes a typed refusal instead of throwing to the
    // dispatcher — preserving the "never throws, always mirrors a typed result" invariant.
    // (Through the sanctioned wrapper this is unreachable — it pre-validates the base64 —
    // but agent-edit.json is an unsigned file, so the plugin fails closed on its own.)
    let expect: string;
    let replacement: string;
    try {
      expect = decodeB64Utf8(editPayload.expectB64);
      replacement = decodeB64Utf8(editPayload.replacementB64);
    } catch (_err) {
      await this.writeResult({ ok: false, reason: "bad-payload", nonce });
      return;
    }

    const resolved = this.resolveEditor();
    if (!resolved) {
      await this.writeResult({ ok: false, reason: "no-editor", nonce });
      return;
    }
    const { ed, editor, file } = resolved;
    if (ed.getMode?.() === "preview") {
      await this.writeResult({ ok: false, reason: "preview", nonce });
      return;
    }
    if (!editor.somethingSelected()) {
      await this.writeResult({ ok: false, reason: "empty-selection", nonce });
      return;
    }
    // `save()` is NOT on MarkdownFileInfo — it is inherited from TextFileView by MarkdownView
    // (verified against the real obsidian typings; MarkdownEditView implements MarkdownFileInfo
    // WITHOUT save). Narrow BEFORE mutating so an unsaveable editor is a typed refusal, never a
    // TypeError raised *after* replaceRange has already changed the buffer. Refusing up front
    // also keeps the contract honest: `ok:true` promises the edit reached DISK, and without a
    // deterministic save() we cannot promise that.
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

    // The mutate → save → mirror tail is the ONLY place we change the user's document, so it
    // must never leave the buffer edited with no result mirrored (the wrapper would poll to its
    // deadline and report exit 4 "app-not-running" for an edit that actually LANDED — and a
    // retry would then hit GUARD 2 and report `stale-range`: two contradictory failures for one
    // successful write). A rejected save (disk full, permissions, file deleted) is reported as
    // its own typed reason instead.
    try {
      editor.replaceRange(replacement, from, to);
      await ed.save();
    } catch (_err) {
      await this.writeResult({ ok: false, reason: "save-failed", nonce });
      return;
    }
    await this.writeResult({ ok: true, mode: "apply", newLen: replacement.length, nonce });
  }
}
