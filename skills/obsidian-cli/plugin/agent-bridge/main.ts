import { Notice, Plugin } from "obsidian";

/**
 * agent-bridge — read/replace the live editor selection for an agent running in the
 * integrated terminal (TASK 068). Three plain-`callback` commands (NOT `editorCallback`):
 * `export-selection`, `apply-edit`, and `copy-selection-ref` — all read
 * `this.app.workspace.activeEditor` INSIDE the callback body, which is strictly more
 * robust than gating on an editor-focused callback signature and needs no fallback path.
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

export default class AgentBridge extends Plugin {
  async onload(): Promise<void> {
    this.addCommand({
      id: "export-selection",
      name: "Export selection",
      callback: () => {
        void this.exportSelection();
      },
    });
    this.addCommand({
      id: "apply-edit",
      name: "Apply edit",
      callback: () => {
        void this.applyEdit();
      },
    });
    this.addCommand({
      id: "copy-selection-ref",
      name: "Copy selection reference (for the shell agent)",
      callback: () => {
        void this.copySelectionRef();
      },
    });
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
    const fromLine = from.line + 1; // CM6 line indices are 0-based; file refs are 1-based
    // If the selection ends exactly at column 0 of a later line, that line contains no
    // selected character — the last selected line is the one above it.
    const toLine = to.ch === 0 && to.line > from.line ? to.line : to.line + 1;
    const loc = fromLine === toLine ? `L${fromLine}` : `L${fromLine}-${toLine}`;
    const selection = editor.getRange(from, to); // the EXACT selected text (may be sub-line)
    const payload = `@${ed.file.path}#${loc}\n${selection}`;
    try {
      await navigator.clipboard.writeText(payload);
    } catch (_err) {
      new Notice("agent-bridge: could not write to the clipboard");
      return;
    }
    new Notice(`Copied selection @${ed.file.path}#${loc} (+ exact text)`);
  }

  private async readNonce(file: string): Promise<string> {
    try {
      const raw = await this.app.vault.adapter.read(file);
      const parsed = JSON.parse(raw) as AgentRequest;
      return parsed.nonce;
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
    const ed = this.app.workspace.activeEditor;
    if (!ed || !ed.editor || !ed.file) {
      await this.writeResult({ ok: false, reason: "no-editor", nonce });
      return;
    }
    const editor = ed.editor;
    const file = ed.file;
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
      // No readable edit payload at all -- nothing to act on. Mirror a refusal with an
      // empty nonce so a wrapper poll (which will never see ITS nonce) times out on its
      // own deadline rather than hanging.
      await this.writeResult({ ok: false, reason: "no-editor", nonce: "" });
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

    const ed = this.app.workspace.activeEditor;
    if (!ed || !ed.editor || !ed.file) {
      await this.writeResult({ ok: false, reason: "no-editor", nonce });
      return;
    }
    const editor = ed.editor;
    const file = ed.file;
    if (ed.getMode?.() === "preview") {
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
