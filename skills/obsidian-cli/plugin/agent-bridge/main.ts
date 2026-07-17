import { Editor, MarkdownView, Notice, Plugin, TFile, getAllTags } from "obsidian";
import { Decoration, DecorationSet, EditorView, PluginValue, ViewPlugin, ViewUpdate, showTooltip, Tooltip } from "@codemirror/view";
import { EditorState, StateField } from "@codemirror/state";

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
const CONTEXT_FILE = `${AGENT_DIR}/agent-context.json`;
const RESULT_FILE = `${AGENT_DIR}/agent-result.json`;

interface AgentRequest {
  nonce: string;
  includeOutline?: boolean;
  includeFrontmatter?: boolean;
  // The selection body is the MOST sensitive field (verbatim, untrusted note text, H-6), so it
  // is opt-in exactly like frontmatter — never exported unless the caller asks for it. A caller
  // requesting only `--outline` must not silently also ingest whatever the human highlighted.
  includeSelection?: boolean;
}

interface AgentEdit {
  path: string;
  expectB64: string;
  replacementB64: string;
  // The document offsets the caller captured at READ time. Required: a payload missing them
  // yields `undefined`, which can never equal a live offset, so the position guard below
  // fail-CLOSES rather than silently degrading to the content-only check.
  fromOffset: number;
  toOffset: number;
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
/**
 * The highlight's CSS, mounted by CodeMirror itself rather than by us.
 *
 * This was a `<style>` appended to `document.head`, which stranded the highlight in the MAIN
 * window: a popout ("Move to new window") is a SEPARATE document, and a stylesheet in one
 * document does not style another. CM6 mounts style modules per EditorView ROOT — `mountStyles()`
 * calls `StyleModule.mount(this.root, …)`, and `.root` resolves to the popout's own document —
 * so every editor gets the rule wherever it lives, including editors dragged between windows
 * (`setRoot()` re-mounts). Double-injection is structurally impossible (one StyleSet per root,
 * identity-deduped), and unload cleanup becomes `registerEditorExtension`'s job.
 *
 * `baseTheme` rather than `theme`: `theme()` only applies via the generated prefix class, while
 * `baseTheme`'s ID sits unconditionally on every editor wrapper. It is the one that cannot miss.
 */
const persistSelectionTheme = EditorView.baseTheme({
  [`.${PERSIST_SELECTION_CLASS}`]: { backgroundColor: "var(--text-selection)" },
});

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

// ── selection tooltip: a floating "copy ref" button at the selection ──────────────
const SELECTION_TOOLTIP_CLASS = "agent-bridge-selection-tooltip";

/**
 * The Highlightr-style mouse path to `copy-selection-ref`: a small floating button above the
 * selection head; clicking it puts the same `@path#L…` + exact-text capture on the clipboard
 * as the hotkey. Human-triggered UI only (same T1-UX/clipboard-only class as the hotkey — no
 * new agent-reachable surface, no vault I/O). Built on CM6's native tooltip system
 * (`showTooltip`) so positioning/viewport handling is CM's, not ours, and — like the persist
 * extension — it rides `registerEditorExtension`, so popout windows get it too.
 *
 * `mousedown` + `preventDefault`, NOT `click`: a click's default mousedown would move focus
 * (and with it the selection state we are capturing) out of the editor before the handler
 * runs; preventing the default keeps the editor focused and the selection live, so
 * `copySelectionRef`'s own `resolveEditor()` sees exactly what the button hovered over.
 */
function selectionTooltipField(onCopy: () => void): StateField<readonly Tooltip[]> {
  const compute = (state: EditorState): readonly Tooltip[] => {
    const r = state.selection.main;
    if (r.empty) return [];
    return [{
      pos: r.head,
      above: true,
      strictSide: false,
      create: () => {
        const dom = document.createElement("div");
        dom.className = SELECTION_TOOLTIP_CLASS;
        const btn = dom.appendChild(document.createElement("button"));
        btn.type = "button";
        btn.textContent = "@ ref";
        btn.setAttribute("aria-label", "Copy selection reference (for the shell agent)");
        btn.addEventListener("mousedown", (e) => {
          e.preventDefault(); // keep editor focus + the live selection (see doc comment)
          onCopy();
        });
        return { dom };
      },
    }];
  };
  return StateField.define<readonly Tooltip[]>({
    create: compute,
    update(tooltips, tr) {
      if (!tr.docChanged && !tr.selection) return tooltips;
      return compute(tr.state);
    },
    provide: (f) => showTooltip.computeN([f], (state) => state.field(f)),
  });
}

/** Styled via `baseTheme` for the same reason as the persist highlight: CM mounts it into
 * every editor's own document root, popouts included (see `persistSelectionTheme`). */
const selectionTooltipTheme = EditorView.baseTheme({
  [`.${SELECTION_TOOLTIP_CLASS}`]: {
    backgroundColor: "var(--background-secondary)",
    border: "1px solid var(--background-modifier-border)",
    borderRadius: "var(--radius-s, 4px)",
    padding: "0",
  },
  [`.${SELECTION_TOOLTIP_CLASS} button`]: {
    background: "none",
    border: "none",
    padding: "2px 6px",
    cursor: "pointer",
    fontSize: "var(--font-ui-smaller, 12px)",
    color: "var(--text-muted)",
  },
});

/**
 * The outcome of resolving "which editor may we act on?" — either a `MarkdownView` we can
 * safely read AND write, or a typed reason why not. A discriminated union rather than
 * `T | null` because the caller must mirror the *specific* refusal to disk: `no-editor`,
 * `unsupported-view`, and `preview` are three different things to whoever debugs this.
 */
type ResolvedEditor =
  | { ok: true; view: MarkdownView; editor: Editor; file: TFile; source: string }
  | { ok: false; reason: "no-editor" | "unsupported-view" | "preview" };

/**
 * Like `ResolvedEditor` but WITHOUT the preview mode-gate. `export-context` is a read-only
 * metadata op (path/folder/heading/outline/tags all come from `metadataCache`, which needs no
 * live source-mode editor), so it must succeed while the human is READING the note in preview —
 * unlike `apply-edit`, which needs source mode + a deterministic `save()`. Sharing the active/
 * lastEditor/attached resolution keeps the two paths from drifting; only the mode gate differs.
 */
type ResolvedView =
  | { ok: true; view: MarkdownView; editor: Editor; file: TFile; source: string }
  | { ok: false; reason: "no-editor" | "unsupported-view" };

export default class AgentBridge extends Plugin {
  /**
   * The most-recently-ACTIVE markdown view. Load-bearing, not a nicety: when the agent types
   * in Obsidian's own INTEGRATED TERMINAL — the very scenario this plugin exists for — that
   * terminal is the active leaf, so `app.workspace.activeEditor` is **null** (live-verified:
   * `activeLeafType: "terminal:terminal"`, `activeEditor: null`, while the note's editor still
   * holds the selection). We therefore remember the last markdown editor and fall back to it,
   * mirroring the `recent-open` fallback in `obsidian_active_note.py` (TASK 041 / ADR-008),
   * which exists for exactly this reason.
   */
  private lastEditor: MarkdownView | null = null;

