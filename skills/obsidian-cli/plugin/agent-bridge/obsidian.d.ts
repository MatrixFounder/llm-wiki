// Vendored MINIMAL ambient declaration for the "obsidian" plugin API — TASK 068 / R-068-1.
//
// This is NOT the full upstream `obsidian.d.ts`; it declares ONLY the symbols `main.ts`
// touches (Plugin, App, Editor, EditorPosition, MarkdownView, TFile, DataAdapter, Notice,
// Command), each with a REAL (non-`any`) signature. An all-`any` stub would make
// `tsc --noEmit` pass vacuously (explicit `any` escapes `strict`/`noImplicitAny`), which
// would silently defeat the whole point of the R-068-1 type-check gate — see
// `docs/tasks/task-068-01-plugin-skeleton.md` TC-04 (the negative-control test that proves
// this file is not all-`any`).
//
// Kept in lockstep, by hand, with the real npm "obsidian" module's shape for the members
// actually used here. If a future task needs another symbol/member, add it here (and only
// here) rather than reaching for `any`.

declare module "obsidian" {
  export interface EditorPosition {
    line: number;
    ch: number;
  }

  export interface Editor {
    getValue(): string;
    getRange(from: EditorPosition, to: EditorPosition): string;
    replaceRange(replacement: string, from: EditorPosition, to: EditorPosition): void;
    // The real union — NOT a widened `string` (which would let `getCursor("form")` compile
    // and silently return the head position: vacuous type-checking, the very thing this
    // vendored file exists to prevent).
    getCursor(side?: "from" | "to" | "head" | "anchor"): EditorPosition;
    somethingSelected(): boolean;
    posToOffset(pos: EditorPosition): number;
  }

  export interface FileStats {
    ctime: number;
    mtime: number;
    size: number;
  }

  export class TFile {
    path: string;
    name: string;
    extension: string;
    stat: FileStats;
  }

  // The shape `workspace.activeEditor` carries. VERIFIED against the real obsidian 1.13.1
  // typings (`npm pack obsidian`): `MarkdownFileInfo` is `{app, file, editor?}` — it does
  // **NOT** declare `save()` or `getMode()`.
  //
  // ⚠️ Do NOT "helpfully" add them back. `save()` lives on `TextFileView` (real d.ts:7081),
  // which only `MarkdownView` extends; `MarkdownEditView` — the mobile/WYSIWYG editor — also
  // `implements MarkdownFileInfo` and has **no** `save()`. Declaring `save()` here previously
  // made `tsc` validate `main.ts` against a FICTION: the call type-checked and would have
  // thrown `TypeError` at runtime *after* `replaceRange` had already mutated the buffer.
  // A precisely-typed fabrication defeats this gate harder than an `any` would, because it
  // looks verified. The plugin now narrows via `instanceof MarkdownView` before calling save().
  //
  // `getMode` is declared OPTIONAL to model exactly what the plugin does — a defensive
  // `ed.getMode?.()` probe on an object that may or may not implement it — not to assert the
  // real interface has it (it does not; `MarkdownView` does).
  export interface MarkdownFileInfo {
    file: TFile | null;
    editor?: Editor;
    getMode?(): string;
  }

  // The full markdown view: a MarkdownFileInfo that additionally inherits TextFileView.save().
  export class MarkdownView implements MarkdownFileInfo {
    file: TFile | null;
    editor: Editor;
    getMode(): string;
    save(clear?: boolean): Promise<void>;
  }

  export interface DataAdapter {
    read(normalizedPath: string): Promise<string>;
    write(normalizedPath: string, data: string): Promise<void>;
    exists(normalizedPath: string): Promise<boolean>;
  }

  export class Vault {
    adapter: DataAdapter;
    getName(): string;
  }

  // Opaque handle returned by `Workspace.on`, handed to `Plugin.registerEvent` for cleanup.
  export interface EventRef {
    readonly __eventRef?: never;
  }