  /** Last-resort net for a command that threw outside its own typed-result handling. */
  private reportCrash(command: string, err: unknown): void {
    new Notice(`agent-bridge: ${command} failed — see the console`);
    console.error(`agent-bridge: ${command} threw`, err);
  }

  /**
   * Remember the active markdown view. ONLY a `MarkdownView` is worth remembering: `isAttached`
   * proves liveness by identity against the markdown leaf list, whose `view` IS the
   * `MarkdownView` (`WorkspaceLeaf.view: View`), so any other `MarkdownFileInfo` could never
   * pass it — it would be dead state that ALSO evicts a usable memory in `resolveEditor`.
   */
  private rememberEditor(): void {
    const ae = this.app.workspace.activeEditor;
    if (ae instanceof MarkdownView && ae.editor && ae.file) this.lastEditor = ae;
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
  private resolveView(): ResolvedView {
    let view: MarkdownView;
    let source: string;
    const active = this.app.workspace.activeEditor;
    if (active) {
      // ★ The `instanceof` test gates on `active` ALONE — deliberately NOT on
      // `active && active.editor && active.file`. Getting this wrong reintroduces the exact bug
      // this whole bead exists to delete: `MarkdownFileInfo.editor` is OPTIONAL (real
      // obsidian.d.ts), and `MarkdownEditView` — the canonical non-MarkdownView implementer —
      // declares NO `editor` member at all. So an `active.editor &&` pre-condition makes the
      // refusal UNREACHABLE for precisely the class it was written to catch: control falls to the
      // `else` branch and silently resolves `lastEditor`, i.e. a DIFFERENT note from the one the
      // human is looking at, and every apply guard below then passes against the wrong file.
      //
      // The rule is: if there IS an active editor, we resolve to IT or we refuse. We never fall
      // through. The `lastEditor` fallback is legitimate only when `activeEditor` is genuinely
      // NULL — the integrated-terminal case this plugin exists for (live-verified).
      if (!(active instanceof MarkdownView)) return { ok: false, reason: "unsupported-view" };
      view = active;
      source = "active";
    } else {
      const last = this.lastEditor;
      if (!last || !last.editor || !last.file || !this.isAttached(last)) {
        if (last && !this.isAttached(last)) this.lastEditor = null; // drop a dangling reference
        return { ok: false, reason: "no-editor" };
      }
      view = last;
      source = "recent-editor";
    }
    const editor = view.editor;
    const file = view.file; // FileView.file is TFile | null
    // RUNTIME ASSUMPTION (unverifiable by the deterministic tests — they simulate this plugin's
    // output): `MarkdownView.editor` stays non-null in PREVIEW mode (Obsidian keeps the editor
    // instance alive across mode switches). export-context's preview tolerance rests on it — if
    // an Obsidian release ever nulls the editor in reading view, preview reads regress to
    // `no-editor` (fail-closed, not wrong-data). Re-verify on a live preview smoke after app bumps.
    if (!editor || !file) return { ok: false, reason: "no-editor" };
    return { ok: true, view, editor, file, source };
  }

  private resolveEditor(): ResolvedEditor {
    const resolved = this.resolveView();
    if (!resolved.ok) return resolved;
    // Direct call, no `?.`: `view` IS a MarkdownView, so this guard can never evaluate to
    // undefined. `getMode()` returns `MarkdownViewModeType` ('source' | 'preview'), so a typo'd
    // literal here is a COMPILE error, not a silent fail-open. (The retired vendored d.ts
    // declared `getMode?(): string` — a double fabrication: the optional marker defeated the
    // guard at runtime, the widened `string` defeated it at compile time.)
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
  private isAttached(view: MarkdownView): boolean {
    return this.app.workspace.getLeavesOfType("markdown").some((leaf) => leaf.view === view);
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
    this.addCommand({
      id: "export-context",
      name: "Export note context",
      callback: () => {
        this.exportContext().catch((e) => this.reportCrash("export-context", e));
      },
    });

    // Track the last active markdown editor so the commands still work when the agent's
    // integrated terminal is the active leaf (activeEditor === null there).
    this.registerEvent(this.app.workspace.on("active-leaf-change", () => this.rememberEditor()));
    this.app.workspace.onLayoutReady(() => this.rememberEditor()); // a note may already be active

    // Keep the selection visible when the editor is unfocused (see the header comment). The
    // theme rides along as an extension so CM6 mounts it into EVERY editor's own document root
    // — popouts included. See `persistSelectionTheme`.
    this.registerEditorExtension([persistSelectionExtension, persistSelectionTheme]);

    // The mouse path to copy-selection-ref: a floating button at the selection (see
    // `selectionTooltipField`). Same crash net as the command dispatches.
    this.registerEditorExtension([
      selectionTooltipField(() => {
        this.copySelectionRef().catch((e) => this.reportCrash("copy-selection-ref", e));
      }),
      selectionTooltipTheme,
    ]);
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
    if (!resolved.ok) {
      // Includes `preview`, which this path did NOT guard before TASK 070: it used to copy the
      // stale source-mode selection under a confident `@path#L12-14` label.
      new Notice(`agent-bridge: cannot capture the selection (${resolved.reason})`);
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

    // `save()` is NOT on MarkdownFileInfo — it is inherited from TextFileView by MarkdownView.
    // `resolveEditor` now hands back a MarkdownView or a typed refusal, so the old post-hoc
    // `instanceof` check here is GONE: an unsaveable editor can no longer reach this code at
    // all, rather than being caught by a guard someone must remember to write. That keeps the
    // contract honest — `ok:true` promises the edit reached DISK, and without a deterministic
    // save() we could not promise that.
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

    // Derive the coordinates from the LIVE selection at apply time (load-bearing --
    // never source from/to from the payload; the payload carries no from/to at all, by
    // design, so GUARD 2 below is never tautological).
    const from = editor.getCursor("from");
    const to = editor.getCursor("to");

    // GUARD 1 — same file
    if (editPayload.path !== file.path) {
      await this.writeResult({ ok: false, reason: "path-mismatch", nonce });
      return;
    }
    // GUARD 2 — same POSITION. Content alone (GUARD 3) is NOT sufficient: an identical string
    // re-selected elsewhere in the same file satisfies it, and we would replace the WRONG
    // occurrence silently. The read already exported these offsets; the caller echoes them back
    // so the range is pinned in the document, not just matched by text.
    if (editor.posToOffset(from) !== editPayload.fromOffset || editor.posToOffset(to) !== editPayload.toOffset) {
      await this.writeResult({ ok: false, reason: "position-mismatch", nonce });
      return;
    }
    // GUARD 3 — same content at that position (still required: the offsets can survive while the
    // text under them changes, e.g. an in-place edit of the same length).
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
      await view.save();
    } catch (_err) {
      await this.writeResult({ ok: false, reason: "save-failed", nonce });
      return;
    }
    await this.writeResult({ ok: true, mode: "apply", newLen: replacement.length, nonce });
  }

  private async exportContext(): Promise<void> {
    // Read the request file ONCE — nonce and the export flags come from a single snapshot. Reading
    // it three times (as an earlier version did) is a torn-read TOCTOU: a concurrent dispatch
    // between reads could flip `includeFrontmatter` against the matched caller's intent, defeating
    // the default-off posture of the untrusted fields. `nonce` is normalized to "" (never string)
    // exactly like `readNonce`, so it simply never matches the wrapper's uuid — fail-closed.
    const req = await this.readRequest(REQUEST_FILE);
    const nonce = typeof req.nonce === "string" ? req.nonce : "";
    const includeOutline = !!req.includeOutline;
    const includeFrontmatter = !!req.includeFrontmatter;
    const includeSelection = !!req.includeSelection;

    // Read-only metadata op → tolerate PREVIEW (the human is reading the note). Metadata comes
    // from `metadataCache`, which needs no live source-mode editor; only cursor/selection do.
    const resolved = this.resolveView();
    if (!resolved.ok) {
      await this.writeResult({ ok: false, reason: resolved.reason, nonce });
      return;
    }

    const { view, editor, file, source } = resolved;
    const fileCache = this.app.metadataCache.getFileCache(file);
    const isSource = view.getMode() === "source";

    // `file.parent?.path` is "/" for a vault-root note; normalize to "" so a downstream path
    // join yields "<vault>/<name>", not "<vault>//<name>" (recipe-10 convention).
    const parentPath = file.parent?.path ?? "";
    const folder = parentPath === "/" ? "" : parentPath;

    const context: Record<string, unknown> = {
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
      nonce,
    };

    // Cursor + current-heading are meaningful ONLY in source mode (preview has no live cursor).
    if (isSource) {
      const cursor = editor.getCursor();
      context.cursor = { line: cursor.line, ch: cursor.ch };
      context.cursorOffset = editor.posToOffset(cursor);

      // The section the cursor sits in: the last heading whose start line is <= the cursor line
      // (headings are document-ordered). `heading` is the RAW heading text — no leading `#`s, as
      // Obsidian's `HeadingCache.heading` provides it. `level` disambiguates nesting.
      let currentHeading = "";
      let currentLevel = 0;
      if (fileCache?.headings) {
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

      // Selection: opt-in (untrusted, H-6 — see AgentRequest.includeSelection) AND source-mode only.
      if (includeSelection && editor.somethingSelected()) {
        const from = editor.getCursor("from");
        const to = editor.getCursor("to");
        context.selection = {
          from,
          to,
          fromOffset: editor.posToOffset(from),
          toOffset: editor.posToOffset(to),
          text: editor.getRange(from, to),
        };
      }
    }

    // Outline (opt-in): every heading, RAW text + level + line. Cache-resident — no file read.
    if (includeOutline && fileCache?.headings) {
      context.outline = fileCache.headings.map((h) => ({
        level: h.level,
        heading: h.heading,
        line: h.position.start.line,
      }));
    }

    // Tags: `getAllTags` unifies INLINE (`#tag`) and FRONTMATTER (`tags:`) tags — the raw
    // `fileCache.tags` array is inline-only and would drop every frontmatter tag. Strip the
    // leading `#` so callers get `["health"]`, not `["#health"]`.
    if (fileCache) {
      const allTags = getAllTags(fileCache);
      if (allTags && allTags.length) {
        context.tags = allTags.map((t) => (t.startsWith("#") ? t.slice(1) : t));
      }
    }

    // Frontmatter (opt-in, untrusted H-6): author-supplied YAML — data, never instructions.
    if (includeFrontmatter && fileCache?.frontmatter) {
      context.frontmatter = fileCache.frontmatter;
    }

    await this.app.vault.adapter.write(CONTEXT_FILE, JSON.stringify(context));
    await this.writeResult({ ok: true, mode: "context", nonce });
  }

  private async readRequest(file: string): Promise<AgentRequest> {
    try {
      const raw = await this.app.vault.adapter.read(file);
      return JSON.parse(raw) as AgentRequest;
    } catch (_err) {
      return { nonce: "" };
    }
  }
}