  // A workspace leaf hosting a markdown view — only what the attachment check below needs.
  export interface MarkdownLeaf {
    view: MarkdownView;
  }

  export class Workspace {
    activeEditor: MarkdownFileInfo | null;
    // Only the event this plugin subscribes to — it tracks the last markdown editor so the
    // commands still resolve when the agent's integrated terminal is the active leaf.
    on(name: "active-leaf-change", callback: (leaf: unknown) => void): EventRef;
    onLayoutReady(callback: () => void): void;
    // Used to prove a remembered editor is still attached (a closed note leaves a detached
    // view that still answers `.editor`/`.file`).
    getLeavesOfType(viewType: "markdown"): MarkdownLeaf[];
  }

  export class App {
    vault: Vault;
    workspace: Workspace;
  }

  export interface Command {
    id: string;
    name: string;
    callback?: () => unknown;
  }

  export abstract class Plugin {
    app: App;
    constructor(app: App, manifest: unknown);
    addCommand(command: Command): Command;
    // Register a CodeMirror 6 editor extension for all markdown editors (the persist-selection
    // ViewPlugin). Takes the CM6 `Extension` type from @codemirror/state.
    registerEditorExtension(extension: import("@codemirror/state").Extension): void;
    // Register a cleanup callback run on plugin unload (from Component; Plugin extends it).
    register(cb: () => void): void;
    // Register a workspace event subscription so it is detached on unload.
    registerEvent(ref: EventRef): void;
    onload(): void | Promise<void>;
    onunload(): void | Promise<void>;
  }

  export class Notice {
    constructor(message: string, timeout?: number);
  }
}

// ── minimal CodeMirror 6 ambient types — ONLY what the persist-selection ViewPlugin uses ──
// Same discipline as the "obsidian" block above: real (non-`any`) signatures for the members
// actually touched, kept in lockstep with @codemirror/{state,view} by hand. Obsidian provides
// these modules at runtime; here they exist only so `tsc --noEmit` can type-check main.ts.
declare module "@codemirror/state" {
  export interface SelectionRange {
    readonly from: number;
    readonly to: number;
    readonly empty: boolean;
  }
  export interface EditorSelection {
    readonly ranges: readonly SelectionRange[];
  }
  export interface EditorState {
    readonly selection: EditorSelection;
  }
  export interface Range<T> {
    readonly from: number;
    readonly to: number;
    readonly value: T;
  }
  export interface RangeSet<T> {
    readonly size: number;
  }
  // CM6's Extension is a recursive union; this opaque shape is enough for our usage (we only
  // obtain extensions from @codemirror/view and hand them to Obsidian's registerEditorExtension).
  export type Extension = { extension: Extension } | readonly Extension[];
}

declare module "@codemirror/view" {
  import { EditorState, Extension, Range, RangeSet } from "@codemirror/state";

  export interface PluginValue {
    update?(update: ViewUpdate): void;
    destroy?(): void;
  }

  export class EditorView {
    readonly hasFocus: boolean;
    readonly state: EditorState;
  }

  export interface ViewUpdate {
    readonly view: EditorView;
    readonly state: EditorState;
    readonly selectionSet: boolean;
    readonly docChanged: boolean;
    readonly viewportChanged: boolean;
    readonly focusChanged: boolean;
  }

  export type DecorationSet = RangeSet<Decoration>;

  export class Decoration {
    static mark(spec: { class?: string; attributes?: Record<string, string> }): Decoration;
    static set(of: readonly Range<Decoration>[] | Range<Decoration>, sort?: boolean): DecorationSet;
    static readonly none: DecorationSet;
    range(from: number, to: number): Range<Decoration>;
  }

  export class ViewPlugin {
    static fromClass<V extends PluginValue>(
      cls: { new (view: EditorView): V },
      spec: { decorations?: (value: V) => DecorationSet }
    ): Extension;
  }
}
